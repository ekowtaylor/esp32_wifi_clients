"""
ESP32 WiFi Performance Monitor CLI

Command-line interface for monitoring WiFi performance from ESP32 devices.
"""

import argparse
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from .device import ESP32Device
from .live_view import LiveDisplay, SimpleDisplay
from .logger import LogAnalyzer, PerformanceLogger
from .manager import ESP32Manager
from .performance import PerformanceMonitor


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="ESP32 WiFi Performance Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-discover and monitor all ESP32 devices
  esp32-wifi-monitor

  # Monitor specific ports
  esp32-wifi-monitor -p /dev/ttyUSB0 /dev/ttyUSB1

  # Monitor with logging to CSV
  esp32-wifi-monitor -l -f csv -o ./logs

  # Trigger a speed test on all devices
  esp32-wifi-monitor --speed-test

  # Analyze previously logged data
  esp32-wifi-monitor --analyze logs/wifi_perf_20240101_120000.jsonl
        """,
    )

    # Device selection
    device_group = parser.add_argument_group("Device Options")
    device_group.add_argument(
        "-p",
        "--ports",
        nargs="+",
        help="Specific serial ports to connect to (e.g., /dev/ttyUSB0 COM3)",
    )
    device_group.add_argument(
        "-b",
        "--baud-rate",
        type=int,
        default=115200,
        help="Serial baud rate (default: 115200)",
    )
    device_group.add_argument(
        "--list-devices",
        action="store_true",
        help="List discovered ESP32 devices and exit",
    )

    # Display options
    display_group = parser.add_argument_group("Display Options")
    display_group.add_argument(
        "-c",
        "--compact",
        action="store_true",
        help="Use compact single-line display mode",
    )
    display_group.add_argument(
        "--no-graphs",
        action="store_true",
        help="Disable RSSI history graphs",
    )
    display_group.add_argument(
        "--simple",
        action="store_true",
        help="Simple line-by-line output (for piping)",
    )
    display_group.add_argument(
        "-r",
        "--refresh-rate",
        type=float,
        default=0.5,
        help="Display refresh rate in seconds (default: 0.5)",
    )

    # Logging options
    log_group = parser.add_argument_group("Logging Options")
    log_group.add_argument(
        "-l",
        "--log",
        action="store_true",
        help="Enable logging to file",
    )
    log_group.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default="logs",
        help="Log output directory (default: logs)",
    )
    log_group.add_argument(
        "-f",
        "--format",
        choices=["jsonl", "csv", "log"],
        default="jsonl",
        help="Log file format (default: jsonl)",
    )
    log_group.add_argument(
        "--separate-logs",
        action="store_true",
        help="Create separate log files per device",
    )
    log_group.add_argument(
        "--max-size",
        type=float,
        default=100.0,
        help="Max log file size in MB before rotation (default: 100)",
    )

    # Commands
    cmd_group = parser.add_argument_group("Commands")
    cmd_group.add_argument(
        "--speed-test",
        action="store_true",
        help="Trigger speed test on all devices",
    )
    cmd_group.add_argument(
        "--report",
        action="store_true",
        help="Request single performance report and exit",
    )
    cmd_group.add_argument(
        "--continuous",
        action="store_true",
        help="Enable continuous reporting on devices",
    )
    cmd_group.add_argument(
        "--interval",
        type=int,
        default=1000,
        help="Reporting interval in ms for continuous mode (default: 1000)",
    )
    cmd_group.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Run duration in seconds (0 = indefinite, default: 0)",
    )

    # Analysis
    analysis_group = parser.add_argument_group("Analysis")
    analysis_group.add_argument(
        "--analyze",
        type=str,
        metavar="FILE",
        help="Analyze a log file and print statistics",
    )
    analysis_group.add_argument(
        "--export-summary",
        type=str,
        metavar="FILE",
        help="Export summary report to file",
    )

    return parser.parse_args()


def list_devices():
    """List all discovered ESP32 devices."""
    print("Scanning for ESP32 devices...")
    devices = ESP32Device.discover_devices()

    if not devices:
        print("No ESP32 devices found.")
        return

    print(f"\nFound {len(devices)} device(s):\n")
    print(
        f"{'Port':<20} {'Device ID':<15} {'VID:PID':<12} {'Manufacturer':<20} {'Description'}"
    )
    print("-" * 90)

    for dev in devices:
        vid_pid = f"{dev.vid:04X}:{dev.pid:04X}" if dev.vid and dev.pid else "N/A"
        mfr = (dev.manufacturer or "N/A")[:20]
        desc = dev.description or "N/A"
        print(f"{dev.port:<20} {dev.device_id:<15} {vid_pid:<12} {mfr:<20} {desc}")


def analyze_log(filepath: str, export_path: Optional[str] = None):
    """Analyze a log file and print statistics."""
    filepath = Path(filepath)

    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    print(f"Analyzing: {filepath}\n")

    # Load data based on format
    if filepath.suffix in (".jsonl", ".gz") and ".jsonl" in filepath.name:
        data = LogAnalyzer.load_jsonl(filepath)
    elif filepath.suffix in (".csv", ".gz") and ".csv" in filepath.name:
        data = LogAnalyzer.load_csv(filepath)
    else:
        print(f"Error: Unsupported file format. Use .jsonl or .csv files.")
        sys.exit(1)

    if not data:
        print("No data found in file.")
        return

    # Calculate and display statistics
    stats = LogAnalyzer.calculate_statistics(data)

    print(f"Total Entries: {stats.get('total_entries', 0)}")
    print(f"Devices: {', '.join(stats.get('devices', []))}")

    if "time_range" in stats:
        tr = stats["time_range"]
        print(f"\nTime Range:")
        print(f"  Start: {tr['start']}")
        print(f"  End: {tr['end']}")
        print(f"  Duration: {tr['duration_seconds']:.0f} seconds")

    if "rssi" in stats:
        r = stats["rssi"]
        print(f"\nRSSI Statistics:")
        print(f"  Min: {r['min']} dBm")
        print(f"  Max: {r['max']} dBm")
        print(f"  Avg: {r['avg']:.1f} dBm")

    if "latency" in stats:
        l = stats["latency"]
        print(f"\nLatency Statistics:")
        print(f"  Min: {l['min']:.1f} ms")
        print(f"  Max: {l['max']:.1f} ms")
        print(f"  Avg: {l['avg']:.1f} ms")

    if "packet_loss" in stats:
        p = stats["packet_loss"]
        print(f"\nPacket Loss Statistics:")
        print(f"  Min: {p['min']:.2f}%")
        print(f"  Max: {p['max']:.2f}%")
        print(f"  Avg: {p['avg']:.2f}%")

    if "download_speed" in stats:
        d = stats["download_speed"]
        print(f"\nDownload Speed Statistics:")
        print(f"  Min: {d['min']:.2f} Mbps")
        print(f"  Max: {d['max']:.2f} Mbps")
        print(f"  Avg: {d['avg']:.2f} Mbps")

    # Export if requested
    if export_path:
        export_format = "json" if export_path.endswith(".json") else "text"
        LogAnalyzer.export_summary(data, export_path, format=export_format)
        print(f"\nSummary exported to: {export_path}")


def run_monitor(args):
    """Run the main monitoring loop."""
    # Initialize components
    manager = ESP32Manager(auto_reconnect=True)
    monitor = PerformanceMonitor()
    logger = None
    display = None

    # Setup signal handlers
    running = True

    def signal_handler(sig, frame):
        nonlocal running
        print("\n\nShutting down...")
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Connect to devices
        if args.ports:
            # Connect to specific ports
            for port in args.ports:
                device_id = manager.add_device(port, baud_rate=args.baud_rate)
                if device_id:
                    print(f"Connected to {port} as {device_id}")
                else:
                    print(f"Failed to connect to {port}")
        else:
            # Auto-discover
            print("Discovering ESP32 devices...")
            connected = manager.discover_and_connect(baud_rate=args.baud_rate)
            if connected:
                print(
                    f"Connected to {len(connected)} device(s): {', '.join(connected)}"
                )
            else:
                print("No ESP32 devices found.")
                sys.exit(1)

        # Setup logger if enabled
        if args.log:
            logger = PerformanceLogger(
                output_dir=args.output_dir,
                file_format=args.format,
                separate_devices=args.separate_logs,
                max_file_size_mb=args.max_size,
            )
            print(f"Logging to: {args.output_dir}/ (format: {args.format})")

        # Setup display
        if args.simple:
            simple_display = SimpleDisplay()
            display_callback = simple_display.display
        else:
            display = LiveDisplay(
                refresh_rate=args.refresh_rate,
                show_graphs=not args.no_graphs,
                compact_mode=args.compact,
            )
            display_callback = display.update

        # Setup data pipeline
        def on_data(device_id: str, line: str):
            perf_data = monitor.process_line(device_id, line)
            if perf_data:
                display_callback(perf_data)
                if logger:
                    logger.log(perf_data)

        manager.add_global_callback(on_data)

        # Handle one-shot commands
        if args.report:
            manager.trigger_all_performance_reports()
            time.sleep(2)  # Wait for responses
            return

        if args.speed_test:
            print("Triggering speed tests on all devices...")
            manager.trigger_all_speed_tests()

        # Enable continuous reporting if requested
        if args.continuous:
            manager.enable_all_continuous_reporting(True, args.interval)

        # Start reading from all devices
        manager.start_reading_all()

        # Start display
        if display:
            display.start()

        # Calculate end time if duration specified
        end_time = None
        if args.duration > 0:
            end_time = time.time() + args.duration

        # Main loop
        while running:
            if end_time and time.time() >= end_time:
                print(f"\nDuration of {args.duration}s reached.")
                break
            time.sleep(0.1)

    finally:
        # Cleanup
        if display:
            display.stop()

        if logger:
            print(f"\nLogged {logger.entry_count} entries.")
            logger.close()

        manager.disconnect_all()
        print("Disconnected from all devices.")


def main():
    """Main entry point."""
    args = parse_args()

    # Handle special modes
    if args.list_devices:
        list_devices()
        return

    if args.analyze:
        analyze_log(args.analyze, args.export_summary)
        return

    # Run main monitor
    run_monitor(args)


if __name__ == "__main__":
    main()
