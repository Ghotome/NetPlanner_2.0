from __future__ import annotations

import math
from uuid import uuid4

from PySide6.QtCore import Signal, QLocale, QSignalBlocker, Qt
from PySide6.QtGui import QDoubleValidator, QValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.domain import AntennaParams, CableType, Link, LinkKind, LinkType, Site, SiteKind


ANTENNA_PRESETS: dict[str, dict[str, float | str | None]] = {
    "dmr": {
        "channel_width_mhz": 0.0125,
        "rx_sensitivity_dbm": -120.0,
        "noise_figure_db": 7.0,
        "required_sinr_db": 9.0,
        "link_margin_db": 12.0,
        "mcs": None,
    },
    "voice_analog": {
        "channel_width_mhz": 0.0125,
        "rx_sensitivity_dbm": -118.0,
        "noise_figure_db": 7.0,
        "required_sinr_db": 12.0,
        "link_margin_db": 12.0,
        "mcs": None,
    },
    "analog_vtx": {
        "channel_width_mhz": 20.0,
        "rx_sensitivity_dbm": -90.0,
        "noise_figure_db": 8.0,
        "required_sinr_db": 12.0,
        "link_margin_db": 16.0,
        "mcs": None,
    },
    "analog_telemetry": {
        "channel_width_mhz": 0.0125,
        "rx_sensitivity_dbm": -119.0,
        "noise_figure_db": 7.0,
        "required_sinr_db": 7.0,
        "link_margin_db": 10.0,
        "mcs": None,
    },
    "digital_video_telemetry": {
        "channel_width_mhz": 20.0,
        "rx_sensitivity_dbm": -88.0,
        "noise_figure_db": 8.0,
        "required_sinr_db": 16.0,
        "link_margin_db": 14.0,
        "mcs": None,
    },
    "wifi_2_4": {
        "channel_width_mhz": 20.0,
        "rx_sensitivity_dbm": -90.0,
        "noise_figure_db": 8.0,
        "required_sinr_db": 18.0,
        "link_margin_db": 10.0,
        "mcs": None,
    },
    "wifi_5_8": {
        "channel_width_mhz": 20.0,
        "rx_sensitivity_dbm": -87.0,
        "noise_figure_db": 8.0,
        "required_sinr_db": 20.0,
        "link_margin_db": 10.0,
        "mcs": None,
    },
}

ANTENNA_TYPE_DEFAULTS: dict[str, dict[str, float]] = {
    "omni": {"azimuth_deg": 0.0, "beamwidth_deg": 360.0},
    "sector": {"azimuth_deg": 0.0, "beamwidth_deg": 120.0},
    "directional": {"azimuth_deg": 0.0, "beamwidth_deg": 35.0},
}


