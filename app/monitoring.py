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

    def __init__(self, devices: Iterable[Device], interval_ms: int = 1000) -> None:
        super().__init__()
        self._devices = list(devices)
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)
        self._executor = ThreadPoolExecutor(max_workers=8)

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
        cmd = self._ping_command(ip)
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if out.returncode == 0:
                rtt = self._parse_rtt(out.stdout + out.stderr) or 0.0
                state = StatusState.UP.value
            else:
                rtt = 0.0
                state = StatusState.DOWN.value
        except Exception:
            rtt = 0.0
            state = StatusState.DOWN.value
        self.status_updated.emit(device.id, state, rtt)

    @staticmethod
    def _ping_command(ip: str) -> list[str]:
        if sys.platform.startswith("win"):
            return ["ping", "-n", "1", "-w", "1000", ip]
        if sys.platform == "darwin":
            return ["ping", "-c", "1", "-W", "1000", ip]
        return ["ping", "-c", "1", "-W", "1", ip]

    @staticmethod
    def _parse_rtt(output: str) -> Optional[float]:
        match = re.search(r"time[=<]([0-9.]+)\s*ms", output)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None
