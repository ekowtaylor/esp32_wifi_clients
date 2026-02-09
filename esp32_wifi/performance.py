"""
WiFi Performance Data Models and Parser

Parses and structures WiFi performance data from ESP32 devices.
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ConnectionStatus(Enum):
    """WiFi connection status."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


@dataclass
class WiFiPerformanceData:
    """
    WiFi performance metrics from an ESP32 device.

    All data fields are optional as devices may not report all metrics.
    """

    # Identification
    device_id: str
    timestamp: float = field(default_factory=time.time)

    # Connection info
    ssid: Optional[str] = None
    bssid: Optional[str] = None
    channel: Optional[int] = None
    status: ConnectionStatus = ConnectionStatus.DISCONNECTED

    # Signal quality
    rssi: Optional[int] = None  # dBm
    snr: Optional[float] = None  # Signal-to-noise ratio
    noise_floor: Optional[int] = None  # dBm

    # Throughput (in Kbps or Mbps depending on context)
    tx_rate: Optional[float] = None
    rx_rate: Optional[float] = None
    link_speed: Optional[int] = None  # Mbps

    # Packet statistics
    tx_packets: Optional[int] = None
    rx_packets: Optional[int] = None
    tx_bytes: Optional[int] = None
    rx_bytes: Optional[int] = None
    tx_errors: Optional[int] = None
    rx_errors: Optional[int] = None
    tx_retries: Optional[int] = None
    packet_loss: Optional[float] = None  # Percentage

    # Latency (in ms)
    latency_min: Optional[float] = None
    latency_avg: Optional[float] = None
    latency_max: Optional[float] = None
    jitter: Optional[float] = None

    # Speed test results
    download_speed: Optional[float] = None  # Mbps
    upload_speed: Optional[float] = None  # Mbps

    # Device metrics
    free_heap: Optional[int] = None  # bytes
    uptime: Optional[int] = None  # seconds
    cpu_freq: Optional[int] = None  # MHz

    # Raw data for custom parsing
    raw_data: Optional[str] = None

    @property
    def signal_strength(self) -> str:
        """Human-readable signal strength."""
        if self.rssi is None:
            return "Unknown"
        if self.rssi >= -50:
            return "Excellent"
        elif self.rssi >= -60:
            return "Good"
        elif self.rssi >= -70:
            return "Fair"
        elif self.rssi >= -80:
            return "Weak"
        else:
            return "Poor"

    @property
    def datetime(self) -> datetime:
        """Convert timestamp to datetime."""
        return datetime.fromtimestamp(self.timestamp)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "device_id": self.device_id,
            "timestamp": self.timestamp,
            "datetime": self.datetime.isoformat(),
            "ssid": self.ssid,
            "bssid": self.bssid,
            "channel": self.channel,
            "status": self.status.value,
            "rssi": self.rssi,
            "signal_strength": self.signal_strength,
            "snr": self.snr,
            "noise_floor": self.noise_floor,
            "tx_rate": self.tx_rate,
            "rx_rate": self.rx_rate,
            "link_speed": self.link_speed,
            "tx_packets": self.tx_packets,
            "rx_packets": self.rx_packets,
            "tx_bytes": self.tx_bytes,
            "rx_bytes": self.rx_bytes,
            "tx_errors": self.tx_errors,
            "rx_errors": self.rx_errors,
            "tx_retries": self.tx_retries,
            "packet_loss": self.packet_loss,
            "latency_min": self.latency_min,
            "latency_avg": self.latency_avg,
            "latency_max": self.latency_max,
            "jitter": self.jitter,
            "download_speed": self.download_speed,
            "upload_speed": self.upload_speed,
            "free_heap": self.free_heap,
            "uptime": self.uptime,
            "cpu_freq": self.cpu_freq,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class PerformanceParser:
    """
    Parser for ESP32 WiFi performance data.

    Supports multiple data formats:
    - JSON format
    - Key-value format (KEY:VALUE or KEY=VALUE)
    - CSV format
    """

    # Regex patterns for different data formats
    PATTERNS = {
        # JSON format: {"rssi": -45, "ssid": "MyNetwork", ...}
        "json": re.compile(r"^\s*\{.*\}\s*$"),
        # Performance report format: PERF|rssi:-45|ssid:MyNetwork|...
        "pipe_delimited": re.compile(r"^PERF\|(.+)$"),
        # Key-value format: rssi=-45, ssid=MyNetwork
        "key_value": re.compile(r"(\w+)\s*[=:]\s*([^,\|]+)"),
        # CSV format: device_id,rssi,ssid,channel,...
        "csv": re.compile(r"^[^,]+(?:,[^,]+)+$"),
    }

    # Field mappings from various names to our standard names
    FIELD_MAPPINGS = {
        # RSSI variations
        "rssi": "rssi",
        "signal": "rssi",
        "signal_strength": "rssi",
        "wifi_rssi": "rssi",
        # SSID variations
        "ssid": "ssid",
        "network": "ssid",
        "wifi_ssid": "ssid",
        # Channel
        "channel": "channel",
        "chan": "channel",
        "ch": "channel",
        # BSSID
        "bssid": "bssid",
        "mac": "bssid",
        "ap_mac": "bssid",
        # Throughput
        "tx_rate": "tx_rate",
        "txrate": "tx_rate",
        "tx_speed": "tx_rate",
        "rx_rate": "rx_rate",
        "rxrate": "rx_rate",
        "rx_speed": "rx_rate",
        "link_speed": "link_speed",
        "linkspeed": "link_speed",
        "speed": "link_speed",
        # Packets
        "tx_packets": "tx_packets",
        "txpkt": "tx_packets",
        "rx_packets": "rx_packets",
        "rxpkt": "rx_packets",
        "tx_bytes": "tx_bytes",
        "txbytes": "tx_bytes",
        "rx_bytes": "rx_bytes",
        "rxbytes": "rx_bytes",
        "tx_errors": "tx_errors",
        "txerr": "tx_errors",
        "rx_errors": "rx_errors",
        "rxerr": "rx_errors",
        "tx_retries": "tx_retries",
        "retries": "tx_retries",
        "packet_loss": "packet_loss",
        "loss": "packet_loss",
        "ploss": "packet_loss",
        # Latency
        "latency": "latency_avg",
        "latency_avg": "latency_avg",
        "ping": "latency_avg",
        "rtt": "latency_avg",
        "latency_min": "latency_min",
        "ping_min": "latency_min",
        "latency_max": "latency_max",
        "ping_max": "latency_max",
        "jitter": "jitter",
        # Speed test
        "download": "download_speed",
        "download_speed": "download_speed",
        "dl_speed": "download_speed",
        "upload": "upload_speed",
        "upload_speed": "upload_speed",
        "ul_speed": "upload_speed",
        # Device info
        "heap": "free_heap",
        "free_heap": "free_heap",
        "freemem": "free_heap",
        "uptime": "uptime",
        "cpu_freq": "cpu_freq",
        "freq": "cpu_freq",
        # SNR
        "snr": "snr",
        "noise": "noise_floor",
        "noise_floor": "noise_floor",
    }

    @classmethod
    def parse(cls, device_id: str, line: str) -> Optional[WiFiPerformanceData]:
        """
        Parse a line of performance data.

        Args:
            device_id: ID of the device that sent this data.
            line: Raw data line to parse.

        Returns:
            WiFiPerformanceData object or None if parsing failed.
        """
        line = line.strip()
        if not line:
            return None

        # Try JSON format first
        if cls.PATTERNS["json"].match(line):
            return cls._parse_json(device_id, line)

        # Try pipe-delimited format
        match = cls.PATTERNS["pipe_delimited"].match(line)
        if match:
            return cls._parse_key_value(device_id, match.group(1), delimiter="|")

        # Try key-value format
        if "=" in line or ":" in line:
            return cls._parse_key_value(device_id, line)

        return None

    @classmethod
    def _parse_json(cls, device_id: str, line: str) -> Optional[WiFiPerformanceData]:
        """Parse JSON formatted data."""
        try:
            data = json.loads(line)
            return cls._build_performance_data(device_id, data, line)
        except json.JSONDecodeError:
            return None

    @classmethod
    def _parse_key_value(
        cls,
        device_id: str,
        line: str,
        delimiter: str = ",",
    ) -> Optional[WiFiPerformanceData]:
        """Parse key-value formatted data."""
        data = {}

        # Split by delimiter first if not comma
        if delimiter != ",":
            parts = line.split(delimiter)
        else:
            parts = [line]

        for part in parts:
            matches = cls.PATTERNS["key_value"].findall(part)
            for key, value in matches:
                data[key.lower()] = value.strip()

        if data:
            return cls._build_performance_data(device_id, data, line)
        return None

    @classmethod
    def _build_performance_data(
        cls,
        device_id: str,
        data: Dict[str, Any],
        raw_line: str,
    ) -> WiFiPerformanceData:
        """Build WiFiPerformanceData from parsed data dictionary."""
        perf = WiFiPerformanceData(device_id=device_id, raw_data=raw_line)

        for raw_key, value in data.items():
            normalized_key = cls.FIELD_MAPPINGS.get(raw_key.lower())
            if normalized_key and hasattr(perf, normalized_key):
                try:
                    # Convert value to appropriate type
                    converted = cls._convert_value(normalized_key, value)
                    setattr(perf, normalized_key, converted)
                except (ValueError, TypeError):
                    pass  # Skip invalid values

        # Handle status field specially
        if "status" in data:
            status_val = str(data["status"]).lower()
            if status_val in ["connected", "1", "true"]:
                perf.status = ConnectionStatus.CONNECTED
            elif status_val in ["connecting", "2"]:
                perf.status = ConnectionStatus.CONNECTING
            elif status_val in ["failed", "-1", "error"]:
                perf.status = ConnectionStatus.FAILED
            else:
                perf.status = ConnectionStatus.DISCONNECTED

        return perf

    @classmethod
    def _convert_value(cls, field_name: str, value: Any) -> Any:
        """Convert a value to the appropriate type for a field."""
        if value is None:
            return None

        # String fields
        if field_name in ("ssid", "bssid"):
            return str(value)

        # Integer fields
        int_fields = (
            "rssi",
            "channel",
            "link_speed",
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
        )
        if field_name in int_fields:
            return int(float(value))

        # Float fields
        float_fields = (
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
        )
        if field_name in float_fields:
            return float(value)

        return value


