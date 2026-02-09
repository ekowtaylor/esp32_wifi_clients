# ESP32 WiFi Performance Monitor

A Python wrapper to connect to and read WiFi performance data from multiple ESP32 devices connected directly to a host via USB. Monitor performance live and/or collect data to logs for analysis.

## Features

- **Multi-device Support**: Connect to N number of ESP32s simultaneously
- **Auto-discovery**: Automatically detect ESP32 devices connected via USB
- **Live Monitoring**: Real-time terminal display with ASCII graphs
- **Data Logging**: Log to JSON Lines, CSV, or plain text formats
- **Performance Metrics**:
  - Signal strength (RSSI, SNR)
  - Latency (min/avg/max, jitter)
  - Throughput (TX/RX rates)
  - Packet statistics (errors, retries, loss)
  - Speed test results
- **Flexible Data Format**: Supports JSON, key-value, and pipe-delimited formats from devices
- **Analysis Tools**: Built-in log analysis and statistics

## Installation

### From Source

```bash
cd esp32_wifi_clients
pip install -e .
```

### Requirements

- Python 3.9+
- pyserial

```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Flash ESP32 Firmware

Upload the provided Arduino sketch to your ESP32 devices:

1. Open `firmware/esp32_wifi_reporter/esp32_wifi_reporter.ino` in Arduino IDE
2. Update `WIFI_SSID` and `WIFI_PASSWORD` with your WiFi credentials
3. Select your ESP32 board and port
4. Upload the sketch

### 2. Run the Monitor

```bash
# Auto-discover and monitor all connected ESP32s
esp32-wifi-monitor

# Monitor specific ports
esp32-wifi-monitor -p /dev/ttyUSB0 /dev/ttyUSB1

# List discovered devices
esp32-wifi-monitor --list-devices
```

## Usage

### CLI Commands

```bash
# Basic monitoring
esp32-wifi-monitor

# Enable logging to CSV files
esp32-wifi-monitor -l -f csv -o ./logs

# Compact display mode
esp32-wifi-monitor -c

# Simple output for piping
esp32-wifi-monitor --simple > output.log

# Trigger speed test on all devices
esp32-wifi-monitor --speed-test

# Enable continuous reporting from devices
esp32-wifi-monitor --continuous --interval 500

# Run for specific duration
esp32-wifi-monitor -l --duration 3600  # 1 hour

# Analyze logged data
esp32-wifi-monitor --analyze logs/wifi_perf_20240101_120000.jsonl

# Export summary report
esp32-wifi-monitor --analyze logs/data.jsonl --export-summary report.json
```

### Python API

```python
from esp32_wifi import ESP32Manager, PerformanceMonitor, PerformanceLogger, LiveDisplay

# Create manager and connect to devices
manager = ESP32Manager()
manager.discover_and_connect()

# Set up performance monitoring
monitor = PerformanceMonitor()
logger = PerformanceLogger(output_dir="logs", file_format="csv")
display = LiveDisplay()

# Define callback for data processing
def on_data(device_id, line):
    data = monitor.process_line(device_id, line)
    if data:
        display.update(data)
        logger.log(data)

# Register callback and start
manager.add_global_callback(on_data)
manager.start_reading_all()
display.start()

# Trigger commands
manager.trigger_all_performance_reports()
manager.trigger_all_speed_tests()
manager.enable_all_continuous_reporting(True, interval_ms=1000)

# Run until interrupted
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    display.stop()
    logger.close()
    manager.disconnect_all()
```

### Direct Device Access

```python
from esp32_wifi import ESP32Device

# Discover available devices
devices = ESP32Device.discover_devices()
for dev in devices:
    print(f"{dev.port}: {dev.device_id} ({dev.manufacturer})")

# Connect to a specific device
device = ESP32Device("/dev/ttyUSB0", device_id="esp32_01")
device.connect()

# Add callback for data
device.add_callback(lambda dev_id, line: print(f"[{dev_id}] {line}"))
device.start_reading()

