/*
 * Venus Bot 1 body — ESP32-S3.
 *
 * The ESP32 is Bot 1's body. Over its WiFi link to the Pi relay it:
 *   - polls GET /latest for the newest Bot 1 turn and prints it to Serial,
 *   - reads a line you type into the Serial Monitor and POSTs it to /line,
 *     which the Pi turns into a new task for the two bots.
 *
 * The human interface is Serial; the network link is WiFi to the Pi (never the
 * laptop directly — the ESP32 can't run Tailscale, so the Pi is the relay).
 *
 * Copy secrets.h.example to secrets.h and fill it in. secrets.h is gitignored.
 * Board: any ESP32-S3 dev module. Libraries: WiFi + HTTPClient (bundled with the
 * Arduino ESP32 core).
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include "secrets.h"   // WIFI_SSID, WIFI_PASS, RELAY_HOST, RELAY_PORT, API_KEY

static const unsigned long POLL_INTERVAL_MS = 2000;
static unsigned long lastPoll = 0;
static long lastSeq = 0;          // highest Bot 1 turn seq already shown
static String serialLine = "";    // accumulates a typed line

String relayUrl(const char *path) {
  return String("http://") + RELAY_HOST + ":" + String(RELAY_PORT) + path;
}

void connectWiFi() {
  Serial.printf("Connecting to WiFi \"%s\"", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }
  Serial.printf("\nconnected, IP %s\n", WiFi.localIP().toString().c_str());
  Serial.println("Type a line + Enter to assign a task to the two bots.\n");
}

// Very small extractor: pull "seq" and "text" out of the relay's JSON without a
// JSON library. Good enough for the relay's flat {seq,bot,text} response.
long jsonInt(const String &body, const char *key) {
  int k = body.indexOf(String("\"") + key + "\"");
  if (k < 0) return -1;
  int c = body.indexOf(':', k);
  if (c < 0) return -1;
  return body.substring(c + 1).toInt();
}

String jsonStr(const String &body, const char *key) {
  int k = body.indexOf(String("\"") + key + "\"");
  if (k < 0) return "";
  int c = body.indexOf(':', k);
  int q1 = body.indexOf('"', c + 1);
  int q2 = body.indexOf('"', q1 + 1);
  if (q1 < 0 || q2 < 0) return "";
  return body.substring(q1 + 1, q2);
}

void pollLatest() {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(relayUrl("/latest"));
  int code = http.GET();
  if (code == 200) {
    String body = http.getString();
    long seq = jsonInt(body, "seq");
    if (seq > lastSeq) {
      lastSeq = seq;
      String text = jsonStr(body, "text");
      Serial.println("=== BOT 1 (this ESP32) ===");
      Serial.println(text);
      Serial.println();
    }
  }
  http.end();
}

void sendLine(const String &text) {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(relayUrl("/line"));
  http.addHeader("Content-Type", "application/json");
  // Minimal JSON escaping for quotes/backslashes.
  String esc = text;
  esc.replace("\\", "\\\\");
  esc.replace("\"", "\\\"");
  String payload = String("{\"text\":\"") + esc + "\"}";
  int code = http.POST(payload);
  Serial.printf("[sent to relay, HTTP %d] %s\n", code, text.c_str());
  http.end();
}

void readSerial() {
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      serialLine.trim();
      if (serialLine.length() > 0) {
        sendLine(serialLine);
        serialLine = "";
      }
    } else {
      serialLine += ch;
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\nVenus Bot 1 (ESP32) starting...");
  connectWiFi();
}

void loop() {
  readSerial();
  if (millis() - lastPoll >= POLL_INTERVAL_MS) {
    lastPoll = millis();
    pollLatest();
  }
}
