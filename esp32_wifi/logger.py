"""
Performance Data Logger

Provides logging capabilities for WiFi performance data analysis.
"""

import csv
import gzip
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO, Union

from .performance import WiFiPerformanceData


class PerformanceLogger:
    """
    Logs WiFi performance data to files for later analysis.

    Supports multiple output formats:
    - JSON Lines (.jsonl)
    - CSV (.csv)
    - Plain text (.log)

    Features:
    - Automatic file rotation by size or time
    - Gzip compression for archived logs
    - Per-device or combined logging
    """

    def __init__(
        self,
        output_dir: Union[str, Path] = "logs",
        file_format: str = "jsonl",
        separate_devices: bool = False,
        max_file_size_mb: float = 100.0,
        rotate_interval_hours: Optional[float] = None,
        compress_rotated: bool = True,
    ):
        """
        Initialize the performance logger.

        Args:
            output_dir: Directory for log files.
            file_format: Output format ('jsonl', 'csv', or 'log').
            separate_devices: Create separate files per device.
            max_file_size_mb: Rotate files when they reach this size.
            rotate_interval_hours: Rotate files after this many hours.
            compress_rotated: Gzip compress rotated files.
        """
        self.output_dir = Path(output_dir)
        self.file_format = file_format.lower()
        self.separate_devices = separate_devices
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.rotate_interval_hours = rotate_interval_hours
        self.compress_rotated = compress_rotated

        self._files: Dict[str, TextIO] = {}
        self._file_paths: Dict[str, Path] = {}
        self._file_start_times: Dict[str, datetime] = {}
        self._csv_writers: Dict[str, csv.DictWriter] = {}
        self._lock = threading.Lock()
        self._entry_count = 0

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def log(self, data: WiFiPerformanceData) -> None:
        """
        Log a performance data point.

        Args:
            data: Performance data to log.
        """
        with self._lock:
            file_key = data.device_id if self.separate_devices else "_combined"

            # Check if we need to rotate
            self._check_rotation(file_key)

            # Get or create file handle
            if file_key not in self._files:
                self._open_file(file_key)

            # Write data in appropriate format
            if self.file_format == "jsonl":
                self._write_jsonl(file_key, data)
            elif self.file_format == "csv":
                self._write_csv(file_key, data)
            else:
                self._write_text(file_key, data)

            self._entry_count += 1

    def _generate_filename(self, file_key: str) -> str:
        """Generate a filename with timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if file_key == "_combined":
            base = f"wifi_perf_{timestamp}"
        else:
            base = f"wifi_perf_{file_key}_{timestamp}"

        return f"{base}.{self.file_format}"

    def _open_file(self, file_key: str) -> None:
        """Open a new log file."""
        filename = self._generate_filename(file_key)
        filepath = self.output_dir / filename

        self._file_paths[file_key] = filepath
        self._file_start_times[file_key] = datetime.now()

        if self.file_format == "csv":
            self._files[file_key] = open(filepath, "w", newline="", encoding="utf-8")
            self._csv_writers[file_key] = None  # Will be created on first write
        else:
            self._files[file_key] = open(filepath, "w", encoding="utf-8")

    def _check_rotation(self, file_key: str) -> None:
        """Check if file rotation is needed."""
        if file_key not in self._files:
            return

        should_rotate = False

        # Check size
        filepath = self._file_paths[file_key]
        if filepath.exists() and filepath.stat().st_size >= self.max_file_size_bytes:
            should_rotate = True

        # Check time
        if self.rotate_interval_hours:
            start_time = self._file_start_times.get(file_key)
            if start_time:
                hours_elapsed = (datetime.now() - start_time).total_seconds() / 3600
                if hours_elapsed >= self.rotate_interval_hours:
                    should_rotate = True

        if should_rotate:
            self._rotate_file(file_key)

    def _rotate_file(self, file_key: str) -> None:
        """Rotate a log file."""
        if file_key in self._files:
            self._files[file_key].close()
            del self._files[file_key]

            if file_key in self._csv_writers:
                del self._csv_writers[file_key]

            # Compress old file if enabled
            if self.compress_rotated:
                old_path = self._file_paths[file_key]
                if old_path.exists():
                    self._compress_file(old_path)

    def _compress_file(self, filepath: Path) -> None:
        """Compress a file using gzip."""
        gz_path = filepath.with_suffix(filepath.suffix + ".gz")

        with open(filepath, "rb") as f_in:
            with gzip.open(gz_path, "wb") as f_out:
                f_out.writelines(f_in)

        filepath.unlink()  # Remove original

    def _write_jsonl(self, file_key: str, data: WiFiPerformanceData) -> None:
        """Write data in JSON Lines format."""
        f = self._files[file_key]
        json.dump(data.to_dict(), f)
        f.write("\n")
        f.flush()

    def _write_csv(self, file_key: str, data: WiFiPerformanceData) -> None:
        """Write data in CSV format."""
        f = self._files[file_key]
        data_dict = data.to_dict()

        # Create writer with header on first write
        if self._csv_writers.get(file_key) is None:
            self._csv_writers[file_key] = csv.DictWriter(
                f,
                fieldnames=list(data_dict.keys()),
                extrasaction="ignore",
            )
            self._csv_writers[file_key].writeheader()

        self._csv_writers[file_key].writerow(data_dict)
        f.flush()

    def _write_text(self, file_key: str, data: WiFiPerformanceData) -> None:
        """Write data in plain text format."""
        f = self._files[file_key]

        timestamp = data.datetime.strftime("%Y-%m-%d %H:%M:%S")
        parts = [timestamp, f"[{data.device_id}]"]

        if data.ssid:
            parts.append(f"SSID:{data.ssid}")
        if data.rssi is not None:
            parts.append(f"RSSI:{data.rssi}dBm")
        if data.latency_avg is not None:
            parts.append(f"Latency:{data.latency_avg:.1f}ms")
        if data.packet_loss is not None:
            parts.append(f"Loss:{data.packet_loss:.1f}%")
        if data.tx_rate is not None:
            parts.append(f"TX:{data.tx_rate:.0f}Kbps")
        if data.rx_rate is not None:
            parts.append(f"RX:{data.rx_rate:.0f}Kbps")
        if data.download_speed is not None:
            parts.append(f"DL:{data.download_speed:.2f}Mbps")
        if data.upload_speed is not None:
            parts.append(f"UL:{data.upload_speed:.2f}Mbps")

        f.write(" | ".join(parts) + "\n")
        f.flush()

    def flush(self) -> None:
        """Flush all open log files."""
        with self._lock:
            for f in self._files.values():
                f.flush()

    def close(self) -> None:
        """Close all log files."""
        with self._lock:
            for f in self._files.values():
                f.close()
            self._files.clear()
            self._csv_writers.clear()

    def get_log_files(self) -> List[Path]:
        """Get list of all log files in the output directory."""
        patterns = [f"*.{self.file_format}", f"*.{self.file_format}.gz"]
        files = []
        for pattern in patterns:
            files.extend(self.output_dir.glob(pattern))
        return sorted(files)

    @property
    def entry_count(self) -> int:
        """Number of entries logged."""
        return self._entry_count

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


class LogAnalyzer:
    """
    Analyzes logged WiFi performance data.
    """

    @staticmethod
    def load_jsonl(filepath: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        Load data from a JSONL file.

        Args:
            filepath: Path to the JSONL file.

        Returns:
            List of data dictionaries.
        """
        filepath = Path(filepath)
        data = []

        opener = gzip.open if filepath.suffix == ".gz" else open

        with opener(filepath, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data.append(json.loads(line))

        return data

    @staticmethod
    def load_csv(filepath: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        Load data from a CSV file.

        Args:
            filepath: Path to the CSV file.

        Returns:
            List of data dictionaries.
        """
        filepath = Path(filepath)
        data = []

        opener = gzip.open if filepath.suffix == ".gz" else open

        with opener(filepath, "rt", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric fields
                for key, value in row.items():
                    if value == "":
                        row[key] = None
                    elif key in (
                        "rssi",
                        "channel",
                        "tx_packets",
                        "rx_packets",
                        "tx_bytes",
                        "rx_bytes",
                        "tx_errors",
                        "rx_errors",
                        "tx_retries",
                        "free_heap",
                        "uptime",
                        "cpu_freq",
                        "noise_floor",
                        "link_speed",
                    ):
                        try:
                            row[key] = int(value) if value else None
                        except ValueError:
                            pass
                    elif key in (
                        "snr",
                        "tx_rate",
                        "rx_rate",
                        "packet_loss",
                        "latency_min",
                        "latency_avg",
                        "latency_max",
                        "jitter",
                        "download_speed",
                        "upload_speed",
                        "timestamp",
                    ):
                        try:
                            row[key] = float(value) if value else None
                        except ValueError:
                            pass
                data.append(row)

        return data

    @classmethod
    def calculate_statistics(
        cls,
        data: List[Dict[str, Any]],
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculate statistics from logged data.

        Args:
            data: List of data dictionaries.
            device_id: Filter by device ID (optional).

        Returns:
            Statistics dictionary.
        """
        if device_id:
            data = [d for d in data if d.get("device_id") == device_id]

        if not data:
            return {}

        stats = {
            "total_entries": len(data),
            "devices": list(set(d.get("device_id") for d in data)),
        }

        # Calculate RSSI stats
        rssi_values = [d["rssi"] for d in data if d.get("rssi") is not None]
        if rssi_values:
            stats["rssi"] = {
                "min": min(rssi_values),
                "max": max(rssi_values),
                "avg": sum(rssi_values) / len(rssi_values),
                "samples": len(rssi_values),
            }

        # Calculate latency stats
        latency_values = [
            d["latency_avg"] for d in data if d.get("latency_avg") is not None
        ]
        if latency_values:
            stats["latency"] = {
                "min": min(latency_values),
                "max": max(latency_values),
                "avg": sum(latency_values) / len(latency_values),
                "samples": len(latency_values),
            }

        # Calculate packet loss stats
        loss_values = [
            d["packet_loss"] for d in data if d.get("packet_loss") is not None
        ]
        if loss_values:
            stats["packet_loss"] = {
                "min": min(loss_values),
                "max": max(loss_values),
                "avg": sum(loss_values) / len(loss_values),
                "samples": len(loss_values),
            }

        # Calculate throughput stats
        dl_values = [
            d["download_speed"] for d in data if d.get("download_speed") is not None
        ]
        if dl_values:
            stats["download_speed"] = {
                "min": min(dl_values),
                "max": max(dl_values),
                "avg": sum(dl_values) / len(dl_values),
                "samples": len(dl_values),
            }

        ul_values = [
            d["upload_speed"] for d in data if d.get("upload_speed") is not None
        ]
        if ul_values:
            stats["upload_speed"] = {
                "min": min(ul_values),
                "max": max(ul_values),
                "avg": sum(ul_values) / len(ul_values),
                "samples": len(ul_values),
            }

        # Time range
        timestamps = [d["timestamp"] for d in data if d.get("timestamp")]
        if timestamps:
            stats["time_range"] = {
                "start": datetime.fromtimestamp(min(timestamps)).isoformat(),
                "end": datetime.fromtimestamp(max(timestamps)).isoformat(),
                "duration_seconds": max(timestamps) - min(timestamps),
            }

        return stats

    @classmethod
    def export_summary(
        cls,
        data: List[Dict[str, Any]],
        output_path: Union[str, Path],
        format: str = "json",
    ) -> None:
        """
        Export a summary report.

        Args:
            data: List of data dictionaries.
            output_path: Output file path.
            format: Output format ('json' or 'text').
        """
        output_path = Path(output_path)

        # Get unique devices
        devices = list(set(d.get("device_id") for d in data if d.get("device_id")))

        summary = {
            "generated_at": datetime.now().isoformat(),
            "overall": cls.calculate_statistics(data),
            "per_device": {
                device_id: cls.calculate_statistics(data, device_id)
                for device_id in devices
            },
        }

        if format == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("WiFi Performance Summary Report\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Generated: {summary['generated_at']}\n\n")

                overall = summary["overall"]
                f.write("Overall Statistics:\n")
                f.write(f"  Total Entries: {overall.get('total_entries', 0)}\n")
                f.write(f"  Devices: {', '.join(overall.get('devices', []))}\n")

                if "rssi" in overall:
                    f.write(f"\n  RSSI:\n")
                    f.write(f"    Min: {overall['rssi']['min']} dBm\n")
                    f.write(f"    Max: {overall['rssi']['max']} dBm\n")
                    f.write(f"    Avg: {overall['rssi']['avg']:.1f} dBm\n")

                if "latency" in overall:
                    f.write(f"\n  Latency:\n")
                    f.write(f"    Min: {overall['latency']['min']:.1f} ms\n")
                    f.write(f"    Max: {overall['latency']['max']:.1f} ms\n")
                    f.write(f"    Avg: {overall['latency']['avg']:.1f} ms\n")

                if "packet_loss" in overall:
                    f.write(f"\n  Packet Loss:\n")
                    f.write(f"    Min: {overall['packet_loss']['min']:.2f}%\n")
                    f.write(f"    Max: {overall['packet_loss']['max']:.2f}%\n")
                    f.write(f"    Avg: {overall['packet_loss']['avg']:.2f}%\n")

                f.write("\n" + "=" * 50 + "\n")
                f.write("Per-Device Statistics:\n")

                for device_id, device_stats in summary["per_device"].items():
                    f.write(f"\n  {device_id}:\n")
                    f.write(f"    Entries: {device_stats.get('total_entries', 0)}\n")

                    if "rssi" in device_stats:
                        f.write(
                            f"    RSSI Avg: {device_stats['rssi']['avg']:.1f} dBm\n"
                        )
                    if "latency" in device_stats:
                        f.write(
                            f"    Latency Avg: {device_stats['latency']['avg']:.1f} ms\n"
                        )
