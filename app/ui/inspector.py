from __future__ import annotations

import math

from PySide6.QtCore import Signal, QLocale, QSignalBlocker
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.coverage import CoverageCalculator
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
        self._site_name = QLineEdit(self)
        self._site_name.setReadOnly(True)
        self._site_type = QComboBox(self)
        self._site_type.addItem("CORE", SiteKind.CORE)
        self._site_type.addItem("POP", SiteKind.POP)
        self._site_type.addItem("CPE", SiteKind.CPE)
        self._site_lat = QLineEdit(self)
        self._site_lon = QLineEdit(self)
        self._site_elevation = QLabel("—")
        self._site_notes = QLabel("—")
        self._site_antenna_type = QComboBox(self)
        self._site_antenna_type.addItems(["omni", "sector", "directional"])
        self._site_azimuth = QLineEdit(self)
        self._site_beamwidth = QLineEdit(self)
        self._site_gain = QLineEdit(self)
        self._site_height = QLineEdit(self)
        self._site_frequency = QLineEdit(self)
        self._site_tx_power = QLineEdit(self)
        self._site_rx_gain = QLineEdit(self)
        self._site_rx_height = QLineEdit(self)
        self._site_rx_sens = QLineEdit(self)
        self._site_misc_losses = QLineEdit(self)
        self._site_margin = QLineEdit(self)
        self._site_mcs = QComboBox(self)
        self._calc_distance = QLineEdit(self)
        self._calc_fspl = QLineEdit(self)
        self._calc_required_eirp = QLineEdit(self)
        self._calc_eirp_ok = QLineEdit(self)
        self._site_azimuth.setValidator(QDoubleValidator(0.0, 360.0, 1, self))
        self._site_beamwidth.setValidator(QDoubleValidator(0.0, 360.0, 1, self))
        self._site_gain.setValidator(QDoubleValidator(0.0, 60.0, 1, self))
        self._site_height.setValidator(QDoubleValidator(0.0, 200.0, 2, self))
        self._site_lat.setValidator(QDoubleValidator(-90.0, 90.0, 6, self))
        self._site_lon.setValidator(QDoubleValidator(-180.0, 180.0, 6, self))
        freq_validator = QDoubleValidator(1.0, 100000.0, 3, self)
        freq_validator.setLocale(QLocale.c())
        self._site_frequency.setValidator(freq_validator)
        power_validator = QDoubleValidator(-60.0, 60.0, 2, self)
        power_validator.setLocale(QLocale.c())
        self._site_tx_power.setValidator(power_validator)
        gain_validator = QDoubleValidator(0.0, 60.0, 1, self)
        gain_validator.setLocale(QLocale.c())
        self._site_rx_gain.setValidator(gain_validator)
        rx_height_validator = QDoubleValidator(0.0, 200.0, 2, self)
        rx_height_validator.setLocale(QLocale.c())
        self._site_rx_height.setValidator(rx_height_validator)
        sens_validator = QDoubleValidator(-150.0, -30.0, 2, self)
        sens_validator.setLocale(QLocale.c())
        self._site_rx_sens.setValidator(sens_validator)
        loss_validator = QDoubleValidator(0.0, 60.0, 2, self)
        loss_validator.setLocale(QLocale.c())
        self._site_misc_losses.setValidator(loss_validator)
        margin_validator = QDoubleValidator(0.0, 40.0, 2, self)
        margin_validator.setLocale(QLocale.c())
        self._site_margin.setValidator(margin_validator)
        dist_validator = QDoubleValidator(0.1, 300.0, 2, self)
        dist_validator.setLocale(QLocale.c())
        self._calc_distance.setValidator(dist_validator)
        self._calc_fspl.setReadOnly(True)
        self._calc_required_eirp.setReadOnly(True)
        self._calc_required_eirp.setVisible(False)
        self._calc_eirp_ok.setReadOnly(True)
        self._site_apply = QPushButton("Застосувати антену", self)
        self._site_apply.clicked.connect(self._apply_site_changes)
        self._site_apply_basic = QPushButton("Застосувати сайт", self)
        self._site_apply_basic.clicked.connect(self._apply_site_basic_changes)
        self._site_frequency.textChanged.connect(self._update_eirp_calculator)
        self._calc_distance.textChanged.connect(self._update_eirp_calculator)
        self._site_rx_sens.textChanged.connect(self._update_eirp_calculator)
        self._site_rx_gain.textChanged.connect(self._update_eirp_calculator)
        self._site_misc_losses.textChanged.connect(self._update_eirp_calculator)
        self._site_margin.textChanged.connect(self._update_eirp_calculator)
        self._site_rx_height.textChanged.connect(self._update_eirp_calculator)
        for field in (
            self._site_azimuth,
            self._site_beamwidth,
            self._site_gain,
            self._site_height,
            self._site_lat,
            self._site_lon,
            self._site_frequency,
            self._site_tx_power,
            self._site_rx_gain,
            self._site_rx_height,
            self._site_rx_sens,
            self._site_misc_losses,
            self._site_margin,
            self._calc_distance,
        ):
            field.textChanged.connect(lambda _text, f=field: self._normalize_decimal(f))
        label_name = QLabel("Назва:")
        label_type = QLabel("Тип:")
        label_lat = QLabel("Широта:")
        label_lon = QLabel("Довгота:")
        label_elevation = QLabel("Висота:")
        label_notes = QLabel("Нотатки:")
        label_antenna = QLabel("Тип антени:")
        label_azimuth = QLabel("Азимут:")
        label_beamwidth = QLabel("Сектор (°):")
        label_gain = QLabel("Підсилення (dBi):")
        label_height = QLabel("Висота антени (м):")
        label_frequency = QLabel("Частота (МГц):")
        label_tx_power = QLabel("Потужність TX (dBm):")
        label_rx_gain = QLabel("Підсилення RX (dBi):")
        label_rx_height = QLabel("Висота RX (м):")
        label_rx_sens = QLabel("Чутливість RX (dBm):")
        label_losses = QLabel("Втрати (дБ):")
        label_margin = QLabel("Margin (дБ):")
        label_mcs = QLabel("MCS:")
        label_calc_distance = QLabel("Дистанція (км):")
        label_calc_fspl = QLabel("Втрати FSPL (дБ):")
        label_calc_ok = QLabel("EIRP OK:")

        label_rx_sens.setToolTip("Параметр береться зі специфікації пристрою (RX sensitivity).")
        label_rx_gain.setToolTip("Підсилення приймальної антени зі специфікації.")
        label_rx_height.setToolTip("Висота приймальної антени над землею.")
        label_losses.setToolTip("Втрати на АФТ: кабель, конектори, грозозахист, роз'єми.")
        label_margin.setToolTip(
            "Запас лінку (fade margin) на завади/погоду/деградацію.\n"
            "Зазвичай 5–15 дБ."
        )
        label_mcs.setToolTip(
            "Обери MCS зі специфікації. Чутливість RX залежить від MCS.\n"
            "Після вибору внеси RX sensitivity зі специфікації."
        )
        label_calc_distance.setToolTip("Введи відому дистанцію для оцінки втрат у вільному просторі.")
        label_calc_fspl.setToolTip(
            "FSPL = 92.45 + 20·log10(d_km) + 20·log10(f_GHz)\n"
            "f_GHz = f_MHz / 1000"
        )
        label_calc_ok.setToolTip("Наведи курсор, щоб побачити фактичне/потрібне EIRP.")

        self._site_mcs.addItem("Auto", None)
        for idx in range(0, 13):
            self._site_mcs.addItem(f"MCS {idx}", f"mcs{idx}")

        site_layout.addRow(label_name, self._site_name)
        site_layout.addRow(label_type, self._site_type)
        site_layout.addRow(label_lat, self._site_lat)
        site_layout.addRow(label_lon, self._site_lon)
        site_layout.addRow(label_elevation, self._site_elevation)
        site_layout.addRow(label_notes, self._site_notes)
        site_layout.addRow(label_antenna, self._site_antenna_type)
        site_layout.addRow(label_azimuth, self._site_azimuth)
        site_layout.addRow(label_beamwidth, self._site_beamwidth)
        site_layout.addRow(label_gain, self._site_gain)
        site_layout.addRow(label_height, self._site_height)
        site_layout.addRow(label_frequency, self._site_frequency)
        site_layout.addRow(label_tx_power, self._site_tx_power)
        site_layout.addRow(label_mcs, self._site_mcs)
        site_layout.addRow(label_rx_gain, self._site_rx_gain)
        site_layout.addRow(label_rx_height, self._site_rx_height)
        site_layout.addRow(label_rx_sens, self._site_rx_sens)
        site_layout.addRow(label_losses, self._site_misc_losses)
        site_layout.addRow(label_margin, self._site_margin)
        site_layout.addRow(label_calc_distance, self._calc_distance)
        site_layout.addRow(label_calc_fspl, self._calc_fspl)
        site_layout.addRow(label_calc_ok, self._calc_eirp_ok)
        site_layout.addRow(self._site_apply_basic)
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
        self._link_notes = QLineEdit(self)

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
        link_layout.addRow(QLabel("Нотатки:"), self._link_notes)
        link_layout.addRow(self._label_link_type, self._link_type)
        link_layout.addRow(self._label_cable_type, self._cable_type)
        link_layout.addRow(self._apply_btn)
        link_layout.addRow(self._analyze_btn)

        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self._site_group)
        content_layout.addWidget(self._link_group)
        content_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        self._link_group.setVisible(False)
        self._current_site_id: str | None = None

    def show_site(self, site: Site | None) -> None:
        if site is None:
            self._site_name.setText("")
            self._site_type.setCurrentIndex(0)
            self._site_lat.setText("")
            self._site_lon.setText("")
            self._site_elevation.setText("—")
            self._site_notes.setText("—")
            self._calc_distance.setText("")
            self._calc_fspl.setText("")
            self._calc_required_eirp.setText("")
            self._calc_eirp_ok.setText("")
            self._site_group.setVisible(True)
            self._link_group.setVisible(False)
            self._current_link_id = None
            self._current_site_id = None
            return

        self._site_name.setText(site.name)
        type_idx = self._site_type.findData(site.kind)
        if type_idx >= 0:
            self._site_type.setCurrentIndex(type_idx)
        self._site_lat.setText(f"{site.location.lat:.6f}")
        self._site_lon.setText(f"{site.location.lon:.6f}")
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
        if antenna.frequency_ghz is None:
            self._site_frequency.setText("")
        else:
            self._site_frequency.setText(f"{antenna.frequency_ghz * 1000.0:.3f}")
        self._site_tx_power.setText("" if antenna.tx_power_dbm is None else str(antenna.tx_power_dbm))
        self._site_rx_gain.setText("" if antenna.rx_gain_dbi is None else str(antenna.rx_gain_dbi))
        self._site_rx_height.setText("" if antenna.rx_height_m is None else str(antenna.rx_height_m))
        if antenna.mcs:
            idx = self._site_mcs.findData(antenna.mcs)
            if idx >= 0:
                self._site_mcs.setCurrentIndex(idx)
        else:
            self._site_mcs.setCurrentIndex(0)
        rx_sens = CoverageCalculator.rx_sensitivity_dbm(antenna)
        self._site_rx_sens.setText("" if rx_sens is None else f"{rx_sens:.2f}")
        self._site_misc_losses.setText("" if antenna.misc_losses_db is None else str(antenna.misc_losses_db))
        self._site_margin.setText("" if antenna.link_margin_db is None else str(antenna.link_margin_db))
        self._update_eirp_calculator()
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
        self._link_notes.setText(link.notes_text or "")
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
            "notes_text": self._link_notes.text().strip() or None,
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
            "frequency_ghz": self._mhz_to_ghz(self._site_frequency.text()),
            "tx_power_dbm": float(self._site_tx_power.text()) if self._site_tx_power.text().strip() else None,
            "mcs": self._site_mcs.currentData(),
            "rx_gain_dbi": float(self._site_rx_gain.text()) if self._site_rx_gain.text().strip() else None,
            "rx_height_m": float(self._site_rx_height.text()) if self._site_rx_height.text().strip() else None,
            "rx_sensitivity_dbm": float(self._site_rx_sens.text()) if self._site_rx_sens.text().strip() else None,
            "misc_losses_db": float(self._site_misc_losses.text()) if self._site_misc_losses.text().strip() else None,
            "link_margin_db": float(self._site_margin.text()) if self._site_margin.text().strip() else None,
        }
        self.site_updated.emit(self._current_site_id, payload)

    def _apply_site_basic_changes(self) -> None:
        if self._current_site_id is None:
            return
        payload = {
            "kind": self._site_type.currentData(),
            "lat": float(self._site_lat.text()) if self._site_lat.text().strip() else None,
            "lon": float(self._site_lon.text()) if self._site_lon.text().strip() else None,
        }
        self.site_updated.emit(self._current_site_id, payload)

    def _update_eirp_calculator(self) -> None:
        freq_text = self._site_frequency.text().strip()
        dist_text = self._calc_distance.text().strip()
        rx_sens_text = self._site_rx_sens.text().strip()
        rx_gain_text = self._site_rx_gain.text().strip()
        losses_text = self._site_misc_losses.text().strip()
        margin_text = self._site_margin.text().strip()
        try:
            freq_mhz = float(freq_text) if freq_text else None
            dist = float(dist_text) if dist_text else None
            rx_sens = float(rx_sens_text) if rx_sens_text else None
            rx_gain = float(rx_gain_text) if rx_gain_text else 0.0
            losses = float(losses_text) if losses_text else 0.0
            margin = float(margin_text) if margin_text else 0.0
        except ValueError:
            self._calc_fspl.setText("")
            self._calc_required_eirp.setText("")
            self._calc_eirp_ok.setText("")
            self._calc_eirp_ok.setToolTip("")
            return
        if not freq_mhz or not dist or rx_sens is None:
            self._calc_fspl.setText("")
            self._calc_required_eirp.setText("")
            self._calc_eirp_ok.setText("")
            self._calc_eirp_ok.setToolTip("")
            return
        freq = freq_mhz / 1000.0
        fspl = 92.45 + 20.0 * math.log10(dist) + 20.0 * math.log10(freq)
        required_eirp = rx_sens + margin + fspl + losses - rx_gain
        self._calc_fspl.setText(f"{fspl:.2f}")
        self._calc_required_eirp.setText(f"{required_eirp:.2f}")
        tx_gain_text = self._site_gain.text().strip()
        tx_power_text = self._site_tx_power.text().strip()
        try:
            tx_gain = float(tx_gain_text) if tx_gain_text else 0.0
            tx_power = float(tx_power_text) if tx_power_text else None
        except ValueError:
            tx_power = None
        if tx_power is None:
            self._calc_eirp_ok.setText("")
            self._calc_eirp_ok.setToolTip("")
            return
        actual_eirp = tx_power + tx_gain - losses # type: ignore
        ok = actual_eirp >= required_eirp
        self._calc_eirp_ok.setText("Так" if ok else "Ні")
        self._calc_eirp_ok.setToolTip(
            f"EIRP_actual: {actual_eirp:.2f} dBm\nEIRP_required: {required_eirp:.2f} dBm"
        )

    @staticmethod
    def _normalize_decimal(field: QLineEdit) -> None:
        text = field.text()
        if "," not in text:
            return
        new_text = text.replace(",", ".")
        if new_text == text:
            return
        cursor_pos = field.cursorPosition()
        with QSignalBlocker(field):
            field.setText(new_text)
        field.setCursorPosition(cursor_pos)

    @staticmethod
    def _mhz_to_ghz(text: str) -> float | None:
        value = text.strip()
        if not value:
            return None
        try:
            mhz = float(value)
        except ValueError:
            return None
        if mhz <= 0:
            return None
        return mhz / 1000.0
