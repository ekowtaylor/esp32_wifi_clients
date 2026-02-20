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
 *   SET_NAME:X       - Set device name (persists across reboots, max 32 chars)
 *   GET_NAME         - Get current device name
 *
 * Output format: JSON for easy parsing
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <esp_wifi.h>
#include <Preferences.h>

// ==================== Configuration ====================
// WiFi credentials - CHANGE THESE
const char* WIFI_SSID = "Pixel_6104";
const char* WIFI_PASSWORD = "54321qwert";

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

// Device naming
Preferences preferences;
String deviceName = "";

void setup() {
    Serial.begin(115200);
    delay(1000);

    // Load device name from NVS
    preferences.begin("wifi_monitor", false);
    deviceName = preferences.getString("device_name", "");
    
    Serial.print("{\"event\":\"boot\",\"message\":\"ESP32 WiFi Performance Reporter starting\"");
    if (deviceName.length() > 0) {
        Serial.print(",\"device_name\":\"");
        Serial.print(deviceName);
        Serial.print("\"");
    }
    Serial.println("}");

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
    
    // Handle SET_NAME specially to preserve case
    String cmdUpper = cmd;
    cmdUpper.toUpperCase();
    
    if (cmdUpper.startsWith("SET_NAME:")) {
        String newName = cmd.substring(9);  // Use original case
        newName.trim();
        if (newName.length() > 0 && newName.length() <= 32) {
            deviceName = newName;
            preferences.putString("device_name", deviceName);
            Serial.print("{\"event\":\"name_set\",\"device_name\":\"");
            Serial.print(deviceName);
            Serial.println("\"}");
        } else {
            Serial.println("{\"event\":\"error\",\"message\":\"Name must be 1-32 characters\"}");
        }
        return;
    }
    
    // For other commands, use uppercase
    cmd = cmdUpper;

    if (cmd == "PERF_REPORT") {
        sendPerformanceReport();
    }
    else if (cmd == "GET_NAME") {
        Serial.print("{\"event\":\"device_name\",\"device_name\":\"");
        Serial.print(deviceName);
        Serial.println("\"}");
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
        Serial.print("{\"status\":\"disconnected\"");
        if (deviceName.length() > 0) {
            Serial.print(",\"device_name\":\"");
            Serial.print(deviceName);
            Serial.print("\"");
        }
        Serial.println(",\"rssi\":null}");
        return;
    }

    // Get detailed WiFi stats from ESP-IDF
    wifi_ap_record_t wifiInfo;
    esp_wifi_sta_get_ap_info(&wifiInfo);

    // Get TX power
    int8_t txPower;
    esp_wifi_get_max_tx_power(&txPower);

    // Get WiFi protocol mode
    uint8_t protocol;
    esp_wifi_get_protocol(WIFI_IF_STA, &protocol);

    // Get bandwidth
    wifi_bandwidth_t bandwidth;
    esp_wifi_get_bandwidth(WIFI_IF_STA, &bandwidth);

    // Calculate latency stats
    float latencyAvg = (latencyCount > 0) ? (latencySum / latencyCount) : 0;

    // Estimate noise floor (typical values for 2.4GHz: -90 to -95 dBm)
    int noiseFloor = -95;
    int snr = WiFi.RSSI() - noiseFloor;

    // Determine PHY mode string
    String phyMode = "unknown";
    if (wifiInfo.phy_11ax) phyMode = "802.11ax";
    else if (wifiInfo.phy_11n) phyMode = "802.11n";
    else if (wifiInfo.phy_11g) phyMode = "802.11g";
    else if (wifiInfo.phy_11b) phyMode = "802.11b";

    // Determine auth mode string
    String authMode = "unknown";
    switch (wifiInfo.authmode) {
        case WIFI_AUTH_OPEN: authMode = "open"; break;
        case WIFI_AUTH_WEP: authMode = "wep"; break;
        case WIFI_AUTH_WPA_PSK: authMode = "wpa_psk"; break;
        case WIFI_AUTH_WPA2_PSK: authMode = "wpa2_psk"; break;
        case WIFI_AUTH_WPA_WPA2_PSK: authMode = "wpa_wpa2_psk"; break;
        case WIFI_AUTH_WPA3_PSK: authMode = "wpa3_psk"; break;
        case WIFI_AUTH_WPA2_WPA3_PSK: authMode = "wpa2_wpa3_psk"; break;
        case WIFI_AUTH_WAPI_PSK: authMode = "wapi_psk"; break;
        default: authMode = "enterprise"; break;
    }

    // Determine pairwise cipher string
    String cipher = "unknown";
    switch (wifiInfo.pairwise_cipher) {
        case WIFI_CIPHER_TYPE_NONE: cipher = "none"; break;
        case WIFI_CIPHER_TYPE_WEP40: cipher = "wep40"; break;
        case WIFI_CIPHER_TYPE_WEP104: cipher = "wep104"; break;
        case WIFI_CIPHER_TYPE_TKIP: cipher = "tkip"; break;
        case WIFI_CIPHER_TYPE_CCMP: cipher = "ccmp"; break;
        case WIFI_CIPHER_TYPE_TKIP_CCMP: cipher = "tkip_ccmp"; break;
        case WIFI_CIPHER_TYPE_AES_CMAC128: cipher = "aes_cmac128"; break;
        case WIFI_CIPHER_TYPE_GCMP: cipher = "gcmp"; break;
        case WIFI_CIPHER_TYPE_GCMP256: cipher = "gcmp256"; break;
        default: break;
    }

    // Bandwidth string
    String bwStr = (bandwidth == WIFI_BW_HT20) ? "20MHz" : "40MHz";

    // Estimate link speed based on PHY mode and bandwidth
    int linkSpeed = 54;  // Default 802.11g
    if (wifiInfo.phy_11ax) {
        linkSpeed = (bandwidth == WIFI_BW_HT40) ? 574 : 287;  // WiFi 6 estimates
    } else if (wifiInfo.phy_11n) {
        linkSpeed = (bandwidth == WIFI_BW_HT40) ? 300 : 150;
    }

    // Build JSON response with ALL parameters
    Serial.print("{");
    Serial.print("\"status\":\"connected\"");
    
    // Device name (if set)
    if (deviceName.length() > 0) {
        Serial.print(",\"device_name\":\""); Serial.print(deviceName); Serial.print("\"");
    }
    
    // Network identification
    Serial.print(",\"ssid\":\""); Serial.print(WiFi.SSID()); Serial.print("\"");
    Serial.print(",\"bssid\":\""); Serial.print(WiFi.BSSIDstr()); Serial.print("\"");
    Serial.print(",\"ip\":\""); Serial.print(WiFi.localIP().toString()); Serial.print("\"");
    Serial.print(",\"gateway\":\""); Serial.print(WiFi.gatewayIP().toString()); Serial.print("\"");
    Serial.print(",\"subnet\":\""); Serial.print(WiFi.subnetMask().toString()); Serial.print("\"");
    Serial.print(",\"dns\":\""); Serial.print(WiFi.dnsIP().toString()); Serial.print("\"");
    Serial.print(",\"mac\":\""); Serial.print(WiFi.macAddress()); Serial.print("\"");

    // Channel info
    Serial.print(",\"channel\":"); Serial.print(wifiInfo.primary);
    Serial.print(",\"secondary_channel\":"); Serial.print(wifiInfo.second);

    // Signal quality
    Serial.print(",\"rssi\":"); Serial.print(WiFi.RSSI());
    Serial.print(",\"noise_floor\":"); Serial.print(noiseFloor);
    Serial.print(",\"snr\":"); Serial.print(snr);
    
    // TX power (in 0.25 dBm units, convert to dBm)
    Serial.print(",\"tx_power\":"); Serial.print(txPower / 4.0, 1);

    // PHY layer info
    Serial.print(",\"phy_mode\":\""); Serial.print(phyMode); Serial.print("\"");
    Serial.print(",\"phy_11b\":"); Serial.print(wifiInfo.phy_11b ? "true" : "false");
    Serial.print(",\"phy_11g\":"); Serial.print(wifiInfo.phy_11g ? "true" : "false");
    Serial.print(",\"phy_11n\":"); Serial.print(wifiInfo.phy_11n ? "true" : "false");
    Serial.print(",\"phy_11ax\":"); Serial.print(wifiInfo.phy_11ax ? "true" : "false");
    Serial.print(",\"phy_lr\":"); Serial.print(wifiInfo.phy_lr ? "true" : "false");

    // Bandwidth and speed
    Serial.print(",\"bandwidth\":\""); Serial.print(bwStr); Serial.print("\"");
    Serial.print(",\"link_speed\":"); Serial.print(linkSpeed);

    // Security
    Serial.print(",\"auth_mode\":\""); Serial.print(authMode); Serial.print("\"");
    Serial.print(",\"cipher\":\""); Serial.print(cipher); Serial.print("\"");

    // Country code
    wifi_country_t country;
    if (esp_wifi_get_country(&country) == ESP_OK) {
        Serial.print(",\"country\":\"");
        Serial.print(country.cc[0]); Serial.print(country.cc[1]);
        Serial.print("\"");
        Serial.print(",\"max_tx_power_country\":"); Serial.print(country.max_tx_power);
    }

    // HE (WiFi 6) capabilities if available
    Serial.print(",\"wifi6_supported\":"); Serial.print(wifiInfo.phy_11ax ? "true" : "false");
    Serial.print(",\"ftm_responder\":"); Serial.print(wifiInfo.ftm_responder ? "true" : "false");
    Serial.print(",\"ftm_initiator\":"); Serial.print(wifiInfo.ftm_initiator ? "true" : "false");

    // Packet statistics
    Serial.print(",\"tx_packets\":"); Serial.print(txPackets);
    Serial.print(",\"rx_packets\":"); Serial.print(rxPackets);
    Serial.print(",\"tx_bytes\":"); Serial.print(txBytes);
    Serial.print(",\"rx_bytes\":"); Serial.print(rxBytes);
    Serial.print(",\"tx_errors\":"); Serial.print(txErrors);
    Serial.print(",\"rx_errors\":"); Serial.print(rxErrors);
    Serial.print(",\"tx_retries\":"); Serial.print(txRetries);
    Serial.print(",\"connection_attempts\":"); Serial.print(connectionAttempts);

    // Latency
    if (latencyCount > 0) {
        float jitter = latencyMax - latencyMin;
        Serial.print(",\"latency_min\":"); Serial.print(latencyMin, 2);
        Serial.print(",\"latency_avg\":"); Serial.print(latencyAvg, 2);
        Serial.print(",\"latency_max\":"); Serial.print(latencyMax, 2);
        Serial.print(",\"jitter\":"); Serial.print(jitter, 2);
        Serial.print(",\"latency_samples\":"); Serial.print(latencyCount);
    }

    // System info
    Serial.print(",\"free_heap\":"); Serial.print(ESP.getFreeHeap());
    Serial.print(",\"min_free_heap\":"); Serial.print(ESP.getMinFreeHeap());
    Serial.print(",\"heap_size\":"); Serial.print(ESP.getHeapSize());
    Serial.print(",\"uptime\":"); Serial.print(millis() / 1000);
    Serial.print(",\"uptime_ms\":"); Serial.print(millis());
    Serial.print(",\"cpu_freq\":"); Serial.print(ESP.getCpuFreqMHz());
    Serial.print(",\"chip_model\":\""); Serial.print(ESP.getChipModel()); Serial.print("\"");
    Serial.print(",\"chip_revision\":"); Serial.print(ESP.getChipRevision());
    Serial.print(",\"sdk_version\":\""); Serial.print(ESP.getSdkVersion()); Serial.print("\"");

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
