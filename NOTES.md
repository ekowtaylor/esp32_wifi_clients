# Developer Notes

Notes and gotchas for extending this ESP32 WiFi Performance Monitor.

## ESP32 Chip Variants

Different ESP32 chips require different board configurations:

| Chip | VID:PID | FQBN | Notes |
|------|---------|------|-------|
| ESP32-S2 | 0x303A:0x1001 | `esp32:esp32:esp32s2` | Native USB |
| ESP32-S3 | 0x303A:0x0002 | `esp32:esp32:esp32s3` | Native USB |
| ESP32-C5 | 0x303A:0x1001 | `esp32:esp32:esp32c5` | WiFi 6, requires CDC enabled |
| ESP32 (classic) | 0x10C4:0xEA60 | `esp32:esp32:esp32` | CP210x USB-UART |
| ESP32-C3 | varies | `esp32:esp32:esp32c3` | RISC-V based |

### USB CDC On Boot (Critical for S2/S3/C5)

Chips with native USB **require** `CDCOnBoot=cdc` to output Serial over USB:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c5:CDCOnBoot=cdc firmware/esp32_wifi_reporter
```

Without this flag, Serial output won't appear over USB—you'll only see boot ROM messages.

## Firmware Compilation

### Prerequisites

```bash
# Install Arduino CLI
brew install arduino-cli

# Add ESP32 board manager
arduino-cli config init
arduino-cli config add board_manager.additional_urls \
  https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json

# Install ESP32 core
arduino-cli core update-index
arduino-cli core install esp32:esp32
```

### Common Build Errors

1. **`he_ap` is a struct, not bool** (ESP32 Arduino 3.x)
   - In newer ESP-IDF, `wifi_ap_record_t.he_ap` is a `wifi_he_ap_info_t` struct, not a boolean
   - Use `wifiInfo.phy_11ax` for WiFi 6 capability instead

2. **Missing serial output after flash**
   - Usually means USB CDC not enabled
   - Add `:CDCOnBoot=cdc` to FQBN

3. **Wrong chip detected during upload**
   - esptool auto-detects; if it says "This chip is ESP32-C5, not ESP32-S2", update your FQBN

## WiFi API Notes

### Available Signal Parameters

From `esp_wifi_sta_get_ap_info()`:

```c
wifi_ap_record_t wifiInfo;
esp_wifi_sta_get_ap_info(&wifiInfo);

// Primary fields
wifiInfo.primary          // Primary channel
wifiInfo.second           // Secondary channel (0 = none, 1 = above, 2 = below)
wifiInfo.rssi             // Signal strength in dBm
wifiInfo.authmode         // Authentication mode enum
wifiInfo.pairwise_cipher  // Cipher type enum

// PHY capabilities (booleans)
wifiInfo.phy_11b          // 802.11b supported
wifiInfo.phy_11g          // 802.11g supported  
wifiInfo.phy_11n          // 802.11n (WiFi 4) supported
wifiInfo.phy_11ax         // 802.11ax (WiFi 6) supported
wifiInfo.phy_lr           // Long Range mode

// FTM (Fine Timing Measurement) for location
wifiInfo.ftm_responder    // AP supports FTM responder
wifiInfo.ftm_initiator    // AP supports FTM initiator
```

### TX Power

TX power is returned in 0.25 dBm units:

```c
int8_t txPower;
esp_wifi_get_max_tx_power(&txPower);
float txPowerDbm = txPower / 4.0;  // Convert to dBm
```

### Bandwidth

```c
wifi_bandwidth_t bandwidth;
esp_wifi_get_bandwidth(WIFI_IF_STA, &bandwidth);
// WIFI_BW_HT20 = 20MHz
// WIFI_BW_HT40 = 40MHz
```

### Noise Floor Estimation

ESP32 doesn't provide direct noise floor measurement. Common approximations:
- 2.4 GHz typical: -95 to -90 dBm
- 5 GHz typical: -95 to -92 dBm

SNR can be estimated as: `SNR = RSSI - noise_floor`

## Python Package

### Device Discovery

The `ESP32Device.discover_devices()` method matches devices by USB VID/PID pairs defined in `KNOWN_ESP32_DEVICES`. Add new chips there:

```python
KNOWN_ESP32_DEVICES = [
    (0x10C4, 0xEA60),  # Silicon Labs CP210x
    (0x1A86, 0x7523),  # CH340
    (0x303A, 0x1001),  # ESP32-S2/C5 native USB
    # Add new devices here
]
```

### Data Parsing

`PerformanceParser` in `performance.py` supports:
- JSON format (preferred)
- Key-value (`KEY:VALUE` or `KEY=VALUE`)
- CSV format

The firmware outputs JSON, but the parser is flexible for custom firmware.

### Callback System

Both `ESP32Device` and `ESP32Manager` use callbacks for data:

```python
def my_callback(device_id: str, data: str):
    print(f"{device_id}: {data}")

