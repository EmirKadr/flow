from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIRMWARE_DIR = ROOT / "hardware" / "rfid_esp32_flow"


def test_rfid_firmware_sketch_is_local_only_and_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    readme = (FIRMWARE_DIR / "README.md").read_text(encoding="utf-8")

    assert "hardware/rfid_esp32_flow/rfid_esp32_flow.ino" in gitignore
    assert "git-ignorerad" in readme
    assert "rfid_esp32_flow.local.h" not in readme


def test_rfid_readme_documents_current_rdm6300_rx_pin():
    readme = (FIRMWARE_DIR / "README.md").read_text(encoding="utf-8")

    assert "| TX | GPIO16" in readme
    assert "GPIO14" not in readme


def test_rfid_readme_documents_four_wifi_slots():
    readme = (FIRMWARE_DIR / "README.md").read_text(encoding="utf-8")

    assert "WIFI_SSID_2" in readme
    assert "WIFI_SSID_3" in readme
    assert "WIFI_SSID_4" in readme
    assert "Tomma slots hoppas over" in readme
