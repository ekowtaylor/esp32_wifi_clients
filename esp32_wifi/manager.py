"""
ESP32 Device Manager

Manages multiple ESP32 device connections simultaneously.
"""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .device import DeviceInfo, ESP32Device


@dataclass
class DeviceStatus:
    """Status information for a connected device."""

    device_id: str
    port: str
    connected: bool
    reading: bool
    last_data_time: Optional[float] = None
    error_count: int = 0


class ESP32Manager:
    """
    Manages connections to multiple ESP32 devices.

    Provides a unified interface for discovering, connecting to, and
    managing multiple ESP32 devices simultaneously.
    """

    def __init__(
        self,
        auto_reconnect: bool = True,
        reconnect_interval: float = 5.0,
    ):
        """
        Initialize the ESP32 manager.

        Args:
            auto_reconnect: Automatically reconnect to disconnected devices.
            reconnect_interval: Seconds between reconnection attempts.
        """
        self.auto_reconnect = auto_reconnect
        self.reconnect_interval = reconnect_interval

        self._devices: Dict[str, ESP32Device] = {}
        self._device_status: Dict[str, DeviceStatus] = {}
        self._global_callbacks: list[Callable[[str, str], None]] = []
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False

    def discover_and_connect(
        self,
        baud_rate: int = 115200,
        device_filter: Optional[Callable[[DeviceInfo], bool]] = None,
    ) -> List[str]:
        """
        Discover all ESP32 devices and connect to them.

        Args:
            baud_rate: Baud rate for all connections.
            device_filter: Optional function to filter devices.

        Returns:
            List of device IDs that were successfully connected.
        """
        devices = ESP32Device.discover_devices()

        if device_filter:
            devices = [d for d in devices if device_filter(d)]

        connected_ids = []
        for device_info in devices:
            device_id = self.add_device(
                port=device_info.port,
                device_id=device_info.device_id,
                baud_rate=baud_rate,
            )
            if device_id:
                connected_ids.append(device_id)

        return connected_ids

    def add_device(
        self,
        port: str,
        device_id: Optional[str] = None,
        baud_rate: int = 115200,
    ) -> Optional[str]:
        """
        Add and connect to a specific device.

        Args:
            port: Serial port path.
            device_id: Custom device identifier.
            baud_rate: Serial baud rate.

        Returns:
            Device ID if connected successfully, None otherwise.
        """
        device = ESP32Device(
            port=port,
            device_id=device_id,
            baud_rate=baud_rate,
        )

        if not device.connect():
            return None

        # Add global callbacks
        for callback in self._global_callbacks:
            device.add_callback(callback)

        with self._lock:
            self._devices[device.device_id] = device
            self._device_status[device.device_id] = DeviceStatus(
                device_id=device.device_id,
                port=port,
                connected=True,
                reading=False,
            )

        return device.device_id

    def remove_device(self, device_id: str) -> bool:
        """
        Disconnect and remove a device.

        Args:
            device_id: ID of device to remove.

        Returns:
            True if device was found and removed.
        """
        with self._lock:
            device = self._devices.pop(device_id, None)
            self._device_status.pop(device_id, None)

        if device:
            device.disconnect()
            return True
        return False

    def get_device(self, device_id: str) -> Optional[ESP32Device]:
        """Get a device by ID."""
        return self._devices.get(device_id)

    def get_all_devices(self) -> List[ESP32Device]:
        """Get all connected devices."""
        return list(self._devices.values())

    def get_device_ids(self) -> List[str]:
        """Get all device IDs."""
        return list(self._devices.keys())

    def get_status(self, device_id: Optional[str] = None) -> Dict[str, DeviceStatus]:
        """
        Get status of devices.

        Args:
            device_id: Specific device ID, or None for all devices.

        Returns:
            Dictionary of device statuses.
        """
        if device_id:
            status = self._device_status.get(device_id)
            return {device_id: status} if status else {}
        return dict(self._device_status)

    def start_reading_all(self) -> None:
        """Start reading from all connected devices."""
        for device_id, device in self._devices.items():
            device.start_reading()
            if device_id in self._device_status:
                self._device_status[device_id].reading = True

    def stop_reading_all(self) -> None:
        """Stop reading from all devices."""
        for device_id, device in self._devices.items():
            device.stop_reading()
            if device_id in self._device_status:
                self._device_status[device_id].reading = False

    def add_global_callback(self, callback: Callable[[str, str], None]) -> None:
        """
        Add a callback that receives data from all devices.

        Args:
            callback: Function(device_id, line) called for each data line.
        """
        self._global_callbacks.append(callback)
        for device in self._devices.values():
            device.add_callback(callback)

    def remove_global_callback(self, callback: Callable[[str, str], None]) -> None:
        """Remove a global callback."""
        if callback in self._global_callbacks:
            self._global_callbacks.remove(callback)
            for device in self._devices.values():
                device.remove_callback(callback)

    def broadcast_command(self, command: str) -> Dict[str, bool]:
        """
        Send a command to all devices.

        Args:
            command: Command to send.

        Returns:
            Dictionary mapping device_id to success status.
        """
        results = {}
        for device_id, device in self._devices.items():
            results[device_id] = device.send_command(command)
        return results

    def trigger_all_performance_reports(self) -> Dict[str, bool]:
        """Request performance reports from all devices."""
        return self.broadcast_command("PERF_REPORT")

    def trigger_all_speed_tests(self) -> Dict[str, bool]:
        """Trigger speed tests on all devices."""
        return self.broadcast_command("SPEED_TEST")

    def enable_all_continuous_reporting(
        self,
        enable: bool = True,
        interval_ms: int = 1000,
    ) -> None:
        """
        Enable or disable continuous reporting on all devices.

        Args:
            enable: Whether to enable continuous reporting.
            interval_ms: Reporting interval in milliseconds.
        """
        for device in self._devices.values():
            device.set_report_interval(interval_ms)
            device.enable_continuous_reporting(enable)

    def start_monitoring(self) -> None:
        """Start background monitoring for device health and auto-reconnect."""
        if self._running:
            return

        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="ESP32Monitor"
        )
        self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
            self._monitor_thread = None

    def _monitor_loop(self) -> None:
        """Background loop for device health monitoring."""
        while self._running:
            # Check for disconnected devices
            for device_id, device in list(self._devices.items()):
                if not device.is_connected:
                    if device_id in self._device_status:
                        self._device_status[device_id].connected = False

                    if self.auto_reconnect:
                        # Attempt reconnect
                        if device.connect():
                            device.start_reading()
                            if device_id in self._device_status:
                                self._device_status[device_id].connected = True
                                self._device_status[device_id].reading = True

            time.sleep(self.reconnect_interval)

    def disconnect_all(self) -> None:
        """Disconnect from all devices."""
        self.stop_monitoring()
        self.stop_reading_all()

        for device in list(self._devices.values()):
            device.disconnect()

        self._devices.clear()
        self._device_status.clear()

    @property
    def device_count(self) -> int:
        """Number of connected devices."""
        return len(self._devices)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnect all devices."""
        self.disconnect_all()
        return False

    def __repr__(self) -> str:
        return f"ESP32Manager({self.device_count} devices)"
