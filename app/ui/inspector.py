from __future__ import annotations

from PySide6.QtCore import Signal, QLocale
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.domain import CableType, Link, LinkKind, LinkType, Site, SiteKind


class InspectorPanel(QWidget):
    link_updated = Signal(str, dict)
    link_analyze_requested = Signal(str)
    site_updated = Signal(str, dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_link_id: str | None = None

        self._site_group = QWidget(self)
        site_layout = QFormLayout(self._site_group)
        self._site_name = QLabel("—")
        self._site_type = QLabel("—")
        self._site_coords = QLabel("—")
        self._site_elevation = QLabel("—")
        self._site_notes = QLabel("—")
        self._site_antenna_type = QComboBox(self)
        self._site_antenna_type.addItems(["omni", "sector", "directional"])
        self._site_azimuth = QLineEdit(self)
        self._site_beamwidth = QLineEdit(self)
        self._site_gain = QLineEdit(self)
        self._site_height = QLineEdit(self)
        self._site_azimuth.setValidator(QDoubleValidator(0.0, 360.0, 1, self))
        self._site_beamwidth.setValidator(QDoubleValidator(0.0, 360.0, 1, self))
        self._site_gain.setValidator(QDoubleValidator(0.0, 60.0, 1, self))
        self._site_height.setValidator(QDoubleValidator(0.0, 200.0, 2, self))
        self._site_apply = QPushButton("Застосувати антену", self)
        self._site_apply.clicked.connect(self._apply_site_changes)
        site_layout.addRow(QLabel("Назва:"), self._site_name)
        site_layout.addRow(QLabel("Тип:"), self._site_type)
        site_layout.addRow(QLabel("Координати:"), self._site_coords)
        site_layout.addRow(QLabel("Висота:"), self._site_elevation)
        site_layout.addRow(QLabel("Нотатки:"), self._site_notes)
        site_layout.addRow(QLabel("Тип антени:"), self._site_antenna_type)
        site_layout.addRow(QLabel("Азимут:"), self._site_azimuth)
        site_layout.addRow(QLabel("Сектор (°):"), self._site_beamwidth)
        site_layout.addRow(QLabel("Підсилення (dBi):"), self._site_gain)
        site_layout.addRow(QLabel("Висота антени (м):"), self._site_height)
        site_layout.addRow(self._site_apply)

        self._link_group = QWidget(self)
        link_layout = QFormLayout(self._link_group)
        self._link_name = QLineEdit(self)
        self._link_kind = QComboBox(self)
        self._link_kind.addItem("PtP", LinkKind.PTP)
        self._link_kind.addItem("PtMP", LinkKind.PTMP)
        self._link_kind.addItem("Ethernet", LinkKind.ETHERNET)
        self._link_kind.currentIndexChanged.connect(self._toggle_link_fields)
        self._label_frequency = QLabel("Частота (ГГц):")
        self._label_ssid = QLabel("SSID:")
        self._label_password = QLabel("Пароль:")
        self._label_link_type = QLabel("Тип лінка:")
        self._label_cable_type = QLabel("Тип кабелю:")

        self._link_between = QLabel("—")
        self._link_distance = QLabel("—")
        self._link_frequency = QLineEdit(self)
        freq_validator = QDoubleValidator(0.0, 100.0, 6, self)
        freq_validator.setLocale(QLocale.c())
        self._link_frequency.setValidator(freq_validator)
        self._link_ssid = QLineEdit(self)
        self._link_password = QLineEdit(self)

        self._link_type = QComboBox(self)
        self._link_type.addItem("Fast Ethernet", LinkType.FAST_ETH)
        self._link_type.addItem("Gigabit Ethernet", LinkType.GIG_ETH)
        self._link_type.addItem("Оптика", LinkType.OPTICAL)
        self._cable_type = QComboBox(self)
        self._cable_type.addItem("Зовнішній", CableType.OUTDOOR)
        self._cable_type.addItem("Внутрішній", CableType.INDOOR)

        self._apply_btn = QPushButton("Застосувати", self)
        self._apply_btn.clicked.connect(self._apply_link_changes)
        self._analyze_btn = QPushButton("Аналіз траси", self)
        self._analyze_btn.clicked.connect(self._request_link_analysis)

        link_layout.addRow(QLabel("Назва:"), self._link_name)
        link_layout.addRow(QLabel("Тип:"), self._link_kind)
        link_layout.addRow(QLabel("Між:"), self._link_between)
        link_layout.addRow(QLabel("Дистанція:"), self._link_distance)
        link_layout.addRow(self._label_frequency, self._link_frequency)
        link_layout.addRow(self._label_ssid, self._link_ssid)
        link_layout.addRow(self._label_password, self._link_password)
        link_layout.addRow(self._label_link_type, self._link_type)
        link_layout.addRow(self._label_cable_type, self._cable_type)
        link_layout.addRow(self._apply_btn)
        link_layout.addRow(self._analyze_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self._site_group)
        layout.addWidget(self._link_group)
        self._link_group.setVisible(False)
        self._current_site_id: str | None = None

    def show_site(self, site: Site | None) -> None:
        if site is None:
            self._site_name.setText("—")
            self._site_type.setText("—")
            self._site_coords.setText("—")
            self._site_elevation.setText("—")
            self._site_notes.setText("—")
            self._site_group.setVisible(True)
            self._link_group.setVisible(False)
            self._current_link_id = None
            self._current_site_id = None
            return

        self._site_name.setText(site.name)
        self._site_type.setText(self._site_kind_label(site.kind.value))
        self._site_coords.setText(f"{site.location.lat:.6f}, {site.location.lon:.6f}")
        self._site_elevation.setText("—")
        self._site_notes.setText(f"пристроїв: {len(site.devices)}")
        antenna = site.antenna
        if antenna.antenna_type:
            idx = self._site_antenna_type.findText(antenna.antenna_type)
            if idx >= 0:
                self._site_antenna_type.setCurrentIndex(idx)
        self._site_azimuth.setText("" if antenna.azimuth_deg is None else str(antenna.azimuth_deg))
        self._site_beamwidth.setText("" if antenna.beamwidth_deg is None else str(antenna.beamwidth_deg))
        self._site_gain.setText("" if antenna.gain_dbi is None else str(antenna.gain_dbi))
        self._site_height.setText("" if antenna.height_m is None else str(antenna.height_m))
        self._site_group.setVisible(True)
        self._link_group.setVisible(False)
        self._current_link_id = None
        self._current_site_id = site.id

    def show_link(self, link: Link | None, site_a_name: str = "—", site_b_name: str = "—") -> None:
        if link is None:
            self.show_site(None)
            return
        kind_value = link.kind.value if hasattr(link.kind, "value") else str(link.kind)
        self._current_link_id = link.id
        self._link_name.setText(link.name)
        self._link_between.setText(f"{site_a_name} ↔ {site_b_name}")
        self._link_distance.setText(
            f"{link.distance_km:.2f} км" if link.distance_km is not None else "—"
        )
        self._set_kind_combo(kind_value)
        if kind_value in ("ptp", "ptmp"):
            self._link_frequency.setText("" if link.frequency_ghz is None else str(link.frequency_ghz))
            self._link_ssid.setText(link.ssid or "")
            self._link_password.setText(link.password or "")
        else:
            self._link_frequency.setText("")
            self._link_ssid.setText("")
            self._link_password.setText("")
            if link.link_type is not None:
                self._link_type.setCurrentIndex(self._link_type.findData(link.link_type))
            if link.cable_type is not None:
                self._cable_type.setCurrentIndex(self._cable_type.findData(link.cable_type))
        self._toggle_link_fields()
        self._site_group.setVisible(False)
        self._link_group.setVisible(True)
        kind_value = link.kind.value if hasattr(link.kind, "value") else str(link.kind)
        self._analyze_btn.setVisible(kind_value in ("ptp", "ptmp"))

    def set_site_elevation(self, elevation_m: float | None, available: bool = True) -> None:
        if elevation_m is None:
            self._site_elevation.setText("—" if available else "немає даних (Pillow?)")
        else:
            self._site_elevation.setText(f"{elevation_m:.1f} м")

    @staticmethod
    def _site_kind_label(kind_value: str) -> str:
        return {
            "core": "CORE",
            "pop": "POP",
            "cpe": "CPE",
        }.get(kind_value, kind_value)

    def _set_kind_combo(self, kind_value: str) -> None:
        for i in range(self._link_kind.count()):
            kind = self._link_kind.itemData(i)
            if isinstance(kind, LinkKind) and kind.value == kind_value:
                self._link_kind.setCurrentIndex(i)
                return

    def _toggle_link_fields(self) -> None:
        kind = self._link_kind.currentData()
        is_wireless = kind in (LinkKind.PTP, LinkKind.PTMP)
        for widget in (
            self._label_frequency,
            self._link_frequency,
            self._label_ssid,
            self._link_ssid,
            self._label_password,
            self._link_password,
        ):
            widget.setVisible(is_wireless)
        for widget in (self._label_link_type, self._link_type, self._label_cable_type, self._cable_type):
            widget.setVisible(not is_wireless)

    def _apply_link_changes(self) -> None:
        if self._current_link_id is None:
            return
        kind = self._link_kind.currentData()
        if kind is None:
            QMessageBox.warning(self, "Помилка", "Тип не може бути порожнім.")
            return
        if kind in (LinkKind.PTP, LinkKind.PTMP):
            freq_text = self._link_frequency.text().strip()
            if freq_text:
                try:
                    float(freq_text)
                except ValueError:
                    QMessageBox.warning(self, "Помилка", "Частота повинна бути числом.")
                    return
        is_wireless = kind in (LinkKind.PTP, LinkKind.PTMP)
        payload = {
            "name": self._link_name.text().strip() or "Лінк",
            "kind": kind,
            "frequency_ghz": float(self._link_frequency.text()) if is_wireless and self._link_frequency.text().strip() else None,
            "ssid": self._link_ssid.text().strip() if is_wireless else None,
            "password": self._link_password.text().strip() if is_wireless else None,
            "link_type": None if is_wireless else self._link_type.currentData(),
            "cable_type": None if is_wireless else self._cable_type.currentData(),
        }
        self.link_updated.emit(self._current_link_id, payload)

    def _request_link_analysis(self) -> None:
        if self._current_link_id is None:
            return
        self.link_analyze_requested.emit(self._current_link_id)

    def _apply_site_changes(self) -> None:
        if self._current_site_id is None:
            return
        payload = {
            "antenna_type": self._site_antenna_type.currentText(),
            "azimuth_deg": float(self._site_azimuth.text()) if self._site_azimuth.text().strip() else None,
            "beamwidth_deg": float(self._site_beamwidth.text()) if self._site_beamwidth.text().strip() else None,
            "gain_dbi": float(self._site_gain.text()) if self._site_gain.text().strip() else None,
            "height_m": float(self._site_height.text()) if self._site_height.text().strip() else None,
        }
        self.site_updated.emit(self._current_site_id, payload)