# Send commands
device.trigger_performance_report()
device.trigger_speed_test()
device.set_report_interval(500)  # 500ms
device.enable_continuous_reporting(True)

# Cleanup
device.disconnect()
```

### Analyzing Logs

```python
from esp32_wifi.logger import LogAnalyzer

# Load data
data = LogAnalyzer.load_jsonl("logs/wifi_perf_20240101_120000.jsonl")

# Calculate statistics
stats = LogAnalyzer.calculate_statistics(data)
print(f"RSSI avg: {stats['rssi']['avg']:.1f} dBm")
print(f"Latency avg: {stats['latency']['avg']:.1f} ms")

# Per-device statistics
for device_id in stats['devices']:
    device_stats = LogAnalyzer.calculate_statistics(data, device_id=device_id)
    print(f"\n{device_id}:")
    print(f"  Entries: {device_stats['total_entries']}")

# Export summary
LogAnalyzer.export_summary(data, "report.json", format="json")
```

## ESP32 Data Format

The parser supports multiple data formats from ESP32 devices:

### JSON Format (Recommended)

```json
{"rssi":-45,"ssid":"MyNetwork","channel":6,"latency_avg":12.5,"packet_loss":0.1}
```

### Pipe-Delimited Format

```
PERF|rssi:-45|ssid:MyNetwork|channel:6|latency:12.5|loss:0.1
```

### Key-Value Format

```
rssi=-45, ssid=MyNetwork, channel=6, latency=12.5, loss=0.1
```

### Supported Fields

| Field | Description | Unit |
|-------|-------------|------|
| `rssi` | Signal strength | dBm |
| `ssid` | Network name | - |
| `bssid` | Access point MAC | - |
| `channel` | WiFi channel | - |
| `snr` | Signal-to-noise ratio | dB |
| `tx_rate` / `rx_rate` | Throughput | Kbps |
| `link_speed` | PHY link speed | Mbps |
| `tx_packets` / `rx_packets` | Packet counts | - |
| `tx_bytes` / `rx_bytes` | Byte counts | bytes |
| `tx_errors` / `rx_errors` | Error counts | - |
| `tx_retries` | Retry count | - |
| `packet_loss` | Loss percentage | % |
| `latency_min/avg/max` | Latency | ms |
| `jitter` | Latency variance | ms |
| `download_speed` | Download speed | Mbps |
| `upload_speed` | Upload speed | Mbps |
| `free_heap` | Available memory | bytes |
| `uptime` | Time since boot | seconds |

## ESP32 Commands

Commands sent to ESP32 devices over serial:

| Command | Description |
|---------|-------------|
| `PERF_REPORT` | Request single performance report |
| `SPEED_TEST` | Trigger download speed test |
| `SET_INTERVAL:X` | Set reporting interval (milliseconds) |
| `CONTINUOUS:ON` | Enable continuous reporting |
| `CONTINUOUS:OFF` | Disable continuous reporting |

## Project Structure

```
esp32_wifi_clients/
├── esp32_wifi/
│   ├── __init__.py       # Package exports
│   ├── device.py         # ESP32Device - single device handling
│   ├── manager.py        # ESP32Manager - multi-device management
│   ├── performance.py    # Data models and parsing
│   ├── logger.py         # Logging and analysis
│   ├── live_view.py      # Terminal display
│   └── cli.py            # Command-line interface
├── firmware/
│   └── esp32_wifi_reporter/
│       └── esp32_wifi_reporter.ino  # ESP32 Arduino sketch
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Supported ESP32 Boards

The tool auto-detects boards with these USB-Serial chips:

- **Silicon Labs CP210x** (ESP32-DevKitC, NodeMCU-32S)
- **CH340/CH9102** (Various ESP32 dev boards)
- **FTDI FT232/FT231X** (Some ESP32 modules)
- **ESP32-S2/S3 Native USB** (Built-in USB support)

## License

MIT License
