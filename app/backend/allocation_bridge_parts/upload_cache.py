def _safe_upload_stem(filename: str | None) -> str:
    stem = Path(filename or "upload").stem or "upload"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-")
    return (safe or "upload")[:80]


def _upload_cache_index_dir() -> Path:
    return _active_upload_cache_dir() / ".index"


def _upload_cache_reference_path(cache_key: str) -> Path:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return _upload_cache_index_dir() / f"{digest}.txt"


def _upload_cache_referenced_names() -> set[str]:
    index_dir = _upload_cache_index_dir()
    if not index_dir.exists():
        return set()
    names: set[str] = set()
    for path in index_dir.iterdir():
        try:
            if path.is_file():
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    names.add(value)
        except OSError:
            continue
    return names


def _remember_upload_cache(cache_key: str | None, target: Path) -> None:
    if not cache_key:
        return
    index_dir = _upload_cache_index_dir()
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = _upload_cache_reference_path(cache_key)
    previous = ""
    try:
        previous = index_path.read_text(encoding="utf-8").strip() if index_path.exists() else ""
    except OSError:
        previous = ""
    if previous == target.name:
        return

    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        dir=index_dir,
        prefix="pending_",
        suffix=".txt",
        mode="w",
        encoding="utf-8",
    )
    try:
        tmp.write(target.name)
        tmp.close()
        Path(tmp.name).replace(index_path)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise

    if previous and previous not in _upload_cache_referenced_names():
        try:
            (_active_upload_cache_dir() / previous).unlink(missing_ok=True)
        except OSError:
            pass


def _cleanup_upload_cache(now: float | None = None) -> None:
    cache_dir = _active_upload_cache_dir()
    try:
        if not cache_dir.exists():
            return
        now_ts = time.time() if now is None else now
        retained: list[tuple[float, int, Path]] = []
        for path in cache_dir.iterdir():
            try:
                if not path.is_file():
                    continue
                stat = path.stat()
                if now_ts - stat.st_mtime > UPLOAD_CACHE_TTL_SECONDS:
                    path.unlink(missing_ok=True)
                    continue
                retained.append((stat.st_mtime, stat.st_size, path))
            except OSError:
                continue

        overflow = len(retained) - UPLOAD_CACHE_MAX_FILES
        if overflow > 0:
            for _mtime, _size, path in sorted(retained)[:overflow]:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    continue
            retained = sorted(retained)[overflow:]

        total_bytes = sum(size for _mtime, size, _path in retained)
        if total_bytes > UPLOAD_CACHE_MAX_BYTES:
            for _mtime, size, path in sorted(retained):
                try:
                    path.unlink(missing_ok=True)
                    total_bytes -= size
                except OSError:
                    continue
                if total_bytes <= UPLOAD_CACHE_MAX_BYTES:
                    break
        index_dir = _upload_cache_index_dir()
        if index_dir.exists():
            existing = {path.name for path in cache_dir.iterdir() if path.is_file()}
            for path in index_dir.iterdir():
                try:
                    if path.is_file() and path.read_text(encoding="utf-8").strip() not in existing:
                        path.unlink(missing_ok=True)
                except OSError:
                    continue
    except OSError:
        return


async def _write_upload_to_temp(
    upload: UploadFile,
    *,
    directory: Path | None = None,
    prefix: str,
    suffix: str,
) -> tuple[Path, str]:
    digest = hashlib.sha256()
    tmp = tempfile.NamedTemporaryFile(delete=False, dir=directory, prefix=prefix, suffix=suffix)
    path = Path(tmp.name)
    try:
        while True:
            chunk = await upload.read(UPLOAD_READ_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            tmp.write(chunk)
        tmp.close()
        return path, digest.hexdigest()
    except Exception:
        tmp.close()
        path.unlink(missing_ok=True)
        raise


async def save_upload(upload: UploadFile, *, cache: bool = False, cache_key: str | None = None) -> Path:
    suffix = Path(upload.filename or "").suffix or ".csv"
    if cache:
        cache_dir = _active_upload_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cleanup_upload_cache()
        temp_path, digest = await _write_upload_to_temp(
            upload,
            directory=cache_dir,
            prefix="pending_",
            suffix=suffix,
        )
        target = cache_dir / f"{digest}{suffix}"
        if target.exists():
            temp_path.unlink(missing_ok=True)
        else:
            temp_path.replace(target)
        _remember_upload_cache(cache_key, target)
        _cleanup_upload_cache()
        return target

    prefix = f"bem_allok_upload_{_safe_upload_stem(upload.filename)}_"
    path, _digest = await _write_upload_to_temp(upload, prefix=prefix, suffix=suffix)
    return path


def _cleanup_sessions(now: float | None = None) -> None:
    cache_dir = _active_session_cache_dir()
    now_ts = time.time() if now is None else now
    for session_id, session in list(SESSIONS.items()):
        try:
            created_at = float(session.get("created_at") or now_ts)
        except (TypeError, ValueError):
            created_at = now_ts
        if now_ts - created_at > SESSION_TTL_SECONDS:
            removed = SESSIONS.pop(session_id, None)
            _remove_session(removed)

    overflow = len(SESSIONS) - SESSION_MAX_COUNT
    ordered = sorted(
        SESSIONS.items(),
        key=lambda item: float(item[1].get("created_at") or now_ts),
    )
    if overflow > 0:
        for session_id, _session in ordered[:overflow]:
            removed = SESSIONS.pop(session_id, None)
            _remove_session(removed)
        ordered = ordered[overflow:]

    total_bytes = sum(_session_size_bytes(session) for _session_id, session in ordered)
    if total_bytes > SESSION_MAX_BYTES:
        for session_id, session in ordered:
            if len(SESSIONS) <= 1:
                break
            removed = SESSIONS.pop(session_id, None)
            total_bytes -= _session_size_bytes(session)
            _remove_session(removed)
            if total_bytes <= SESSION_MAX_BYTES:
                break

    try:
        if cache_dir.exists():
            active_paths = {path.resolve() for session in SESSIONS.values() for path in _session_file_paths(session)}
            for path in cache_dir.iterdir():
                try:
                    if not path.is_file():
                        continue
                    stat = path.stat()
                    if path.resolve() not in active_paths and now_ts - stat.st_mtime > SESSION_TTL_SECONDS:
                        path.unlink(missing_ok=True)
                except OSError:
                    continue
    except OSError:
        return


