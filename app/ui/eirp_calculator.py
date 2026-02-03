from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QLocale
from PySide6.QtGui import QDoubleValidator, QValidator
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.domain import AntennaParams


class EirpCalculatorDialog(QDialog):
    def __init__(self, antenna: Optional[AntennaParams] = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Розрахувати EIRP")
        self.setMinimumWidth(420)

        self._frequency = QLineEdit(self)
        self._distance = QLineEdit(self)
        self._tx_power = QLineEdit(self)
        self._tx_gain = QLineEdit(self)
        self._rx_gain = QLineEdit(self)
        self._rx_sens = QLineEdit(self)
        self._losses = QLineEdit(self)
        self._margin = QLineEdit(self)

        self._fspl = QLineEdit(self)
        self._eirp_required = QLineEdit(self)
        self._eirp_actual = QLineEdit(self)
        self._eirp_ok = QLineEdit(self)
        for field in (self._fspl, self._eirp_required, self._eirp_actual, self._eirp_ok):
            field.setReadOnly(True)

        freq_validator = QDoubleValidator(0.1, 30000.0, 3, self)
        freq_validator.setLocale(QLocale.c())
        dist_validator = QDoubleValidator(0.1, 300.0, 2, self)
        dist_validator.setLocale(QLocale.c())
        power_validator = QDoubleValidator(-60.0, 60.0, 2, self)
        power_validator.setLocale(QLocale.c())
        gain_validator = QDoubleValidator(0.0, 60.0, 1, self)
        gain_validator.setLocale(QLocale.c())
        sens_validator = QDoubleValidator(-150.0, -30.0, 2, self)
        sens_validator.setLocale(QLocale.c())
        loss_validator = QDoubleValidator(0.0, 60.0, 2, self)
        loss_validator.setLocale(QLocale.c())
        margin_validator = QDoubleValidator(0.0, 40.0, 2, self)
        margin_validator.setLocale(QLocale.c())

        self._frequency.setValidator(freq_validator)
        self._distance.setValidator(dist_validator)
        self._tx_power.setValidator(power_validator)
        self._tx_gain.setValidator(gain_validator)
        self._rx_gain.setValidator(gain_validator)
        self._rx_sens.setValidator(sens_validator)
        self._losses.setValidator(loss_validator)
        self._margin.setValidator(margin_validator)

        for field in (
            self._frequency,
            self._distance,
            self._tx_power,
            self._tx_gain,
            self._rx_gain,
            self._rx_sens,
            self._losses,
            self._margin,
        ):
            field.textChanged.connect(self._update)
            field.textChanged.connect(self._validate_inputs)

        intro = QLabel(
            "Калькулятор існує для оцінки FSPL розрахунку EIRP\n"
            "для заданої дистанції. Додаткова інформація наведена в гайді.",
            self,
        )
        intro.setWordWrap(True)

        form = QFormLayout()

        def add_hint(text: str) -> None:
            hint = QLabel(text, self)
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #9aa0a6; font-size: 11px;")
            form.addRow(QLabel(""), hint)

        form.addRow(QLabel("Частота (МГц):"), self._frequency)
        add_hint("Діапазон: 0.1–30000 МГц.")
        form.addRow(QLabel("Необхідна дистанція (км):"), self._distance)
        add_hint("Діапазон: 0.1–300 км.")
        form.addRow(QLabel("Потужність TX (dBm):"), self._tx_power)
        add_hint("Діапазон: -60…60 dBm.")
        form.addRow(QLabel("Підсилення TX (dBi):"), self._tx_gain)
        add_hint("Діапазон: 0–60 dBi.")
        form.addRow(QLabel("Підсилення RX (dBi):"), self._rx_gain)
        add_hint("Діапазон: 0–60 dBi.")
        form.addRow(QLabel("Чутливість RX (dBm):"), self._rx_sens)
        add_hint("Діапазон: -150…-30 dBm.")
        form.addRow(QLabel("Втрати АФТ (дБ):"), self._losses)
        add_hint("Діапазон: 0–60 dB.")
        form.addRow(QLabel("Закладені втрати (дБ):"), self._margin)
        add_hint("Діапазон: 0–40 dB.")

        form.addRow(QLabel("FSPL (дБ):"), self._fspl)
        form.addRow(QLabel("EIRP потрібний (dBm):"), self._eirp_required)
        form.addRow(QLabel("EIRP фактичний (dBm):"), self._eirp_actual)
        form.addRow(QLabel("EIRP статус:"), self._eirp_ok)

        formulas = QLabel(
            "Формули для розрахунків, що використовуються:\n"
            "FSPL = 92.45 + 20·log10(d_km) + 20·log10(f_GHz)\n"
            "EIRP_required = RX_sens + Margin + FSPL + Losses − RX_gain\n"
            "EIRP_actual = Pt + Gt − Losses\n"
            "f_GHz = f_MHz / 1000",
            self,
        )
        formulas.setWordWrap(True)

        close_btn = QPushButton("Закрити", self)
        close_btn.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(formulas)
        layout.addWidget(close_btn)
        self.setLayout(layout)

        if antenna is not None:
            if antenna.frequency_ghz is not None:
                self._frequency.setText(f"{antenna.frequency_ghz * 1000.0:.3f}")
            if antenna.tx_power_dbm is not None:
                self._tx_power.setText(str(antenna.tx_power_dbm))
            if antenna.gain_dbi is not None:
                self._tx_gain.setText(str(antenna.gain_dbi))
            if antenna.rx_gain_dbi is not None:
                self._rx_gain.setText(str(antenna.rx_gain_dbi))
            if antenna.rx_sensitivity_dbm is not None:
                self._rx_sens.setText(str(antenna.rx_sensitivity_dbm))
            if antenna.misc_losses_db is not None:
                self._losses.setText(str(antenna.misc_losses_db))
            if antenna.link_margin_db is not None:
                self._margin.setText(str(antenna.link_margin_db))

        self._update()
        self._validate_inputs()

    def _update(self) -> None:
        self._validate_inputs()
        freq = self._parse_float(self._frequency)
        dist = self._parse_float(self._distance)
        tx_power = self._parse_float(self._tx_power)
        tx_gain = self._parse_float(self._tx_gain, default=0.0)
        rx_gain = self._parse_float(self._rx_gain, default=0.0)
        rx_sens = self._parse_float(self._rx_sens)
        losses = self._parse_float(self._losses, default=0.0)
        margin = self._parse_float(self._margin, default=0.0)

        if not freq or not dist or rx_sens is None:
            self._fspl.setText("")
            self._eirp_required.setText("")
            self._eirp_actual.setText("")
            self._eirp_ok.setText("")
            self._eirp_ok.setStyleSheet("")
            return

        freq_ghz = freq / 1000.0
        fspl = 92.45 + 20.0 * math.log10(dist) + 20.0 * math.log10(freq_ghz)
        required_eirp = rx_sens + margin + fspl + losses - rx_gain
        self._fspl.setText(f"{fspl:.2f}")
        self._eirp_required.setText(f"{required_eirp:.2f}")

        if tx_power is None:
            self._eirp_actual.setText("")
            self._eirp_ok.setText("")
            self._eirp_ok.setStyleSheet("")
            return

        actual_eirp = tx_power + tx_gain - losses
        self._eirp_actual.setText(f"{actual_eirp:.2f}")
        ok = actual_eirp >= required_eirp
        self._eirp_ok.setText("OK" if ok else "НЕ ОК")
        self._eirp_ok.setStyleSheet("color: #16a34a;" if ok else "color: #dc2626;")

    def _validate_inputs(self) -> None:
        fields = (
            self._frequency,
            self._distance,
            self._tx_power,
            self._tx_gain,
            self._rx_gain,
            self._rx_sens,
            self._losses,
            self._margin,
        )
        for field in fields:
            valid = self._is_field_valid(field)
            self._set_field_validity(field, valid)

    @staticmethod
    def _parse_float(field: QLineEdit, default: Optional[float] = None) -> Optional[float]:
        text = field.text().strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default

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
