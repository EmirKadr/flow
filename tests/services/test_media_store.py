import hashlib

from app.backend.media_store import FilesystemMediaStore


def _store(tmp_path) -> FilesystemMediaStore:
    return FilesystemMediaStore(tmp_path, chunk_bytes=64 * 1024)


def test_write_then_read_roundtrip_and_hash(tmp_path):
    store = _store(tmp_path)
    payload = b"".join(bytes([i % 256]) * 1000 for i in range(300))  # ~300 kB
    writer = store.create_writer(suffix=".mp4")
    # Mata in i småbitar för att efterlikna strömmande upload.
    for offset in range(0, len(payload), 7000):
        writer.write(payload[offset : offset + 7000])
    stored = writer.commit()

    assert stored.size == len(payload)
    assert stored.sha256 == hashlib.sha256(payload).hexdigest()
    assert stored.key.endswith(".mp4")
    assert store.stat(stored.key).size == len(payload)

    read_back = b"".join(store.open_all(stored.key))
    assert read_back == payload


def test_open_range_returns_exact_slice(tmp_path):
    store = _store(tmp_path)
    payload = bytes(range(256)) * 500  # 128 000 bytes
    writer = store.create_writer(suffix=".bin")
    writer.write(payload)
    stored = writer.commit()

    chunk = b"".join(store.open_range(stored.key, 1000, 1099))
    assert chunk == payload[1000:1100]
    assert len(chunk) == 100


def test_content_addressed_dedup(tmp_path):
    store = _store(tmp_path)
    payload = b"identical-content" * 1000

    w1 = store.create_writer(suffix=".mp4")
    w1.write(payload)
    first = w1.commit()

    w2 = store.create_writer(suffix=".mp4")
    w2.write(payload)
    second = w2.commit()

    assert first.key == second.key  # samma innehåll => samma nyckel
    assert store.materialize_to_temp(first.key).exists()


def test_abort_leaves_no_file(tmp_path):
    store = _store(tmp_path)
    writer = store.create_writer(suffix=".mp4")
    writer.write(b"partial")
    writer.abort()
    # Ingen .part-fil ska ligga kvar.
    leftover = list((tmp_path / ".tmp").glob("*.part")) if (tmp_path / ".tmp").exists() else []
    assert leftover == []


def test_path_traversal_is_blocked(tmp_path):
    store = _store(tmp_path)
    assert store.stat("../../etc/passwd") is None
    store.delete("../../etc/passwd")  # ska inte kasta


def test_delete_removes_file(tmp_path):
    store = _store(tmp_path)
    writer = store.create_writer(suffix=".jpg")
    writer.write(b"image-bytes")
    stored = writer.commit()
    assert store.stat(stored.key) is not None
    store.delete(stored.key)
    assert store.stat(stored.key) is None
