from __future__ import annotations

import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Iterable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from app.domain import Device, StatusState


class PingChecker(QObject):
    status_updated = Signal(str, str, float)  # device_id, state, rtt_ms

    def __init__(self, devices: Iterable[Device], interval_ms: int = 30000) -> None:
        super().__init__()
        self._devices = list(devices)
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)
        self._executor = ThreadPoolExecutor(max_workers=8)
        self._ping_count = 10

    def set_devices(self, devices: Iterable[Device]) -> None:
        self._devices = list(devices)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        for device in self._devices:
            if not device.ip_address:
                continue
            self._executor.submit(self._ping, device)

    def _ping(self, device: Device) -> None:
        ip = device.ip_address
        cmd = self._ping_command(ip, self._ping_count)
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            output = out.stdout + out.stderr
            received = self._parse_received(output)
            rtt = self._parse_rtt(output) or 0.0
            if received is None:
                state = StatusState.DOWN.value if out.returncode != 0 else StatusState.UP.value
            elif received >= 8:
                state = StatusState.UP.value
            else:
                state = StatusState.DOWN.value
        except Exception:
            rtt = 0.0
            state = StatusState.DOWN.value
        self.status_updated.emit(device.id, state, rtt)

    @staticmethod
    def _ping_command(ip: str, count: int) -> list[str]:
        if sys.platform.startswith("win"):
            return ["ping", "-n", str(count), "-w", "1000", ip]
        if sys.platform == "darwin":
            return ["ping", "-c", str(count), "-W", "1000", ip]
        return ["ping", "-c", str(count), "-W", "1", ip]

    @staticmethod
    def _parse_rtt(output: str) -> Optional[float]:
        unix_match = re.search(r"=\s*([0-9.]+)/([0-9.]+)/([0-9.]+)/", output)
        if unix_match:
            try:
                return float(unix_match.group(2))
            except ValueError:
                return None
        win_match = re.search(r"Average\s*=\s*([0-9]+)ms", output)
        if win_match:
            try:
                return float(win_match.group(1))
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_received(output: str) -> Optional[int]:
        unix_match = re.search(r"(\d+)\s+packets\s+transmitted,\s+(\d+)\s+received", output)
        if unix_match:
            try:
                return int(unix_match.group(2))
            except ValueError:
                return None
        win_match = re.search(r"Received\s*=\s*(\d+)", output)
        if win_match:
            try:
                return int(win_match.group(1))
            except ValueError:
                return None
        return None
