/*
 * ESP32 WiFi Performance Reporter
 *
 * This Arduino sketch reports WiFi performance metrics over USB serial
 * for use with the esp32_wifi Python monitoring tool.
 *
 * Supported commands (send via serial):
 *   PERF_REPORT      - Send single performance report
 *   SPEED_TEST       - Run speed test (requires internet)
 *   SET_INTERVAL:X   - Set reporting interval to X milliseconds
 *   CONTINUOUS:ON    - Enable continuous reporting
 *   CONTINUOUS:OFF   - Disable continuous reporting
 *
 * Output format: JSON for easy parsing
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <esp_wifi.h>

// ==================== Configuration ====================
// WiFi credentials - CHANGE THESE
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Reporting settings
unsigned long reportInterval = 1000;  // Default: 1 second
bool continuousReporting = false;

// Speed test server (uses a public server by default)
const char* SPEED_TEST_URL = "http://speedtest.tele2.net/1KB.zip";
// ======================================================

// Variables
unsigned long lastReportTime = 0;
unsigned long txPackets = 0;
unsigned long rxPackets = 0;
unsigned long txBytes = 0;
unsigned long rxBytes = 0;
unsigned long txErrors = 0;
unsigned long rxErrors = 0;
unsigned long txRetries = 0;
unsigned long connectionAttempts = 0;

// Latency measurement
float latencyMin = 999999;
float latencyMax = 0;
float latencySum = 0;
int latencyCount = 0;

// Command buffer
String commandBuffer = "";

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("{\"event\":\"boot\",\"message\":\"ESP32 WiFi Performance Reporter starting\"}");

    // Connect to WiFi
    connectWiFi();
}

void loop() {
    // Handle serial commands
    handleSerial();

    // Check WiFi connection
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("{\"event\":\"disconnected\",\"message\":\"WiFi disconnected, reconnecting...\"}");
        connectWiFi();
    }

    // Continuous reporting
    if (continuousReporting && (millis() - lastReportTime >= reportInterval)) {
        sendPerformanceReport();
        lastReportTime = millis();
    }

    // Periodic latency measurement
    static unsigned long lastPingTime = 0;
    if (millis() - lastPingTime >= 5000) {
        measureLatency();
        lastPingTime = millis();
    }

    delay(10);
}

void connectWiFi() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    Serial.print("{\"event\":\"connecting\",\"ssid\":\"");
    Serial.print(WIFI_SSID);
    Serial.println("\"}");

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        attempts++;
        connectionAttempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.print("{\"event\":\"connected\",\"ssid\":\"");
        Serial.print(WIFI_SSID);
        Serial.print("\",\"ip\":\"");
        Serial.print(WiFi.localIP().toString());
        Serial.print("\",\"rssi\":");
        Serial.print(WiFi.RSSI());
        Serial.println("}");
    } else {
        Serial.println("{\"event\":\"connection_failed\",\"message\":\"Failed to connect to WiFi\"}");
    }
}

void handleSerial() {
    while (Serial.available()) {
        char c = Serial.read();

        if (c == '\n' || c == '\r') {
            if (commandBuffer.length() > 0) {
                processCommand(commandBuffer);
                commandBuffer = "";
            }
        } else {
            commandBuffer += c;
        }
    }
}

void processCommand(String cmd) {
    cmd.trim();
    cmd.toUpperCase();

    if (cmd == "PERF_REPORT") {
        sendPerformanceReport();
    }
    else if (cmd == "SPEED_TEST") {
        runSpeedTest();
    }
    else if (cmd.startsWith("SET_INTERVAL:")) {
        String intervalStr = cmd.substring(13);
        reportInterval = intervalStr.toInt();
        Serial.print("{\"event\":\"interval_set\",\"interval_ms\":");
        Serial.print(reportInterval);
        Serial.println("}");
    }
    else if (cmd == "CONTINUOUS:ON") {
        continuousReporting = true;
        lastReportTime = millis();
        Serial.println("{\"event\":\"continuous_enabled\"}");
    }
    else if (cmd == "CONTINUOUS:OFF") {
        continuousReporting = false;
        Serial.println("{\"event\":\"continuous_disabled\"}");
    }
    else {
        Serial.print("{\"event\":\"unknown_command\",\"command\":\"");
        Serial.print(cmd);
        Serial.println("\"}");
    }
}

void sendPerformanceReport() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("{\"status\":\"disconnected\",\"rssi\":null}");
        return;
    }

    // Get WiFi stats
    wifi_ap_record_t wifiInfo;
    esp_wifi_sta_get_ap_info(&wifiInfo);

    // Calculate latency stats
    float latencyAvg = (latencyCount > 0) ? (latencySum / latencyCount) : 0;

    // Build JSON response
    Serial.print("{");
    Serial.print("\"status\":\"connected\"");
    Serial.print(",\"ssid\":\""); Serial.print(WiFi.SSID()); Serial.print("\"");
    Serial.print(",\"bssid\":\""); Serial.print(WiFi.BSSIDstr()); Serial.print("\"");
    Serial.print(",\"channel\":"); Serial.print(WiFi.channel());
    Serial.print(",\"rssi\":"); Serial.print(WiFi.RSSI());

    // Link speed (if available)
    Serial.print(",\"link_speed\":"); Serial.print(wifiInfo.phy_11n ? 150 : 54);

    // Packet statistics
    Serial.print(",\"tx_packets\":"); Serial.print(txPackets);
    Serial.print(",\"rx_packets\":"); Serial.print(rxPackets);
    Serial.print(",\"tx_bytes\":"); Serial.print(txBytes);
    Serial.print(",\"rx_bytes\":"); Serial.print(rxBytes);
    Serial.print(",\"tx_errors\":"); Serial.print(txErrors);
    Serial.print(",\"rx_errors\":"); Serial.print(rxErrors);
    Serial.print(",\"tx_retries\":"); Serial.print(txRetries);

    // Latency
    if (latencyCount > 0) {
        Serial.print(",\"latency_min\":"); Serial.print(latencyMin, 1);
        Serial.print(",\"latency_avg\":"); Serial.print(latencyAvg, 1);
        Serial.print(",\"latency_max\":"); Serial.print(latencyMax, 1);
    }

    // System info
    Serial.print(",\"free_heap\":"); Serial.print(ESP.getFreeHeap());
    Serial.print(",\"uptime\":"); Serial.print(millis() / 1000);
    Serial.print(",\"cpu_freq\":"); Serial.print(ESP.getCpuFreqMHz());

    Serial.println("}");
}

void measureLatency() {
    if (WiFi.status() != WL_CONNECTED) return;

    // Ping the gateway
    IPAddress gateway = WiFi.gatewayIP();

    unsigned long startTime = micros();

    // Simple TCP connect to measure latency
    WiFiClient client;
    if (client.connect(gateway, 80)) {
        unsigned long endTime = micros();
        float latency = (endTime - startTime) / 1000.0;  // Convert to ms

        latencySum += latency;
        latencyCount++;

        if (latency < latencyMin) latencyMin = latency;
        if (latency > latencyMax) latencyMax = latency;

        client.stop();
        txPackets++;
        rxPackets++;
    } else {
        txErrors++;
    }
}

void runSpeedTest() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("{\"event\":\"speed_test\",\"status\":\"failed\",\"error\":\"not_connected\"}");
        return;
    }

    Serial.println("{\"event\":\"speed_test\",\"status\":\"starting\"}");

    HTTPClient http;
    http.begin(SPEED_TEST_URL);
    http.setTimeout(30000);

    // Download test
    unsigned long downloadStart = millis();
    int httpCode = http.GET();

    if (httpCode == HTTP_CODE_OK) {
        WiFiClient* stream = http.getStreamPtr();
        int totalBytes = 0;
        uint8_t buffer[1024];

        while (stream->available()) {
            int bytesRead = stream->readBytes(buffer, sizeof(buffer));
            totalBytes += bytesRead;
            rxBytes += bytesRead;
            rxPackets++;
        }

        unsigned long downloadTime = millis() - downloadStart;
        float downloadSpeed = (totalBytes * 8.0 / 1000.0) / (downloadTime / 1000.0);  // Kbps

        Serial.print("{\"event\":\"speed_test\",\"status\":\"completed\"");
        Serial.print(",\"download_speed\":"); Serial.print(downloadSpeed / 1000.0, 2);  // Mbps
        Serial.print(",\"download_bytes\":"); Serial.print(totalBytes);
        Serial.print(",\"download_time_ms\":"); Serial.print(downloadTime);
        Serial.println("}");
    } else {
        Serial.print("{\"event\":\"speed_test\",\"status\":\"failed\",\"http_code\":");
        Serial.print(httpCode);
        Serial.println("}");
        txErrors++;
    }

    http.end();
}