class AntennaBlock(QWidget):
    apply_requested = Signal(str, dict)
    delete_requested = Signal(str)
    validity_changed = Signal(bool)
    copy_requested = Signal(dict)

    def __init__(self, antenna: AntennaParams | None, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.antenna_id = antenna.id if antenna else uuid4().hex[:8]
        self._index = index
        self._applied = antenna.applied if antenna else False
        self._is_valid = True
        self._initializing = True
        self._field_error_labels: dict[QLineEdit, QLabel] = {}
        self._field_error_messages: dict[QLineEdit, str] = {}

        self._toggle_btn = QToolButton(self)
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(True)
        self._toggle_btn.setArrowType(Qt.ArrowType.DownArrow)
        self._toggle_btn.clicked.connect(self._toggle_content)

        self._name = QLineEdit(self)
        name_value = antenna.name if antenna and antenna.name else f"Антена {index}"
        self._name.setText(name_value)

        header = QHBoxLayout()
        header.addWidget(self._toggle_btn)
        header.addWidget(QLabel("Назва:", self))
        header.addWidget(self._name, 1)

        self._content = QWidget(self)
        form = QFormLayout(self._content)

        def add_hint(text: str) -> None:
            hint = QLabel(text, self)
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #9aa0a6; font-size: 11px;")
            form.addRow(QLabel(""), hint)

        def add_error(field: QLineEdit, text: str) -> None:
            left = QLabel("", self)
            left.hide()
            label = QLabel("", self)
            label.setWordWrap(True)
            label.setStyleSheet("color: #dc2626; font-size: 11px;")
            label.hide()
            form.addRow(left, label)
            self._field_error_labels[field] = label
            self._field_error_messages[field] = text

        self._antenna_type = QComboBox(self)
        self._antenna_type.addItems(["omni", "sector", "directional"])
        if antenna is None:
            idx = self._antenna_type.findText("sector")
            if idx >= 0:
                self._antenna_type.setCurrentIndex(idx)
        self._azimuth = QLineEdit(self)
        self._beamwidth = QLineEdit(self)
        self._gain = QLineEdit(self)
        self._height = QLineEdit(self)
        self._frequency = QLineEdit(self)
        self._tx_power = QLineEdit(self)
        self._rx_gain = QLineEdit(self)
        self._rx_height = QLineEdit(self)
        self._rx_sens = QLineEdit(self)
        self._channel_width = QLineEdit(self)
        self._noise_figure = QLineEdit(self)
        self._required_sinr = QLineEdit(self)
        self._losses = QLineEdit(self)
        self._margin = QLineEdit(self)
        self._mcs = QComboBox(self)
        self._preset = QComboBox(self)
        self._calc_distance = QLineEdit(self)
        self._calc_fspl = QLineEdit(self)
        self._calc_required = QLineEdit(self)
        self._calc_ok = QLineEdit(self)

        self._calc_fspl.setReadOnly(True)
        self._calc_required.setReadOnly(True)
        self._calc_required.setVisible(False)
        self._calc_ok.setReadOnly(True)

        az_validator = QDoubleValidator(0.0, 360.0, 1, self)
        az_validator.setLocale(QLocale.c())
        self._azimuth.setValidator(az_validator)
        bw_validator = QDoubleValidator(0.0, 360.0, 1, self)
        bw_validator.setLocale(QLocale.c())
        self._beamwidth.setValidator(bw_validator)
        gain_tx_validator = QDoubleValidator(0.0, 60.0, 1, self)
        gain_tx_validator.setLocale(QLocale.c())
        self._gain.setValidator(gain_tx_validator)
        height_tx_validator = QDoubleValidator(0.0, 8000.0, 2, self)
        height_tx_validator.setLocale(QLocale.c())
        self._height.setValidator(height_tx_validator)
        freq_validator = QDoubleValidator(0.1, 30000.0, 3, self)
        freq_validator.setLocale(QLocale.c())
        self._frequency.setValidator(freq_validator)
        power_validator = QDoubleValidator(-60.0, 60.0, 2, self)
        power_validator.setLocale(QLocale.c())
        self._tx_power.setValidator(power_validator)
        gain_validator = QDoubleValidator(0.0, 60.0, 1, self)
        gain_validator.setLocale(QLocale.c())
        self._rx_gain.setValidator(gain_validator)
        rx_height_validator = QDoubleValidator(0.0, 8000.0, 2, self)
        rx_height_validator.setLocale(QLocale.c())
        self._rx_height.setValidator(rx_height_validator)
        sens_validator = QDoubleValidator(-150.0, -30.0, 2, self)
        sens_validator.setLocale(QLocale.c())
        self._rx_sens.setValidator(sens_validator)
        ch_validator = QDoubleValidator(0.0001, 2000.0, 4, self)
        ch_validator.setLocale(QLocale.c())
        self._channel_width.setValidator(ch_validator)
        nf_validator = QDoubleValidator(0.0, 30.0, 2, self)
        nf_validator.setLocale(QLocale.c())
        self._noise_figure.setValidator(nf_validator)
        sinr_validator = QDoubleValidator(-20.0, 50.0, 2, self)
        sinr_validator.setLocale(QLocale.c())
        self._required_sinr.setValidator(sinr_validator)
        loss_validator = QDoubleValidator(0.0, 60.0, 2, self)
        loss_validator.setLocale(QLocale.c())
        self._losses.setValidator(loss_validator)
        margin_validator = QDoubleValidator(0.0, 40.0, 2, self)
        margin_validator.setLocale(QLocale.c())
        self._margin.setValidator(margin_validator)
        dist_validator = QDoubleValidator(0.1, 300.0, 2, self)
        dist_validator.setLocale(QLocale.c())
        self._calc_distance.setValidator(dist_validator)

        self._mcs.addItem("Auto", None)
        for idx in range(0, 13):
            self._mcs.addItem(f"MCS {idx}", f"mcs{idx}")
        self._preset.addItem("Власні параметри", None)
        self._preset.addItem("DMR", "dmr")
        self._preset.addItem("Voice analog", "voice_analog")
        self._preset.addItem("Analog VTX", "analog_vtx")
        self._preset.addItem("Analog telemetry", "analog_telemetry")
        self._preset.addItem("Digital video & telemetry", "digital_video_telemetry")
        self._preset.addItem("WiFi 2.4 GHz", "wifi_2_4")
        self._preset.addItem("WiFi 5.8 GHz", "wifi_5_8")
        self._preset.currentIndexChanged.connect(self._apply_selected_preset)
        self._antenna_type.currentIndexChanged.connect(self._on_antenna_type_changed)

        label_preset = QLabel("Пресет:")
        label_rx_sens = QLabel("Чутливість RX (dBm):")
        label_channel_width = QLabel("Ширина каналу (МГц):")
        label_noise_figure = QLabel("Noise Figure (дБ):")
        label_required_sinr = QLabel("Поріг SINR (дБ):")
        label_rx_gain = QLabel("Підсилення RX (dBi):")
        label_rx_height = QLabel("Висота RX (м):")
        label_losses = QLabel("Втрати АФТ (дБ):")
        label_margin = QLabel("Закладені втрати (дБ):")
        label_mcs = QLabel("MCS:")
        label_calc_distance = QLabel("Потрібна дистанція (км):")
        label_calc_fspl = QLabel("Втрати FSPL (дБ):")
        label_calc_ok = QLabel("EIRP OK:")

        label_rx_sens.setToolTip("Параметр береться зі специфікації пристрою (RX sensitivity).")
        label_channel_width.setToolTip(
            "Ширина каналу для корекції чутливості RX.\n"
            "Корекція робиться відносно 20 МГц.\n"
            "Приклад: 20/40/60 МГц для Wi‑Fi, 0.0125 МГц для DMR.\n"
            "ELRS: 0.5/1.0/2.0 МГц для 2.4 ГГц."
            "Analog VTX: 6.25/12.5 МГц для 5.8 ГГц.\n"
            "Детальніше дивиться у специфікації пристрою."
        )
        label_noise_figure.setToolTip(
            "Noise Figure приймача (NF). Якщо немає в специфікації, "
            "використовуй пресет або типове значення 6–9 дБ."
        )
        label_required_sinr.setToolTip(
            "Мінімальний SINR, за якого приймач стабільно декодує сигнал "
            "(для обраного режиму/модуляції)."
        )
        label_rx_gain.setToolTip("Підсилення приймальної антени зі специфікації.")
        label_rx_height.setToolTip("Висота приймальної антени над землею.")
        label_losses.setToolTip("Втрати на АФТ: кабель, конектори, грозозахист, роз'єми.")
        label_margin.setToolTip(
            "Запас лінку (fade margin) на завади/погоду/деградацію.\n"
            "Зазвичай 5–15 дБ.\n"
            "Типові значення:\n"
            "Погода: 5–10 дБ (помірно), 10–20 дБ (складно).\n"
        )
        label_mcs.setToolTip(
            "Обери MCS зі специфікації. Чутливість RX залежить від MCS.\n"
            "Після вибору внеси RX sensitivity зі специфікації."
        )
        label_preset.setToolTip(
            "Пресет заповнює поля орієнтовними консервативними параметрами.\n"
            "Для точного розрахунку індивідуальні значення для кожного пристрою "
            "потрібно вводити вручну зі специфікації."
        )
        self._preset.setToolTip(label_preset.toolTip())
        label_calc_distance.setToolTip("Введи відому дистанцію до приймача для оцінки FSPL та EIRP.")
        label_calc_fspl.setToolTip(
            "Затухання сигналу у вільному просторі (Free Space Path Loss) на введеній дистанції."
        )
        label_calc_ok.setToolTip("EIRP OK, якщо потужність передавача достатня для покриття дистанції.")

        form.addRow(label_preset, self._preset)
        form.addRow(QLabel("Тип антени:"), self._antenna_type)
        form.addRow(QLabel("Азимут:"), self._azimuth)
        add_hint("Діапазон: 0–360°.")
        add_error(self._azimuth, "Діапазон 0–360°.")
        form.addRow(QLabel("Сектор випромінення(°):"), self._beamwidth)
        add_hint("Діапазон: 0–360°.")
        add_error(self._beamwidth, "Діапазон 0–360°.")
        form.addRow(QLabel("Підсилення TX (dBi):"), self._gain)
        add_hint("Діапазон: 0–60 dBi.")
        add_error(self._gain, "Діапазон 0–60 dBi.")
        form.addRow(QLabel("Висота антени TX (м):"), self._height)
        add_hint("Діапазон: 0–8000 м.")
        add_error(self._height, "Діапазон 0–8000 м.")
        form.addRow(QLabel("Частота TX (МГц):"), self._frequency)
        add_hint("Діапазон: 0.1–30000 МГц.")
        add_error(self._frequency, "Очікується МГц у діапазоні 0.1–30000.")
        form.addRow(QLabel("Потужність TX (dBm):"), self._tx_power)
        add_hint("Діапазон: -60…60 dBm.")
        add_error(self._tx_power, "Діапазон -60…60 dBm.")
        form.addRow(label_mcs, self._mcs)
        form.addRow(label_rx_gain, self._rx_gain)
        add_hint("Діапазон: 0–60 dBi.")
        add_error(self._rx_gain, "Діапазон 0–60 dBi.")
        form.addRow(label_rx_height, self._rx_height)
        add_hint("Діапазон: 0–8000 м.")
        add_error(self._rx_height, "Діапазон 0–8000 м.")
        form.addRow(label_rx_sens, self._rx_sens)
        add_hint("Діапазон: -150…-30 dBm.")
        add_error(self._rx_sens, "Діапазон -150…-30 dBm.")
        form.addRow(label_channel_width, self._channel_width)
        add_hint("Діапазон: 0.001–2000 МГц.")
        add_error(self._channel_width, "Діапазон 0.001–2000 МГц.")
        form.addRow(label_noise_figure, self._noise_figure)
        add_hint("Діапазон: 0–30 dB.")
        add_error(self._noise_figure, "Діапазон 0–30 dB.")
        form.addRow(label_required_sinr, self._required_sinr)
        add_hint("Діапазон: -20…50 dB.")
        add_error(self._required_sinr, "Діапазон -20…50 dB.")
        form.addRow(label_losses, self._losses)
        add_hint("Діапазон: 0–60 dB.")
        add_error(self._losses, "Діапазон 0–60 dB.")
        form.addRow(label_margin, self._margin)
        add_hint("Діапазон: 0–40 dB.")
        add_error(self._margin, "Діапазон 0–40 dB.")
        form.addRow(label_calc_distance, self._calc_distance)
        add_hint("Діапазон: 0.1–300 км.")
        add_error(self._calc_distance, "Діапазон 0.1–300 км.")
        form.addRow(label_calc_fspl, self._calc_fspl)
        form.addRow(label_calc_ok, self._calc_ok)

        self._apply_btn = QPushButton("Застосувати антену", self)
        self._apply_btn.clicked.connect(self._emit_apply)
        form.addRow(self._apply_btn)

        self._copy_btn = QPushButton("Копіювати антену", self)
        self._copy_btn.clicked.connect(self._emit_copy)
        form.addRow(self._copy_btn)

        self._delete_btn = QPushButton("Видалити антену", self)
        self._delete_btn.clicked.connect(self._emit_delete)
        form.addRow(self._delete_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self._content)
        self.setLayout(layout)

        for field in (
            self._azimuth,
            self._beamwidth,
            self._gain,
            self._height,
            self._frequency,
            self._tx_power,
            self._rx_gain,
            self._rx_height,
            self._rx_sens,
            self._channel_width,
            self._noise_figure,
            self._required_sinr,
            self._losses,
            self._margin,
            self._calc_distance,
        ):
            field.textChanged.connect(lambda _text, f=field: self._normalize_decimal(f))
            field.textChanged.connect(self._validate_inputs)

        for field in (
            self._frequency,
            self._calc_distance,
            self._rx_sens,
            self._rx_gain,
            self._losses,
            self._margin,
        ):
            field.textChanged.connect(self._update_eirp_calculator)

        if antenna is not None:
            if antenna.antenna_type:
                idx = self._antenna_type.findText(antenna.antenna_type)
                if idx >= 0:
                    self._antenna_type.setCurrentIndex(idx)
            self._azimuth.setText("" if antenna.azimuth_deg is None else str(antenna.azimuth_deg))
            self._beamwidth.setText("" if antenna.beamwidth_deg is None else str(antenna.beamwidth_deg))
            self._gain.setText("" if antenna.gain_dbi is None else str(antenna.gain_dbi))
            self._height.setText("" if antenna.height_m is None else str(antenna.height_m))
            if antenna.frequency_ghz is not None:
                self._frequency.setText(f"{antenna.frequency_ghz * 1000.0:.3f}")
            self._tx_power.setText("" if antenna.tx_power_dbm is None else str(antenna.tx_power_dbm))
            self._rx_gain.setText("" if antenna.rx_gain_dbi is None else str(antenna.rx_gain_dbi))
            self._rx_height.setText("" if antenna.rx_height_m is None else str(antenna.rx_height_m))
            if antenna.mcs:
                idx = self._mcs.findData(antenna.mcs)
                if idx >= 0:
                    self._mcs.setCurrentIndex(idx)
            self._rx_sens.setText(
                "" if antenna.rx_sensitivity_dbm is None else f"{antenna.rx_sensitivity_dbm:.2f}"
            )
            if antenna.channel_width_mhz is not None:
                text = f"{antenna.channel_width_mhz:.4f}".rstrip("0").rstrip(".")
                self._channel_width.setText(text)
            self._noise_figure.setText("" if antenna.noise_figure_db is None else str(antenna.noise_figure_db))
            self._required_sinr.setText("" if antenna.required_sinr_db is None else str(antenna.required_sinr_db))
            self._losses.setText("" if antenna.misc_losses_db is None else str(antenna.misc_losses_db))
            self._margin.setText("" if antenna.link_margin_db is None else str(antenna.link_margin_db))
            self._update_eirp_calculator()
            if antenna.azimuth_deg is None or antenna.beamwidth_deg is None:
                self._apply_antenna_type_defaults(force=False)
        else:
            self._apply_antenna_type_defaults(force=True)
        self._initializing = False
        self._validate_inputs()

    def _apply_selected_preset(self) -> None:
        preset_key = self._preset.currentData()
        if not isinstance(preset_key, str):
            return
        preset = ANTENNA_PRESETS.get(preset_key)
        if not isinstance(preset, dict):
            return
        mcs_value = preset.get("mcs")
        with QSignalBlocker(self._mcs):
            mcs_idx = self._mcs.findData(mcs_value)
            if mcs_idx >= 0:
                self._mcs.setCurrentIndex(mcs_idx)
        self._set_float_field(self._rx_sens, preset.get("rx_sensitivity_dbm"))
        self._set_float_field(self._channel_width, preset.get("channel_width_mhz"), max_precision=4)
        self._set_float_field(self._noise_figure, preset.get("noise_figure_db"))
        self._set_float_field(self._required_sinr, preset.get("required_sinr_db"))
        self._set_float_field(self._margin, preset.get("link_margin_db"))
        self._validate_inputs()
        self._update_eirp_calculator()

    def _toggle_content(self) -> None:
        expanded = self._toggle_btn.isChecked()
        self._content.setVisible(expanded)
        self._toggle_btn.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def _on_antenna_type_changed(self) -> None:
        if self._initializing:
            return
        self._apply_antenna_type_defaults(force=True)
        self._validate_inputs()

    def _apply_antenna_type_defaults(self, *, force: bool) -> None:
        defaults = ANTENNA_TYPE_DEFAULTS.get(self._antenna_type.currentText())
        if defaults is None:
            return
        if force or not self._azimuth.text().strip():
            self._set_float_field(self._azimuth, defaults["azimuth_deg"], max_precision=1)
        if force or not self._beamwidth.text().strip():
            self._set_float_field(self._beamwidth, defaults["beamwidth_deg"], max_precision=1)

    def _emit_apply(self) -> None:
        self._applied = True
        payload = self.to_payload()
        payload["applied"] = True
        self.apply_requested.emit(self.antenna_id, payload)

    def _emit_delete(self) -> None:
        self.delete_requested.emit(self.antenna_id)

    def _emit_copy(self) -> None:
        payload = self.to_payload()
        payload["applied"] = False
        self.copy_requested.emit(payload)

    def set_applied(self, value: bool) -> None:
        self._applied = value

    def is_valid(self) -> bool:
        return self._is_valid

    def to_payload(self) -> dict:
        name = self._name.text().strip() or f"Антена {self._index}"
        antenna_type = self._antenna_type.currentText()
        defaults = ANTENNA_TYPE_DEFAULTS.get(antenna_type, {})
        azimuth_deg = float(self._azimuth.text()) if self._azimuth.text().strip() else None
        beamwidth_deg = float(self._beamwidth.text()) if self._beamwidth.text().strip() else None
        if azimuth_deg is None:
            azimuth_deg = defaults.get("azimuth_deg")
        if beamwidth_deg is None:
            beamwidth_deg = defaults.get("beamwidth_deg")
        return {
            "id": self.antenna_id,
            "name": name,
            "antenna_type": antenna_type,
            "azimuth_deg": azimuth_deg,
            "beamwidth_deg": beamwidth_deg,
            "gain_dbi": float(self._gain.text()) if self._gain.text().strip() else None,
            "height_m": float(self._height.text()) if self._height.text().strip() else None,
            "frequency_ghz": self._mhz_to_ghz(self._frequency.text()),
            "tx_power_dbm": float(self._tx_power.text()) if self._tx_power.text().strip() else None,
            "mcs": self._mcs.currentData(),
            "rx_gain_dbi": float(self._rx_gain.text()) if self._rx_gain.text().strip() else None,
            "rx_height_m": float(self._rx_height.text()) if self._rx_height.text().strip() else None,
            "rx_sensitivity_dbm": float(self._rx_sens.text()) if self._rx_sens.text().strip() else None,
            "channel_width_mhz": float(self._channel_width.text()) if self._channel_width.text().strip() else None,
            "noise_figure_db": float(self._noise_figure.text()) if self._noise_figure.text().strip() else None,
            "required_sinr_db": float(self._required_sinr.text()) if self._required_sinr.text().strip() else None,
            "misc_losses_db": float(self._losses.text()) if self._losses.text().strip() else None,
            "link_margin_db": float(self._margin.text()) if self._margin.text().strip() else None,
            "applied": self._applied,
        }

    def _update_eirp_calculator(self) -> None:
        freq_text = self._frequency.text().strip()
        dist_text = self._calc_distance.text().strip()
        rx_sens_text = self._rx_sens.text().strip()
        rx_gain_text = self._rx_gain.text().strip()
        losses_text = self._losses.text().strip()
        margin_text = self._margin.text().strip()
        try:
            freq_mhz = float(freq_text) if freq_text else None
            dist = float(dist_text) if dist_text else None
            rx_sens = float(rx_sens_text) if rx_sens_text else None
            rx_gain = float(rx_gain_text) if rx_gain_text else 0.0
            losses = float(losses_text) if losses_text else 0.0
            margin = float(margin_text) if margin_text else 0.0
        except ValueError:
            self._calc_fspl.setText("")
            self._calc_required.setText("")
            self._calc_ok.setText("")
            self._calc_ok.setToolTip("")
            return
        if not freq_mhz or not dist or rx_sens is None:
            self._calc_fspl.setText("")
            self._calc_required.setText("")
            self._calc_ok.setText("")
            self._calc_ok.setToolTip("")
            return
        freq = freq_mhz / 1000.0
        fspl = 92.45 + 20.0 * math.log10(dist) + 20.0 * math.log10(freq)
        required_eirp = rx_sens + margin + fspl + losses - rx_gain
        self._calc_fspl.setText(f"{fspl:.2f}")
        self._calc_required.setText(f"{required_eirp:.2f}")
        tx_gain_text = self._gain.text().strip()
        tx_power_text = self._tx_power.text().strip()
        try:
            tx_gain = float(tx_gain_text) if tx_gain_text else 0.0
            tx_power = float(tx_power_text) if tx_power_text else None
        except ValueError:
            tx_power = None
        if tx_power is None:
            self._calc_ok.setText("")
            self._calc_ok.setToolTip("")
            return
        actual_eirp = tx_power + tx_gain - losses
        ok = actual_eirp >= required_eirp
        self._calc_ok.setText("Так" if ok else "Ні")
        self._calc_ok.setToolTip(
            f"EIRP_actual: {actual_eirp:.2f} dBm\nEIRP_required: {required_eirp:.2f} dBm"
        )

    def _validate_inputs(self) -> None:
        fields = (
            self._azimuth,
            self._beamwidth,
            self._gain,
            self._height,
            self._frequency,
            self._tx_power,
            self._rx_gain,
            self._rx_height,
            self._rx_sens,
            self._noise_figure,
            self._required_sinr,
            self._losses,
            self._margin,
            self._calc_distance,
        )
        all_valid = True
        for field in fields:
            valid = self._is_field_valid(field)
            self._set_field_validity(field, valid)
            self._set_field_error(field, valid)
            all_valid = all_valid and valid
        self._apply_btn.setEnabled(all_valid)
        if all_valid != self._is_valid:
            self._is_valid = all_valid
            self.validity_changed.emit(all_valid)

    @staticmethod
    def _is_field_valid(field: QLineEdit) -> bool:
        text = field.text().strip()
        if not text:
            return True
        validator = field.validator()
        if validator is None:
            return True
        state, _, _ = validator.validate(text, 0)
        return state == QValidator.State.Acceptable

    @staticmethod
    def _set_field_validity(field: QLineEdit, valid: bool) -> None:
        if valid:
            field.setStyleSheet("")
        else:
            field.setStyleSheet("border: 1px solid #dc2626;")

    def _set_field_error(self, field: QLineEdit, valid: bool) -> None:
        label = self._field_error_labels.get(field)
        if label is None:
            return
        text = field.text().strip()
        if valid or not text:
            label.hide()
            label.clear()
            return
        message = self._field_error_messages.get(field, "Некоректне значення.")
        label.setText(message)
        label.show()

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
    def _set_float_field(field: QLineEdit, value: object, max_precision: int = 2) -> None:
        if not isinstance(value, (int, float)):
            return
        text = f"{float(value):.{max_precision}f}".rstrip("0").rstrip(".")
        with QSignalBlocker(field):
            field.setText(text)

class InspectorPanel(QWidget):
    link_updated = Signal(str, dict)
    link_analyze_requested = Signal(str)
    site_updated = Signal(str, dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(320)
        self._current_link_id: str | None = None
        self._empty_project_mode = False

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
        self._site_lat_error = QLabel("", self)
        self._site_lon_error = QLabel("", self)
        self._site_lat_error.setStyleSheet("color: #dc2626; font-size: 11px;")
        self._site_lon_error.setStyleSheet("color: #dc2626; font-size: 11px;")
        self._site_lat_error.hide()
        self._site_lon_error.hide()
        self._site_elevation = QLabel("—")
        self._site_notes = QLabel("—")
        self._site_environment = QComboBox(self)
        self._site_environment.addItem("Відкритий простір", "open")
        self._site_environment.addItem("Змішане середовище", "mixed")
        self._site_environment.addItem("Міська забудова", "urban")
        self._site_environment.addItem("Висока рослинність", "vegetation")
        self._site_environment.setToolTip(
            "Вплив середовища на затухання сигналу для антен цього сайту."
        )
        lat_validator = QDoubleValidator(-90.0, 90.0, 6, self)
        lat_validator.setLocale(QLocale.c())
        self._site_lat.setValidator(lat_validator)
        lon_validator = QDoubleValidator(-180.0, 180.0, 6, self)
        lon_validator.setLocale(QLocale.c())
        self._site_lon.setValidator(lon_validator)

        self._site_apply_basic = QPushButton("Застосувати сайт", self)
        self._site_apply_basic.clicked.connect(self._apply_site_basic_changes)
        self._antenna_blocks: list[AntennaBlock] = []
        self._antenna_container = QVBoxLayout()
        self._antenna_container.setContentsMargins(0, 0, 0, 0)
        self._antenna_container_widget = QWidget(self)
        self._antenna_container_widget.setLayout(self._antenna_container)
        self._add_antenna_btn = QPushButton("Додати антену", self)
        self._add_antenna_btn.clicked.connect(lambda: self._add_antenna_block())
        self._add_antenna_btn.setEnabled(False)
        self._apply_all_antennas_btn = QPushButton("Застосувати всі антени", self)
        self._apply_all_antennas_btn.clicked.connect(self._apply_all_antennas)
        self._apply_all_antennas_btn.setEnabled(False)

        for field in (self._site_lat, self._site_lon):
            field.textChanged.connect(lambda _text, f=field: self._normalize_decimal(f))
            field.textChanged.connect(self._validate_site_fields)

        label_name = QLabel("Назва:")
        label_type = QLabel("Тип:")
        label_lat = QLabel("Широта:")
        label_lon = QLabel("Довгота:")
        label_elevation = QLabel("Висота:")
        label_notes = QLabel("Нотатки:")
        label_environment = QLabel("Середовище:")

        site_layout.addRow(label_name, self._site_name)
        site_layout.addRow(label_type, self._site_type)
        site_layout.addRow(label_lat, self._site_lat)
        lat_error_left = QLabel("", self)
        lat_error_left.hide()
        site_layout.addRow(lat_error_left, self._site_lat_error)
        site_layout.addRow(label_lon, self._site_lon)
        lon_error_left = QLabel("", self)
        lon_error_left.hide()
        site_layout.addRow(lon_error_left, self._site_lon_error)
        site_layout.addRow(label_elevation, self._site_elevation)
        site_layout.addRow(label_notes, self._site_notes)
        site_layout.addRow(label_environment, self._site_environment)
        site_layout.addRow(self._site_apply_basic)
        site_layout.addRow(QLabel("Антени:"))
        site_layout.addRow(self._antenna_container_widget)
        site_layout.addRow(self._add_antenna_btn)
        site_layout.addRow(self._apply_all_antennas_btn)

        self._link_group = QWidget(self)
        link_layout = QFormLayout(self._link_group)
        self._link_name = QLineEdit(self)
        self._link_kind = QComboBox(self)
        self._link_kind.addItem("PtP", LinkKind.PTP)
        self._link_kind.addItem("PtMP", LinkKind.PTMP)
        self._link_kind.addItem("Ethernet", LinkKind.ETHERNET)
        self._link_kind.currentIndexChanged.connect(self._toggle_link_fields)
        self._label_frequency = QLabel("Частота (МГц):")
        self._label_ssid = QLabel("SSID:")
        self._label_password = QLabel("Пароль:")
        self._label_link_type = QLabel("Тип лінка:")
        self._label_cable_type = QLabel("Тип кабелю:")

        self._link_between = QLabel("—")
        self._link_distance = QLabel("—")
        self._link_frequency = QLineEdit(self)
        freq_validator = QDoubleValidator(0.1, 30000.0, 3, self)
        freq_validator.setLocale(QLocale.c())
        self._link_frequency.setValidator(freq_validator)
        self._link_freq_hint = QLabel("Діапазон: 0.1–30000 МГц.")
        self._link_freq_hint.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        self._link_freq_error = QLabel("", self)
        self._link_freq_error.setStyleSheet("color: #dc2626; font-size: 11px;")
        self._link_freq_error.setWordWrap(True)
        self._link_freq_error.hide()
        self._link_frequency.textChanged.connect(self._validate_link_fields)
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
        link_layout.addRow(QLabel(""), self._link_freq_hint)
        link_freq_error_left = QLabel("", self)
        link_freq_error_left.hide()
        link_layout.addRow(link_freq_error_left, self._link_freq_error)
        link_layout.addRow(self._label_ssid, self._link_ssid)
        link_layout.addRow(self._label_password, self._link_password)
        link_layout.addRow(QLabel("Нотатки:"), self._link_notes)
        link_layout.addRow(self._label_link_type, self._link_type)
        link_layout.addRow(self._label_cable_type, self._cable_type)
        link_layout.addRow(self._apply_btn)
        link_layout.addRow(self._analyze_btn)
        self._set_link_editable(False)

        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self._empty_state_label = QLabel(
            "Створіть перший сайт для початку роботи або завантажте проєкт",
            self,
        )
        self._empty_state_label.setWordWrap(True)
        self._empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_state_label.setStyleSheet(
            "QLabel {"
            "background: rgba(15, 23, 32, 220);"
            "color: white;"
            "border-radius: 10px;"
            "padding: 16px;"
            "font-weight: 600;"
            "}"
        )
        content_layout.addWidget(self._site_group)
        content_layout.addWidget(self._link_group)
        content_layout.addWidget(self._empty_state_label)
        content_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        self._link_group.setVisible(False)
        self._empty_state_label.setVisible(False)
        self._current_site_id: str | None = None

    def set_empty_project_mode(self, enabled: bool) -> None:
        self._empty_project_mode = enabled
        if enabled:
            self._current_site_id = None
            self._current_link_id = None
            self._site_group.setVisible(False)
            self._link_group.setVisible(False)
            self._empty_state_label.setVisible(True)
            return
        self._empty_state_label.setVisible(False)

    def _set_link_editable(self, editable: bool) -> None:
        for field in (
            self._link_name,
            self._link_frequency,
            self._link_ssid,
            self._link_password,
            self._link_notes,
        ):
            field.setReadOnly(not editable)
        for widget in (self._link_kind, self._link_type, self._cable_type):
            widget.setEnabled(editable)
        self._apply_btn.setVisible(editable)
        self._apply_btn.setEnabled(editable)

    def show_site(self, site: Site | None) -> None:
        if site is None:
            self._site_name.setText("")
            self._site_type.setCurrentIndex(0)
            self._site_lat.setText("")
            self._site_lon.setText("")
            self._site_elevation.setText("—")
            self._site_notes.setText("—")
            self._set_site_environment(None)
            self._clear_antenna_blocks()
            self._add_antenna_btn.setEnabled(False)
            self._apply_all_antennas_btn.setEnabled(False)
            self._site_group.setVisible(not self._empty_project_mode)
            self._link_group.setVisible(False)
            self._empty_state_label.setVisible(self._empty_project_mode)
            self._current_link_id = None
            self._current_site_id = None
            self._validate_site_fields()
            return

        self._empty_project_mode = False
        self._site_name.setText(site.name)
        type_idx = self._site_type.findData(site.kind)
        if type_idx >= 0:
            self._site_type.setCurrentIndex(type_idx)
        self._site_lat.setText(f"{site.location.lat:.6f}")
        self._site_lon.setText(f"{site.location.lon:.6f}")
        self._site_elevation.setText("—")
        self._site_notes.setText(f"пристроїв: {len(site.devices)}")
        self._set_site_environment(site.metadata.get("environment") if site.metadata else None)
        self._clear_antenna_blocks()
        for idx, antenna in enumerate(site.antennas, start=1):
            self._add_antenna_block(antenna, idx)
        self._add_antenna_btn.setEnabled(True)
        self._update_apply_all_state()
        self._site_group.setVisible(True)
        self._link_group.setVisible(False)
        self._empty_state_label.setVisible(False)
        self._current_link_id = None
        self._current_site_id = site.id
        self._validate_site_fields()

    def _set_site_environment(self, value: str | None) -> None:
        idx = self._site_environment.findData(value or "")
        if idx < 0:
            idx = self._site_environment.findData("mixed")
            if idx < 0:
                idx = 0
        with QSignalBlocker(self._site_environment):
            self._site_environment.setCurrentIndex(idx)

    def show_link(self, link: Link | None, site_a_name: str = "—", site_b_name: str = "—") -> None:
        if link is None:
            self.show_site(None)
            return
        self._empty_project_mode = False
        kind_value = link.kind.value if hasattr(link.kind, "value") else str(link.kind)
        self._current_link_id = link.id
        self._link_name.setText(link.name)
        self._link_between.setText(f"{site_a_name} ↔ {site_b_name}")
        self._link_distance.setText(
            f"{link.distance_km:.2f} км" if link.distance_km is not None else "—"
        )
        self._set_kind_combo(kind_value)
        if kind_value in ("ptp", "ptmp"):
            if link.frequency_ghz is None:
                self._link_frequency.setText("")
            else:
                self._link_frequency.setText(str(link.frequency_ghz * 1000.0))
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
        self._empty_state_label.setVisible(False)
        kind_value = link.kind.value if hasattr(link.kind, "value") else str(link.kind)
        self._analyze_btn.setVisible(kind_value in ("ptp", "ptmp"))

    def _clear_antenna_blocks(self) -> None:
        for block in self._antenna_blocks:
            self._antenna_container.removeWidget(block)
            block.deleteLater()
        self._antenna_blocks = []

    def _add_antenna_block(self, antenna: AntennaParams | None = None, index: int | None = None) -> None:
        idx = index if index is not None else len(self._antenna_blocks) + 1
        block = AntennaBlock(antenna, idx, self)
        block.apply_requested.connect(self._apply_single_antenna)
        block.delete_requested.connect(self._delete_antenna_block)
        block.validity_changed.connect(lambda _ok: self._update_apply_all_state())
        block.copy_requested.connect(self._copy_antenna_block)
        self._antenna_blocks.append(block)
        self._antenna_container.addWidget(block)
        self._update_apply_all_state()

    def _apply_single_antenna(self, antenna_id: str, payload: dict) -> None:
        if self._current_site_id is None:
            return
        payload["id"] = antenna_id
        self.site_updated.emit(self._current_site_id, {"antenna": payload, "apply": True})

    def _apply_all_antennas(self) -> None:
        if self._current_site_id is None:
            return
        if not self._antenna_blocks:
            QMessageBox.information(self, "Антени", "Спочатку додайте антену.")
            return
        antennas = []
        for idx, block in enumerate(self._antenna_blocks, start=1):
            data = block.to_payload()
            data["name"] = data.get("name") or f"Антена {idx}"
            data["applied"] = True
            block.set_applied(True)
            antennas.append(data)
        self.site_updated.emit(self._current_site_id, {"antennas": antennas, "apply_all": True})
        self._update_apply_all_state()

    def _delete_antenna_block(self, antenna_id: str) -> None:
        if self._current_site_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Видалити антену",
            "Видалити цю антену?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        block = next((b for b in self._antenna_blocks if b.antenna_id == antenna_id), None)
        if block is None:
            return
        self._antenna_container.removeWidget(block)
        self._antenna_blocks.remove(block)
        block.deleteLater()
        antennas = []
        for idx, b in enumerate(self._antenna_blocks, start=1):
            data = b.to_payload()
            data["name"] = data.get("name") or f"Антена {idx}"
            antennas.append(data)
        self.site_updated.emit(self._current_site_id, {"antennas": antennas})
        self._update_apply_all_state()

    def _copy_antenna_block(self, payload: dict) -> None:
        if self._current_site_id is None:
            return
        new_index = len(self._antenna_blocks) + 1
        new_antenna = AntennaParams(id=uuid4().hex[:8])
        new_antenna.name = f"Антена {new_index}"
        new_antenna.antenna_type = payload.get("antenna_type")
        new_antenna.azimuth_deg = payload.get("azimuth_deg")
        new_antenna.beamwidth_deg = payload.get("beamwidth_deg")
        new_antenna.gain_dbi = payload.get("gain_dbi")
        new_antenna.height_m = payload.get("height_m")
        new_antenna.frequency_ghz = payload.get("frequency_ghz")
        new_antenna.tx_power_dbm = payload.get("tx_power_dbm")
        new_antenna.mcs = payload.get("mcs")
        new_antenna.rx_gain_dbi = payload.get("rx_gain_dbi")
        new_antenna.rx_height_m = payload.get("rx_height_m")
        new_antenna.rx_sensitivity_dbm = payload.get("rx_sensitivity_dbm")
        new_antenna.channel_width_mhz = payload.get("channel_width_mhz")
        new_antenna.noise_figure_db = payload.get("noise_figure_db")
        new_antenna.required_sinr_db = payload.get("required_sinr_db")
        new_antenna.misc_losses_db = payload.get("misc_losses_db")
        new_antenna.link_margin_db = payload.get("link_margin_db")
        new_antenna.applied = False
        self._add_antenna_block(new_antenna, new_index)

    def _update_apply_all_state(self) -> None:
        if self._current_site_id is None or not self._antenna_blocks:
            self._apply_all_antennas_btn.setEnabled(False)
            return
        all_valid = all(block.is_valid() for block in self._antenna_blocks)
        self._apply_all_antennas_btn.setEnabled(all_valid)

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
            self._link_freq_hint,
            self._link_freq_error,
            self._label_ssid,
            self._link_ssid,
            self._label_password,
            self._link_password,
        ):
            widget.setVisible(is_wireless)
        for widget in (self._label_link_type, self._link_type, self._label_cable_type, self._cable_type):
            widget.setVisible(not is_wireless)
        self._validate_link_fields()

    def _validate_link_fields(self) -> None:
        kind = self._link_kind.currentData()
        is_wireless = kind in (LinkKind.PTP, LinkKind.PTMP)
        valid = True
        if is_wireless:
            valid = AntennaBlock._is_field_valid(self._link_frequency)
            AntennaBlock._set_field_validity(self._link_frequency, valid)
            freq_text = self._link_frequency.text().strip()
            if valid or not freq_text:
                self._link_freq_error.hide()
                self._link_freq_error.clear()
            else:
                self._link_freq_error.setText("Очікується МГц у діапазоні 0.1–30000.")
                self._link_freq_error.show()
        else:
            AntennaBlock._set_field_validity(self._link_frequency, True)
            self._link_freq_error.hide()
            self._link_freq_error.clear()
        self._apply_btn.setEnabled(valid)

    def _validate_site_fields(self) -> None:
        lat_valid = AntennaBlock._is_field_valid(self._site_lat)
        lon_valid = AntennaBlock._is_field_valid(self._site_lon)
        AntennaBlock._set_field_validity(self._site_lat, lat_valid)
        AntennaBlock._set_field_validity(self._site_lon, lon_valid)

        lat_text = self._site_lat.text().strip()
        lon_text = self._site_lon.text().strip()
        if lat_valid or not lat_text:
            self._site_lat_error.hide()
            self._site_lat_error.clear()
        else:
            self._site_lat_error.setText("Очікується діапазон -90…90.")
            self._site_lat_error.show()
        if lon_valid or not lon_text:
            self._site_lon_error.hide()
            self._site_lon_error.clear()
        else:
            self._site_lon_error.setText("Очікується діапазон -180…180.")
            self._site_lon_error.show()

        self._site_apply_basic.setEnabled(lat_valid and lon_valid and self._current_site_id is not None)

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
            "frequency_ghz": (float(self._link_frequency.text()) / 1000.0)
            if is_wireless and self._link_frequency.text().strip()
            else None,
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

    def _apply_site_basic_changes(self) -> None:
        if self._current_site_id is None:
            return
        lat_text = self._site_lat.text().strip()
        lon_text = self._site_lon.text().strip()
        try:
            lat = float(lat_text) if lat_text else None
            lon = float(lon_text) if lon_text else None
        except ValueError:
            self._validate_site_fields()
            return
        payload = {
            "kind": self._site_type.currentData(),
            "lat": lat,
            "lon": lon,
            "environment": self._site_environment.currentData(),
        }
        self.site_updated.emit(self._current_site_id, payload)

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
