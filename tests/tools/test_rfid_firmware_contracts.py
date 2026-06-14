import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIRMWARE_DIR = ROOT / "hardware" / "rfid_esp32_flow"


def test_rfid_firmware_uses_ignored_local_config_header():
    ino = (FIRMWARE_DIR / "rfid_esp32_flow.ino").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert '__has_include("rfid_esp32_flow.local.h")' in ino
    assert '#include "rfid_esp32_flow.local.h"' in ino
    assert "hardware/rfid_esp32_flow/*.local.h" in gitignore
    assert not re.search(r'const\s+char\*\s+(WIFI_SSID|WIFI_PASSWORD|RFID_TOKEN)\s*=\s*"', ino)


def test_rfid_firmware_example_config_is_placeholder_only():
    example = (FIRMWARE_DIR / "rfid_esp32_flow.local.example.h").read_text(encoding="utf-8")

    assert "#define FLOW_WIFI_SSID" in example
    assert "#define FLOW_WIFI_PASSWORD" in example
    assert "#define FLOW_BASE_URL" in example
    assert "#define FLOW_RFID_TOKEN" in example
    assert "DIT_WIFI" in example
    assert "DIN_DATOR_IP" in example
