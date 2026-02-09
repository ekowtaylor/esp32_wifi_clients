"""
Live Display for WiFi Performance Monitoring

Provides real-time terminal display of performance data.
"""

import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

from .performance import WiFiPerformanceData


class LiveDisplay:
    """
    Real-time terminal display for WiFi performance data.

    Provides a continuously updating view of performance metrics
    from multiple ESP32 devices.
    """

    # ANSI color codes
    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
    }

    def __init__(
        self,
        refresh_rate: float = 0.5,
        show_graphs: bool = True,
        compact_mode: bool = False,
    ):
        """
        Initialize the live display.

        Args:
            refresh_rate: Seconds between display updates.
            show_graphs: Whether to show ASCII graphs.
            compact_mode: Use compact single-line per device format.
        """
        self.refresh_rate = refresh_rate
        self.show_graphs = show_graphs
        self.compact_mode = compact_mode

        self._device_data: Dict[str, WiFiPerformanceData] = {}
        self._rssi_history: Dict[str, List[int]] = {}
        self._history_size = 60  # Keep 60 data points for graphs
        self._running = False
        self._display_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._start_time = time.time()

    def update(self, data: WiFiPerformanceData) -> None:
        """
        Update display with new performance data.

        Args:
            data: New performance data from a device.
        """
        with self._lock:
            self._device_data[data.device_id] = data

            # Update RSSI history for graphs
            if data.rssi is not None:
                if data.device_id not in self._rssi_history:
                    self._rssi_history[data.device_id] = []
                self._rssi_history[data.device_id].append(data.rssi)
                if len(self._rssi_history[data.device_id]) > self._history_size:
                    self._rssi_history[data.device_id].pop(0)

    def start(self) -> None:
        """Start the live display update loop."""
        if self._running:
            return

        self._running = True
        self._start_time = time.time()
        self._display_thread = threading.Thread(
            target=self._display_loop, daemon=True, name="LiveDisplay"
        )
        self._display_thread.start()

    def stop(self) -> None:
        """Stop the live display."""
        self._running = False
        if self._display_thread:
            self._display_thread.join(timeout=2.0)
            self._display_thread = None

    def _display_loop(self) -> None:
        """Background loop for display updates."""
        while self._running:
            self._render()
            time.sleep(self.refresh_rate)

    def _clear_screen(self) -> None:
        """Clear terminal screen."""
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

    def _render(self) -> None:
        """Render the display."""
        self._clear_screen()

        c = self.COLORS
        uptime = time.time() - self._start_time

        # Header
        print(
            f"{c['bold']}{c['cyan']}╔══════════════════════════════════════════════════════════════════════════════╗{c['reset']}"
        )
        print(
            f"{c['bold']}{c['cyan']}║{c['reset']}  {c['bold']}ESP32 WiFi Performance Monitor{c['reset']}                                              {c['cyan']}║{c['reset']}"
        )
        print(
            f"{c['bold']}{c['cyan']}║{c['reset']}  {c['dim']}Running: {self._format_duration(uptime)} | Devices: {len(self._device_data)} | {datetime.now().strftime('%H:%M:%S')}{c['reset']}      {c['cyan']}║{c['reset']}"
        )
        print(
            f"{c['bold']}{c['cyan']}╠══════════════════════════════════════════════════════════════════════════════╣{c['reset']}"
        )

        with self._lock:
            if not self._device_data:
                print(
                    f"{c['cyan']}║{c['reset']}  {c['dim']}Waiting for data...{c['reset']}                                                         {c['cyan']}║{c['reset']}"
                )
            else:
                for device_id, data in sorted(self._device_data.items()):
                    if self.compact_mode:
                        self._render_compact(device_id, data)
                    else:
                        self._render_detailed(device_id, data)

        print(
            f"{c['bold']}{c['cyan']}╚══════════════════════════════════════════════════════════════════════════════╝{c['reset']}"
        )
        print(f"\n{c['dim']}Press Ctrl+C to exit{c['reset']}")

    def _render_compact(self, device_id: str, data: WiFiPerformanceData) -> None:
        """Render compact single-line view for a device."""
        c = self.COLORS

        rssi_str = f"{data.rssi:4d} dBm" if data.rssi else "   N/A  "
        rssi_color = self._get_rssi_color(data.rssi)

        ssid = (data.ssid or "N/A")[:15].ljust(15)
        latency = f"{data.latency_avg:6.1f}ms" if data.latency_avg else "    N/A "
        loss = f"{data.packet_loss:5.1f}%" if data.packet_loss is not None else "  N/A "

        line = f"{c['cyan']}║{c['reset']} {c['bold']}{device_id:12s}{c['reset']} │ {ssid} │ {rssi_color}{rssi_str}{c['reset']} │ {latency} │ {loss} {c['cyan']}║{c['reset']}"
        print(line)

    def _render_detailed(self, device_id: str, data: WiFiPerformanceData) -> None:
        """Render detailed multi-line view for a device."""
        c = self.COLORS

        # Device header
        status_color = c["green"] if data.status.value == "connected" else c["red"]
        print(
            f"{c['cyan']}║{c['reset']}  {c['bold']}{c['blue']}┌─ {device_id}{c['reset']} {status_color}[{data.status.value.upper()}]{c['reset']}"
        )

        # Connection info
        ssid = data.ssid or "N/A"
        channel = data.channel or "N/A"
        print(
            f"{c['cyan']}║{c['reset']}  {c['blue']}│{c['reset']}  SSID: {c['white']}{ssid}{c['reset']} | Channel: {channel}"
        )

        # Signal quality
        rssi_color = self._get_rssi_color(data.rssi)
        rssi_str = f"{data.rssi} dBm" if data.rssi else "N/A"
        signal_bar = self._render_signal_bar(data.rssi) if data.rssi else ""
        print(
            f"{c['cyan']}║{c['reset']}  {c['blue']}│{c['reset']}  Signal: {rssi_color}{rssi_str:10s}{c['reset']} {signal_bar} ({data.signal_strength})"
        )

        # Throughput
        if data.tx_rate or data.rx_rate or data.link_speed:
            tx = f"{data.tx_rate:.1f}" if data.tx_rate else "N/A"
            rx = f"{data.rx_rate:.1f}" if data.rx_rate else "N/A"
            link = f"{data.link_speed}" if data.link_speed else "N/A"
            print(
                f"{c['cyan']}║{c['reset']}  {c['blue']}│{c['reset']}  TX: {tx} Kbps | RX: {rx} Kbps | Link: {link} Mbps"
            )

        # Latency
        if data.latency_avg is not None:
            lat_color = self._get_latency_color(data.latency_avg)
            jitter = f"{data.jitter:.1f}ms" if data.jitter else "N/A"
            print(
                f"{c['cyan']}║{c['reset']}  {c['blue']}│{c['reset']}  Latency: {lat_color}{data.latency_avg:.1f}ms{c['reset']} (min: {data.latency_min or 0:.1f}, max: {data.latency_max or 0:.1f}) | Jitter: {jitter}"
            )

        # Packet stats
        if data.packet_loss is not None:
            loss_color = (
                c["green"]
                if data.packet_loss < 1
                else c["yellow"] if data.packet_loss < 5 else c["red"]
            )
            print(
                f"{c['cyan']}║{c['reset']}  {c['blue']}│{c['reset']}  Packet Loss: {loss_color}{data.packet_loss:.2f}%{c['reset']} | TX Retries: {data.tx_retries or 0}"
            )

        # Speed test results
        if data.download_speed or data.upload_speed:
            dl = f"{data.download_speed:.2f} Mbps" if data.download_speed else "N/A"
            ul = f"{data.upload_speed:.2f} Mbps" if data.upload_speed else "N/A"
            print(
                f"{c['cyan']}║{c['reset']}  {c['blue']}│{c['reset']}  Download: {c['green']}{dl}{c['reset']} | Upload: {c['blue']}{ul}{c['reset']}"
            )

        # RSSI graph
        if self.show_graphs and device_id in self._rssi_history:
            self._render_rssi_graph(device_id)

        print(f"{c['cyan']}║{c['reset']}  {c['blue']}└{'─' * 70}{c['reset']}")

    def _render_signal_bar(self, rssi: Optional[int]) -> str:
        """Render ASCII signal strength bar."""
        if rssi is None:
            return ""

        c = self.COLORS
        # Normalize RSSI to 0-5 scale (-90 to -40 dBm range)
        normalized = max(0, min(5, (rssi + 90) // 10))

        bar = ""
        for i in range(5):
            if i < normalized:
                if normalized >= 4:
                    bar += f"{c['green']}█{c['reset']}"
                elif normalized >= 2:
                    bar += f"{c['yellow']}█{c['reset']}"
                else:
                    bar += f"{c['red']}█{c['reset']}"
            else:
                bar += f"{c['dim']}░{c['reset']}"

        return f"[{bar}]"

    def _render_rssi_graph(self, device_id: str) -> str:
        """Render ASCII RSSI history graph."""
        c = self.COLORS
        history = self._rssi_history.get(device_id, [])
        if len(history) < 2:
            return

        # Graph dimensions
        width = 50
        height = 3

        # Normalize values to graph height
        min_rssi, max_rssi = -90, -40

        # Resample history to fit width
        step = max(1, len(history) // width)
        samples = history[::step][-width:]

        # Build graph
        graph_lines = [["░"] * width for _ in range(height)]

        for i, rssi in enumerate(samples):
            if rssi is not None:
                normalized = (rssi - min_rssi) / (max_rssi - min_rssi)
                bar_height = int(normalized * height)
                for h in range(min(bar_height, height)):
                    if normalized > 0.7:
                        graph_lines[height - 1 - h][i] = f"{c['green']}█{c['reset']}"
                    elif normalized > 0.4:
                        graph_lines[height - 1 - h][i] = f"{c['yellow']}█{c['reset']}"
                    else:
                        graph_lines[height - 1 - h][i] = f"{c['red']}█{c['reset']}"

        print(
            f"{c['cyan']}║{c['reset']}  {c['blue']}│{c['reset']}  {c['dim']}RSSI History:{c['reset']}"
        )
        for line in graph_lines:
            print(
                f"{c['cyan']}║{c['reset']}  {c['blue']}│{c['reset']}    {''.join(line)}"
            )

    def _get_rssi_color(self, rssi: Optional[int]) -> str:
        """Get color code for RSSI value."""
        c = self.COLORS
        if rssi is None:
            return c["dim"]
        if rssi >= -50:
            return c["green"]
        elif rssi >= -60:
            return c["green"]
        elif rssi >= -70:
            return c["yellow"]
        elif rssi >= -80:
            return c["yellow"]
        else:
            return c["red"]

    def _get_latency_color(self, latency: float) -> str:
        """Get color code for latency value."""
        c = self.COLORS
        if latency < 20:
            return c["green"]
        elif latency < 50:
            return c["yellow"]
        else:
            return c["red"]

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human readable format."""
        mins, secs = divmod(int(seconds), 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}h {mins}m {secs}s"
        elif mins > 0:
            return f"{mins}m {secs}s"
        else:
            return f"{secs}s"

    def render_once(self) -> None:
        """Render display once without starting loop."""
        self._render()


class SimpleDisplay:
    """
    Simple line-by-line display for performance data.

    Suitable for piping to files or simple terminals.
    """

    def __init__(self, timestamp: bool = True, device_prefix: bool = True):
        """
        Initialize simple display.

        Args:
            timestamp: Include timestamp in output.
            device_prefix: Include device ID prefix.
        """
        self.timestamp = timestamp
        self.device_prefix = device_prefix

    def display(self, data: WiFiPerformanceData) -> None:
        """Display a line of performance data."""
        parts = []

        if self.timestamp:
            parts.append(data.datetime.strftime("%Y-%m-%d %H:%M:%S"))

        if self.device_prefix:
            parts.append(f"[{data.device_id}]")

        # Key metrics
        if data.rssi is not None:
            parts.append(f"RSSI:{data.rssi}dBm")

        if data.latency_avg is not None:
            parts.append(f"Lat:{data.latency_avg:.1f}ms")

        if data.packet_loss is not None:
            parts.append(f"Loss:{data.packet_loss:.1f}%")

        if data.tx_rate is not None:
            parts.append(f"TX:{data.tx_rate:.0f}Kbps")

        if data.rx_rate is not None:
            parts.append(f"RX:{data.rx_rate:.0f}Kbps")

        print(" | ".join(parts))
