/*
 * RFID ESP32 till flow
 * Laser EM4100/125 kHz via RDM6300 och skickar scans till flow.
 */

#include <WiFi.h>
#include <HTTPClient.h>

// ====== KONFIGURERA ======
// Hemligheter/lokal konfig ligger i rfid_esp32_flow.local.h (git-ignorerad).
// Fallbacks nedan ar bara exempel sa firmwarefilen kan commitas sakert.
#if defined(__has_include)
#if __has_include("rfid_esp32_flow.local.h")
#include "rfid_esp32_flow.local.h"
#endif
#endif

#ifndef FLOW_WIFI_SSID
#define FLOW_WIFI_SSID "DIT_WIFI"
#endif
#ifndef FLOW_WIFI_PASSWORD
#define FLOW_WIFI_PASSWORD "DIT_WIFI_LOSENORD"
#endif
#ifndef FLOW_BASE_URL
#define FLOW_BASE_URL "http://FLOW_SERVER_IP:8000"
#endif
#ifndef FLOW_RFID_TOKEN
#define FLOW_RFID_TOKEN ""
#endif
#ifndef FLOW_DEVICE_ID
#define FLOW_DEVICE_ID "esp32-mg-plock-01"
#endif
#ifndef FLOW_MODULE_NAME
#define FLOW_MODULE_NAME "MG Plock"
#endif

const char* WIFI_SSID = FLOW_WIFI_SSID;
const char* WIFI_PASSWORD = FLOW_WIFI_PASSWORD;
const char* FLOW_BASE_URL_VALUE = FLOW_BASE_URL;
const char* RFID_TOKEN = FLOW_RFID_TOKEN;

const char* DEVICE_ID = FLOW_DEVICE_ID;
const char* MODULE_NAME = FLOW_MODULE_NAME;

const int RDM_RX_PIN = 16;
const int RDM_TX_PIN = 17;
// =========================

HardwareSerial RDM(2);

const uint8_t FRAME_START = 0x02;
const uint8_t FRAME_END = 0x03;
const int FRAME_LEN = 14;
const unsigned long SAME_TAG_DEDUPE_MS = 3000;

uint8_t buf[FRAME_LEN];
int bufIndex = 0;
String lastPostedTag = "";
unsigned long lastPostedAt = 0;
unsigned long scanCount = 0;

uint8_t hex2byte(uint8_t hi, uint8_t lo) {
  auto nib = [](uint8_t c) -> uint8_t {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return 0;
  };
  return (nib(hi) << 4) | nib(lo);
}

String jsonEscape(const String& value) {
  String out = "";
  for (size_t i = 0; i < value.length(); i++) {
    char c = value.charAt(i);
    if (c == '"' || c == '\\') out += '\\';
    out += c;
  }
  return out;
}

void postScan(const String& tagHex, const String& tagDec) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi saknas, hoppar over scan.");
    return;
  }
  if (tagHex == lastPostedTag && millis() - lastPostedAt < SAME_TAG_DEDUPE_MS) {
    Serial.println("Samma bricka igen direkt, lokal dedupe.");
    return;
  }

  HTTPClient http;
  String url = String(FLOW_BASE_URL_VALUE) + "/api/rfid/scans";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  if (String(RFID_TOKEN).length() > 0) {
    http.addHeader("X-Flow-RFID-Token", RFID_TOKEN);
  }

  String body = "{";
  body += "\"device_id\":\"" + jsonEscape(DEVICE_ID) + "\",";
  body += "\"module_name\":\"" + jsonEscape(MODULE_NAME) + "\",";
  body += "\"tag_hex\":\"" + jsonEscape(tagHex) + "\",";
  body += "\"tag_dec\":\"" + jsonEscape(tagDec) + "\",";
  body += "\"scan_count\":" + String(scanCount);
  body += "}";

  int code = http.POST(body);
  String response = http.getString();
  http.end();

  Serial.printf("POST %s -> HTTP %d\n", url.c_str(), code);
  if (response.length()) Serial.println(response);
  if (code >= 200 && code < 300) {
    lastPostedTag = tagHex;
    lastPostedAt = millis();
  }
}

bool parseFrame() {
  if (buf[0] != FRAME_START || buf[FRAME_LEN - 1] != FRAME_END) return false;

  uint8_t bytes[5];
  for (int i = 0; i < 5; i++) {
    bytes[i] = hex2byte(buf[1 + i * 2], buf[2 + i * 2]);
  }
  uint8_t checksum = hex2byte(buf[11], buf[12]);

  uint8_t calc = 0;
  for (int i = 0; i < 5; i++) calc ^= bytes[i];
  if (calc != checksum) return false;

  char hexStr[9];
  sprintf(hexStr, "%02X%02X%02X%02X", bytes[1], bytes[2], bytes[3], bytes[4]);

  unsigned long dec =
      ((unsigned long)bytes[1] << 24) |
      ((unsigned long)bytes[2] << 16) |
      ((unsigned long)bytes[3] << 8) |
      ((unsigned long)bytes[4]);

  scanCount++;
  String tagHex = String(hexStr);
  String tagDec = String(dec);
  Serial.printf("[%s] RFID HEX=%s DEC=%s count=%lu\n", MODULE_NAME, tagHex.c_str(), tagDec.c_str(), scanCount);
  postScan(tagHex, tagDec);
  return true;
}

void readRDM() {
  while (RDM.available()) {
    uint8_t b = RDM.read();
    if (b == FRAME_START) bufIndex = 0;
    if (bufIndex < FRAME_LEN) buf[bufIndex++] = b;
    if (bufIndex == FRAME_LEN && b == FRAME_END) {
      parseFrame();
      bufIndex = 0;
    }
  }
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("Ansluter till WiFi %s", WIFI_SSID);
  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Ansluten. IP: ");
  Serial.println(WiFi.localIP());
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\nRFID ESP32 till flow startar...");
  RDM.begin(9600, SERIAL_8N1, RDM_RX_PIN, RDM_TX_PIN);
  connectWifi();
  Serial.printf("Modul: %s, device: %s\n", MODULE_NAME, DEVICE_ID);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
  }
  readRDM();
}

