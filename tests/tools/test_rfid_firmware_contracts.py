from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIRMWARE_DIRS = [
    ROOT / "hardware" / "MG_Plock",
    ROOT / "hardware" / "MG_VM",
]


def test_rfid_firmware_sketches_are_local_only_and_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    for firmware_dir in FIRMWARE_DIRS:
        readme = (firmware_dir / "README.md").read_text(encoding="utf-8")
        sketch_path = f"hardware/{firmware_dir.name}/{firmware_dir.name}.ino"

        assert sketch_path in gitignore
        assert "git-ignorerad" in readme
        assert "local.h" not in readme


def test_rfid_readme_documents_current_rdm6300_rx_pin():
    readmes = [(firmware_dir / "README.md").read_text(encoding="utf-8") for firmware_dir in FIRMWARE_DIRS]

    for readme in readmes:
        assert "| TX | GPIO16" in readme
        assert "GPIO14" not in readme


def test_rfid_sketches_post_directly_over_wifi():
    readmes = [(firmware_dir / "README.md").read_text(encoding="utf-8") for firmware_dir in FIRMWARE_DIRS]

    for readme in readmes:
        assert "WiFi" in readme
        assert "POST /api/rfid/scans" in readme
        assert "RFID_DEVICE_TOKEN" in readme

    for firmware_dir in FIRMWARE_DIRS:
        sketch_path = firmware_dir / f"{firmware_dir.name}.ino"
        if not sketch_path.exists():
            continue
        sketch = sketch_path.read_text(encoding="utf-8")
        assert "#include <WiFi.h>" in sketch
        assert "#include <HTTPClient.h>" in sketch
        assert "RFID HEX=" in sketch
        assert "WiFi-lage" in sketch
