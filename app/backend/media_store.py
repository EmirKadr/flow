"""Strömmande media-lagring för meta-uppladdningar.

Hela poängen med den här modulen är att en mediafil (video/bild) aldrig hålls i
sin helhet i RAM. All IO sker chunk för chunk:

* skrivning: ``create_writer()`` -> ``write(chunk)`` -> ``commit()`` (atomiskt
  byte, sha256 + storlek beräknas under skrivningen).
* läsning: ``open_all()`` / ``open_range()`` yield:ar ~chunk-stora block.
* analys (ffmpeg/Gemini): ``materialize_to_temp()`` ger en filväg utan att
  ladda bytena i processminnet.

Standardbackend är ``FilesystemMediaStore`` som lagrar filer under
``MEDIA_STORE_ROOT`` (i prod en monterad disk). Lagringen är medvetet *inte*
extern molnlagring. En ADR-anteckning om valet finns i ``get_media_store``.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

from .config import settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ObjectStat:
    size: int


class MediaWriter(Protocol):
    def write(self, chunk: bytes) -> None: ...
    def commit(self) -> StoredObject: ...
    def abort(self) -> None: ...


class MediaStore(Protocol):
    backend: str

    def create_writer(self, *, suffix: str = "") -> MediaWriter: ...
    def stat(self, key: str) -> ObjectStat | None: ...
    def open_all(self, key: str) -> Iterator[bytes]: ...
    def open_range(self, key: str, start: int, end: int) -> Iterator[bytes]: ...
    def materialize_to_temp(self, key: str) -> Path: ...
    def delete(self, key: str) -> None: ...


class _FilesystemWriter:
    """Skriver inkommande chunks till en temp-fil och flyttar atomiskt vid commit.

    Den slutliga nyckeln är innehållsadresserad (sha256), så identiska filer
    delar samma path och dubbletter blir gratis dedup.
    """

    def __init__(self, store: "FilesystemMediaStore", suffix: str) -> None:
        self._store = store
        self._suffix = suffix
        tmp_dir = store._tmp_dir()
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=str(tmp_dir), suffix=".part")
        self._tmp_path = Path(name)
        self._fh = os.fdopen(fd, "wb")
        self._hash = hashlib.sha256()
        self._size = 0
        self._open = True

    def write(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._fh.write(chunk)
        self._hash.update(chunk)
        self._size += len(chunk)

    def commit(self) -> StoredObject:
        if self._open:
            self._fh.close()
            self._open = False
        digest = self._hash.hexdigest()
        key = self._store.key_for(digest, self._suffix)
        dest = self._store._path_for_key(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            # Innehållet finns redan (dedup) — släng temp-filen.
            self._tmp_path.unlink(missing_ok=True)
        else:
            os.replace(self._tmp_path, dest)
        return StoredObject(key=key, size=self._size, sha256=digest)

    def abort(self) -> None:
        try:
            if self._open:
                self._fh.close()
                self._open = False
        finally:
            self._tmp_path.unlink(missing_ok=True)


class FilesystemMediaStore:
    backend = "filesystem"

    def __init__(self, root: Path, chunk_bytes: int) -> None:
        self._root = root.resolve()
        self._chunk = max(64 * 1024, int(chunk_bytes))

    def _tmp_dir(self) -> Path:
        return self._root / ".tmp"

    def key_for(self, digest: str, suffix: str) -> str:
        suffix = suffix if suffix.startswith(".") or suffix == "" else f".{suffix}"
        return f"meta/{digest[:2]}/{digest}{suffix}"

    def _path_for_key(self, key: str) -> Path:
        safe = str(key or "").replace("\\", "/").lstrip("/")
        path = (self._root / safe).resolve()
        # Skydd mot path traversal — måste ligga under roten.
        if path != self._root and self._root not in path.parents:
            raise ValueError(f"Ogiltig lagringsnyckel: {key!r}")
        return path

    def create_writer(self, *, suffix: str = "") -> _FilesystemWriter:
        return _FilesystemWriter(self, suffix)

    def stat(self, key: str) -> ObjectStat | None:
        try:
            path = self._path_for_key(key)
        except ValueError:
            return None
        if not path.is_file():
            return None
        return ObjectStat(size=path.stat().st_size)

    def open_all(self, key: str) -> Iterator[bytes]:
        path = self._path_for_key(key)
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(self._chunk)
                if not chunk:
                    break
                yield chunk

    def open_range(self, key: str, start: int, end: int) -> Iterator[bytes]:
        if end < start:
            return
        path = self._path_for_key(key)
        remaining = end - start + 1
        with open(path, "rb") as fh:
            fh.seek(start)
            while remaining > 0:
                chunk = fh.read(min(self._chunk, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def materialize_to_temp(self, key: str) -> Path:
        # Filerna ligger redan på disk — ingen kopiering behövs.
        return self._path_for_key(key)

    def delete(self, key: str) -> None:
        try:
            self._path_for_key(key).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


_STORE: MediaStore | None = None


def get_media_store() -> MediaStore:
    """Returnera en process-singleton för aktuell backend.

    ADR: ``filesystem`` (monterad disk) är default. Vald framför att lagra
    bytes i Postgres eftersom DB-instansen är liten (1 GB RAM / 0.5 CPU) och
    stora binärblobbar då skulle konkurrera med appens queries. Disk håller
    media-IO helt utanför databasen och är billigare för stora filer. Extern
    molnlagring (S3/Azure) är medvetet utesluten.
    """
    global _STORE
    if _STORE is not None:
        return _STORE
    backend = (settings.MEDIA_STORE_BACKEND or "filesystem").strip().lower()
    if backend != "filesystem":
        raise RuntimeError(
            f"MEDIA_STORE_BACKEND={backend!r} stöds inte ännu. Använd 'filesystem'."
        )
    root = (settings.MEDIA_STORE_ROOT or "").strip()
    root_path = Path(root) if root else Path(tempfile.gettempdir()) / "flow_media_store"
    root_path.mkdir(parents=True, exist_ok=True)
    _STORE = FilesystemMediaStore(root_path, settings.MEDIA_STORE_CHUNK_BYTES)
    return _STORE


def reset_media_store_cache() -> None:
    """Endast för tester — tvinga omladdning av singletonen."""
    global _STORE
    _STORE = None