class PerformanceMonitor:
    """
    Monitors and aggregates WiFi performance data from multiple devices.
    """

    def __init__(self, history_size: int = 1000):
        """
        Initialize the performance monitor.

        Args:
            history_size: Maximum number of data points to keep per device.
        """
        self.history_size = history_size
        self._history: Dict[str, List[WiFiPerformanceData]] = {}
        self._latest: Dict[str, WiFiPerformanceData] = {}
        self._parser = PerformanceParser()
        self._callbacks: list = []

    def process_line(self, device_id: str, line: str) -> Optional[WiFiPerformanceData]:
        """
        Process a line of data from a device.

        Args:
            device_id: ID of the device.
            line: Raw data line.

        Returns:
            Parsed WiFiPerformanceData or None.
        """
        perf_data = self._parser.parse(device_id, line)
        if perf_data:
            self._add_data(perf_data)

            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(perf_data)
                except Exception:
                    pass

        return perf_data

    def _add_data(self, data: WiFiPerformanceData) -> None:
        """Add data point to history."""
        device_id = data.device_id

        if device_id not in self._history:
            self._history[device_id] = []

        self._history[device_id].append(data)
        self._latest[device_id] = data

        # Trim history if needed
        if len(self._history[device_id]) > self.history_size:
            self._history[device_id] = self._history[device_id][-self.history_size :]

    def add_callback(self, callback) -> None:
        """Add callback for new performance data."""
        self._callbacks.append(callback)

    def get_latest(
        self, device_id: Optional[str] = None
    ) -> Dict[str, WiFiPerformanceData]:
        """Get latest performance data for device(s)."""
        if device_id:
            data = self._latest.get(device_id)
            return {device_id: data} if data else {}
        return dict(self._latest)

    def get_history(
        self,
        device_id: str,
        limit: Optional[int] = None,
    ) -> List[WiFiPerformanceData]:
        """Get performance history for a device."""
        history = self._history.get(device_id, [])
        if limit:
            return history[-limit:]
        return list(history)

    def get_statistics(self, device_id: str) -> Dict[str, Any]:
        """
        Calculate statistics for a device's performance history.

        Returns dict with min, max, avg for key metrics.
        """
        history = self._history.get(device_id, [])
        if not history:
            return {}

        stats = {}

        # Calculate stats for RSSI
        rssi_values = [d.rssi for d in history if d.rssi is not None]
        if rssi_values:
            stats["rssi"] = {
                "min": min(rssi_values),
                "max": max(rssi_values),
                "avg": sum(rssi_values) / len(rssi_values),
                "count": len(rssi_values),
            }

        # Calculate stats for latency
        latency_values = [d.latency_avg for d in history if d.latency_avg is not None]
        if latency_values:
            stats["latency"] = {
                "min": min(latency_values),
                "max": max(latency_values),
                "avg": sum(latency_values) / len(latency_values),
                "count": len(latency_values),
            }

        # Calculate stats for packet loss
        loss_values = [d.packet_loss for d in history if d.packet_loss is not None]
        if loss_values:
            stats["packet_loss"] = {
                "min": min(loss_values),
                "max": max(loss_values),
                "avg": sum(loss_values) / len(loss_values),
                "count": len(loss_values),
            }

        return stats

    def clear_history(self, device_id: Optional[str] = None) -> None:
        """Clear history for a device or all devices."""
        if device_id:
            self._history.pop(device_id, None)
        else:
            self._history.clear()