device.add_callback(my_callback)
# or for all devices:
manager.add_global_callback(my_callback)
```

## Common Gotchas

### 1. Serial Port Naming (macOS)

macOS creates two ports for USB serial devices:
- `/dev/cu.*` - Calling unit (use this one)
- `/dev/tty.*` - Terminal (can block)

Always use `/dev/cu.*` for programmatic access.

### 2. Serial Buffer Overflow

ESP32 outputs can be fast. If you see truncated JSON, increase read frequency or buffer size:

```python
ser = serial.Serial(port, 115200, timeout=0.1)
while ser.in_waiting:
    # Read frequently to prevent overflow
```

### 3. WiFi Connection Timing

After flashing, the ESP32 needs time to:
1. Boot (~1-2 seconds)
2. Connect to WiFi (~3-5 seconds for new connection)
3. Get IP via DHCP (~1-2 seconds)

Wait at least 5 seconds after reset before expecting valid readings.

### 4. DTR/RTS Reset

To reset ESP32 programmatically via serial:

```python
ser.dtr = False
ser.rts = True
time.sleep(0.1)
ser.rts = False
```

This toggles the EN (enable) pin through the USB-UART bridge.

### 5. Latency Measurement

The firmware measures latency by attempting TCP connections to the gateway. If the gateway doesn't accept connections on port 80 (common for home routers), latency won't be recorded. Consider:
- Using ICMP ping (requires raw sockets)
- Connecting to an external server
- Using mDNS or other local services

## Extending the Firmware

### Adding New Commands

In `processCommand()`:

```c
else if (cmd == "MY_COMMAND") {
    // Your code here
    Serial.println("{\"event\":\"my_response\",\"data\":123}");
}
```

### Adding New Metrics

1. Add variable to store the metric
2. Collect data in `loop()` or a separate function
3. Add to JSON output in `sendPerformanceReport()`
4. Update `WiFiPerformanceData` dataclass in Python
5. Update `PerformanceParser` if using non-JSON format

### Continuous Reporting

Enable server-push mode:

```bash
echo "SET_INTERVAL:500" > /dev/cu.usbmodem1101
echo "CONTINUOUS:ON" > /dev/cu.usbmodem1101
```

## Testing

### Quick Serial Test

```bash
# Using Python
python3 -c "
import serial, time
ser = serial.Serial('/dev/cu.usbmodem1101', 115200, timeout=2)
time.sleep(0.5)
ser.write(b'PERF_REPORT\n')
time.sleep(1)
while ser.in_waiting:
    print(ser.readline().decode().strip())
ser.close()
"

# Using Arduino CLI monitor
arduino-cli monitor -p /dev/cu.usbmodem1101 -c baudrate=115200
```

### Running the Full Monitor

```bash
cd esp32_wifi_clients
pip install -e .
esp32-wifi-monitor -p /dev/cu.usbmodem1101
```

## Resources

- [ESP-IDF WiFi API Reference](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/network/esp_wifi.html)
- [Arduino-ESP32 WiFi Library](https://github.com/espressif/arduino-esp32/tree/master/libraries/WiFi)
- [ESP32-C5 Datasheet](https://www.espressif.com/en/products/socs/esp32-c5) (WiFi 6 support)
