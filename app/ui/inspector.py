from __future__ import annotations

from PySide6.QtWidgets import QLabel, QFormLayout, QWidget

from app.domain import Site


class InspectorPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)
        self._name = QLabel("—")
        self._type = QLabel("—")
        self._notes = QLabel("—")
        self._coords = QLabel("—")

        layout.addRow("Назва:", self._name)
        layout.addRow("Тип:", self._type)
        layout.addRow("Координати:", self._coords)
        layout.addRow("Нотатки:", self._notes)

    def show_site(self, site: Site | None) -> None:
        if site is None:
            self._name.setText("—")
            self._type.setText("—")
            self._coords.setText("—")
            self._notes.setText("—")
            return

        self._name.setText(site.name)
        self._type.setText(site.kind.value)
        self._coords.setText(f"{site.location.lat:.6f}, {site.location.lon:.6f}")
        self._notes.setText(f"пристроїв: {len(site.devices)}")
