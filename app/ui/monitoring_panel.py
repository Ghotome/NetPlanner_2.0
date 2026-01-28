from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QVBoxLayout, QWidget


class MonitoringPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self._availability = QLabel("Доступність: —", self)
        self._problems = QListWidget(self)
        self._events = QListWidget(self)
        layout.addWidget(self._availability)
        layout.addWidget(QLabel("Проблемні сайти", self))
        layout.addWidget(self._problems)
        layout.addWidget(QLabel("Журнал подій", self))
        layout.addWidget(self._events)

    def set_availability(self, percent: float) -> None:
        self._availability.setText(f"Доступність: {percent:.1f}%")

    def set_problems(self, items: list[str]) -> None:
        self._problems.clear()
        self._problems.addItems(items)

    def add_event(self, text: str) -> None:
        self._events.addItem(text)
