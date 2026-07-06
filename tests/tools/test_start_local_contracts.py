from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_start_local_listens_on_lan_for_hardware_devices():
    script = (ROOT / "scripts" / "start_local.bat").read_text(encoding="utf-8")

    assert "--host 0.0.0.0" in script
    assert "http://localhost:8000" in script
    assert "RFID" in script
    assert "WiFi" in script


def test_start_local_is_fast_user_mode_without_reload_or_implicit_live_sync():
    script = (ROOT / "scripts" / "start_local.bat").read_text(encoding="utf-8")

    assert "--reload" not in script
    assert 'FLOW_SYNC_LIVE_ON_START=0' in script


def test_dev_and_live_sync_scripts_are_explicit_modes():
    dev_script = (ROOT / "scripts" / "start_dev.bat").read_text(encoding="utf-8")
    sync_script = (ROOT / "scripts" / "sync_live_local.bat").read_text(encoding="utf-8")

    assert "--reload" in dev_script
    assert 'FLOW_SYNC_LIVE_ON_START=0' in dev_script
    assert 'FLOW_SYNC_LIVE_ON_START=1' in sync_script
    assert "start_local.bat/uvicorn" in sync_script
