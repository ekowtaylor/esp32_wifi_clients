"""
ESP32 Device Handler

Manages individual serial connections to ESP32 devices.
"""

import threading
import time
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Callable, Optional

import serial
from serial.tools import list_ports


@dataclass
class DeviceInfo:
    """Information about a connected ESP32 device."""

    port: str
    device_id: str
    vid: Optional[int] = None
    pid: Optional[int] = None
    manufacturer: Optional[str] = None
    description: Optional[str] = None


class ESP32Device:
    """
    Manages a serial connection to a single ESP32 device.

    Handles connection, data reading, and command sending.
    """

    # Common USB VID/PID pairs for ESP32 boards
    KNOWN_ESP32_DEVICES = [
        (0x10C4, 0xEA60),  # Silicon Labs CP210x
        (0x1A86, 0x7523),  # CH340
        (0x1A86, 0x55D4),  # CH9102
        (0x303A, 0x1001),  # ESP32-S2 native USB
        (0x303A, 0x0002),  # ESP32-S3 native USB
        (0x0403, 0x6001),  # FTDI FT232
        (0x0403, 0x6015),  # FTDI FT231X
    ]

    def __init__(
        self,
        port: str,
        device_id: Optional[str] = None,
        baud_rate: int = 115200,
        timeout: float = 1.0,
    ):
        """
        Initialize an ESP32 device connection.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0' or 'COM3')
            device_id: Custom identifier for this device
            baud_rate: Serial baud rate (default: 115200)
            timeout: Read timeout in seconds
        """
        self.port = port
        self.device_id = device_id or self._generate_device_id(port)
        self.baud_rate = baud_rate
        self.timeout = timeout

        self._serial: Optional[serial.Serial] = None
        self._read_thread: Optional[threading.Thread] = None
        self._running = False
        self._data_queue: Queue = Queue()
        self._callbacks: list[Callable[[str, str], None]] = []
        self._lock = threading.Lock()

    @staticmethod
    def _generate_device_id(port: str) -> str:
        """Generate a device ID from the port name."""
        return port.split("/")[-1].replace("tty.", "").replace("cu.", "")

    @classmethod
    def discover_devices(cls) -> list[DeviceInfo]:
        """
        Discover all connected ESP32 devices.

        Returns:
            List of DeviceInfo for each discovered device.
        """
        devices = []
        for port_info in list_ports.comports():
            # Check if this matches known ESP32 devices
            is_esp32 = False
            if port_info.vid and port_info.pid:
                for vid, pid in cls.KNOWN_ESP32_DEVICES:
                    if port_info.vid == vid and port_info.pid == pid:
                        is_esp32 = True
                        break

            # Also check by description/manufacturer
            desc_lower = (port_info.description or "").lower()
            mfr_lower = (port_info.manufacturer or "").lower()
            if any(
                kw in desc_lower or kw in mfr_lower
                for kw in ["esp32", "cp210", "ch340", "ch910", "ftdi"]
            ):
                is_esp32 = True

            if is_esp32:
                devices.append(
                    DeviceInfo(
                        port=port_info.device,
                        device_id=cls._generate_device_id(port_info.device),
                        vid=port_info.vid,
                        pid=port_info.pid,
                        manufacturer=port_info.manufacturer,
                        description=port_info.description,
                    )
                )

        return devices

    def connect(self) -> bool:
        """
        Establish connection to the ESP32 device.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
            time.sleep(0.1)  # Allow connection to stabilize
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            return True
        except serial.SerialException as e:
            print(f"[{self.device_id}] Connection failed: {e}")
            return False

    def disconnect(self) -> None:
        """Close the connection to the device."""
        self.stop_reading()
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    @property
    def is_connected(self) -> bool:
        """Check if device is connected."""
        return self._serial is not None and self._serial.is_open

    def start_reading(self) -> None:
        """Start background thread for continuous data reading."""
        if self._running:
            return

        self._running = True
        self._read_thread = threading.Thread(
            target=self._read_loop, daemon=True, name=f"ESP32Reader-{self.device_id}"
        )
        self._read_thread.start()

    def stop_reading(self) -> None:
        """Stop the background reading thread."""
        self._running = False
        if self._read_thread:
            self._read_thread.join(timeout=2.0)
            self._read_thread = None

    def _read_loop(self) -> None:
        """Background loop for reading serial data."""
        buffer = ""
        while self._running and self.is_connected:
            try:
                if self._serial.in_waiting > 0:
                    data = self._serial.read(self._serial.in_waiting)
                    buffer += data.decode("utf-8", errors="replace")

                    # Process complete lines
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            self._handle_line(line)
                else:
                    time.sleep(0.01)
            except serial.SerialException:
                break
            except Exception as e:
                print(f"[{self.device_id}] Read error: {e}")
                time.sleep(0.1)

    def _handle_line(self, line: str) -> None:
        """Process a received line of data."""
        self._data_queue.put(line)

        with self._lock:
            for callback in self._callbacks:
                try:
                    callback(self.device_id, line)
                except Exception as e:
                    print(f"[{self.device_id}] Callback error: {e}")

    def add_callback(self, callback: Callable[[str, str], None]) -> None:
        """
        Add a callback for received data.

        Args:
            callback: Function(device_id, line) called for each line received.
        """
        with self._lock:
            self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[str, str], None]) -> None:
        """Remove a previously added callback."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def get_data(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        Get the next line of data from the queue.

        Args:
            timeout: Time to wait for data (None = non-blocking)

        Returns:
            Data line or None if no data available.
        """
        try:
            return self._data_queue.get(timeout=timeout)
        except Empty:
            return None

    def send_command(self, command: str) -> bool:
        """
        Send a command to the ESP32.

        Args:
            command: Command string to send.

        Returns:
            True if command sent successfully.
        """
        if not self.is_connected:
            return False

        try:
            if not command.endswith("\n"):
                command += "\n"
            self._serial.write(command.encode("utf-8"))
            self._serial.flush()
            return True
        except serial.SerialException as e:
            print(f"[{self.device_id}] Send failed: {e}")
            return False

    def trigger_performance_report(self) -> bool:
        """Request a performance data report from the device."""
        return self.send_command("PERF_REPORT")

    def trigger_speed_test(self) -> bool:
        """Trigger a WiFi speed test on the device."""
        return self.send_command("SPEED_TEST")

    def set_report_interval(self, interval_ms: int) -> bool:
        """Set the automatic reporting interval in milliseconds."""
        return self.send_command(f"SET_INTERVAL:{interval_ms}")

    def enable_continuous_reporting(self, enable: bool = True) -> bool:
        """Enable or disable continuous performance reporting."""
        cmd = "CONTINUOUS:ON" if enable else "CONTINUOUS:OFF"
        return self.send_command(cmd)

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return f"ESP32Device({self.device_id}, port={self.port}, {status})"
