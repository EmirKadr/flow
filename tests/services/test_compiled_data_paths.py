from pathlib import Path
import gzip

import pytest

from app.backend import compiled_data_paths


ROOT = Path(__file__).resolve().parents[2]


def test_compiled_data_root_defaults_to_project_local_media(monkeypatch):
    monkeypatch.setattr(compiled_data_paths.settings, "PRODUCTIVITY_DATA_DIR", "")
    monkeypatch.setattr(compiled_data_paths.settings, "MEDIA_STORE_ROOT", "")

    assert compiled_data_paths.compiled_data_root() == ROOT / "local_media" / "flow-data"


def test_compiled_data_root_uses_media_store_root(monkeypatch, tmp_path):
    monkeypatch.setattr(compiled_data_paths.settings, "PRODUCTIVITY_DATA_DIR", "")
    monkeypatch.setattr(compiled_data_paths.settings, "MEDIA_STORE_ROOT", str(tmp_path / "media"))

    assert compiled_data_paths.compiled_data_root() == tmp_path / "media" / "flow-data"


def test_compiled_data_root_prefers_productivity_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(compiled_data_paths.settings, "PRODUCTIVITY_DATA_DIR", str(tmp_path / "compiled"))
    monkeypatch.setattr(compiled_data_paths.settings, "MEDIA_STORE_ROOT", str(tmp_path / "media"))

    assert compiled_data_paths.compiled_data_root() == tmp_path / "compiled"


def test_article_max_is_seeded_from_legacy_without_creating_empty_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(compiled_data_paths.settings, "PRODUCTIVITY_DATA_DIR", str(tmp_path / "compiled"))
    legacy = tmp_path / "legacy" / "artikel_max.csv"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("artikelnummer,max,pallid\nA1,12,P1\n", encoding="utf-8-sig")
    monkeypatch.setattr(compiled_data_paths, "_legacy_bufferpall_candidates", lambda business_code, filename: [legacy])

    seeded = compiled_data_paths.seed_article_max_file("R3")

    assert seeded == tmp_path / "compiled" / "buffertpall" / "r3" / "artikel_max.csv"
    assert compiled_data_paths.article_max_has_data(seeded)
    assert seeded.read_text(encoding="utf-8-sig").endswith("A1,12,P1\n")


def test_missing_article_max_requires_bufferpall_history(monkeypatch, tmp_path):
    monkeypatch.setattr(compiled_data_paths.settings, "PRODUCTIVITY_DATA_DIR", str(tmp_path / "compiled"))
    monkeypatch.setattr(compiled_data_paths, "_legacy_bufferpall_candidates", lambda business_code, filename: [])

    with pytest.raises(FileNotFoundError) as exc_info:
        compiled_data_paths.ensure_article_max_file("R3")

    max_path = tmp_path / "compiled" / "buffertpall" / "r3" / "artikel_max.csv"
    obs_path = tmp_path / "compiled" / "buffertpall" / "r3" / "observations.csv.gz"
    assert not max_path.exists()
    assert obs_path.is_file()
    assert not compiled_data_paths.bufferpall_observations_has_history(obs_path)
    assert "buffertpallhistorik" in str(exc_info.value)


def test_header_only_article_max_is_not_usable_for_flows(monkeypatch, tmp_path):
    monkeypatch.setattr(compiled_data_paths.settings, "PRODUCTIVITY_DATA_DIR", str(tmp_path / "compiled"))
    monkeypatch.setattr(compiled_data_paths, "_legacy_bufferpall_candidates", lambda business_code, filename: [])
    max_path = compiled_data_paths.article_max_path("R3")
    max_path.parent.mkdir(parents=True)
    max_path.write_text("artikelnummer,max,pallid\n", encoding="utf-8-sig")
    obs_path = compiled_data_paths.bufferpall_observations_path("R3")
    with gzip.open(obs_path, "wt", encoding="utf-8", newline="") as handle:
        handle.write("artikelnummer,pallid,antal\nA1,P1,12\n")

    with pytest.raises(FileNotFoundError) as exc_info:
        compiled_data_paths.ensure_article_max_file("R3")

    assert not compiled_data_paths.article_max_has_data(max_path)
    assert compiled_data_paths.bufferpall_observations_has_history(obs_path)
    assert "artikel_max.csv saknas" in str(exc_info.value)


def test_observations_can_start_empty_for_bufferpall_upload(monkeypatch, tmp_path):
    monkeypatch.setattr(compiled_data_paths.settings, "PRODUCTIVITY_DATA_DIR", str(tmp_path / "compiled"))
    monkeypatch.setattr(compiled_data_paths, "_legacy_bufferpall_candidates", lambda business_code, filename: [])

    path = compiled_data_paths.ensure_bufferpall_observations_file("T3")

    assert path == tmp_path / "compiled" / "buffertpall" / "t3" / "observations.csv.gz"
    assert path.is_file()
    assert not compiled_data_paths.bufferpall_observations_has_history(path)
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert handle.readline().strip() == "artikelnummer,pallid,antal"
