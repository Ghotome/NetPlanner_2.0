from __future__ import annotations

import re
import subprocess
import os
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Deque, Iterable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from app.domain import Device, StatusState


class PingChecker(QObject):
    status_updated = Signal(str, str, float)  # device_id, state, rtt_ms

    def __init__(self, devices: Iterable[Device], interval_ms: int = 30000) -> None:
        super().__init__()
        self._devices = list(devices)
        self._interval_ms = interval_ms
        self._dispatch_timer = QTimer(self)
        self._dispatch_timer.timeout.connect(self._dispatch_tick)
        self._executor = ThreadPoolExecutor(max_workers=6)
        self._max_in_flight = 6
        self._ping_count = 10
        self._device_queue: Deque[Device] = deque()
        self._in_flight: set[str] = set()
        self._next_cycle_ts = 0.0
        self._dispatch_timer.setInterval(self._compute_dispatch_interval())
        self.status_updated.connect(self._on_ping_completed)

    def set_devices(self, devices: Iterable[Device]) -> None:
        self._devices = list(devices)
        self._reset_queue()
        self._dispatch_timer.setInterval(self._compute_dispatch_interval())

    def start(self) -> None:
        self._reset_queue()
        self._next_cycle_ts = time.monotonic() + (self._interval_ms / 1000.0)
        self._dispatch_timer.start()

    def stop(self) -> None:
        self._dispatch_timer.stop()

    def _dispatch_tick(self) -> None:
        now = time.monotonic()
        if now >= self._next_cycle_ts and not self._device_queue:
            self._reset_queue()
            self._next_cycle_ts = now + (self._interval_ms / 1000.0)
        if not self._device_queue:
            return
        if len(self._in_flight) >= self._max_in_flight:
            return
        device = self._device_queue.popleft()
        if not device.ip_address:
            return
        self._in_flight.add(device.id)
        self._executor.submit(self._ping, device)

    def _reset_queue(self) -> None:
        self._device_queue.clear()
        for device in self._devices:
            if device.ip_address:
                self._device_queue.append(device)

    def _compute_dispatch_interval(self) -> int:
        count = max(1, len(self._devices))
        return max(200, int(self._interval_ms / count))

    def _on_ping_completed(self, device_id: str, _state: str, _rtt_ms: float) -> None:
        self._in_flight.discard(device_id)

    def _ping(self, device: Device) -> None:
        ip = device.ip_address
        cmd = self._ping_command(ip, self._ping_count)
        try:
            env = os.environ.copy()
            env["LC_ALL"] = "C"
            env["LANG"] = "C"
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=env)
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
