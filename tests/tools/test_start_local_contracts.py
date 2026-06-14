from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_start_local_listens_on_lan_for_hardware_devices():
    script = (ROOT / "start_local.bat").read_text(encoding="utf-8")

    assert "--host 0.0.0.0" in script
    assert "http://localhost:8000" in script
    assert "ESP32" in script
