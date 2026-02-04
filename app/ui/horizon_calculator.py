from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QLocale
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget, QPushButton


class HorizonCalculatorDialog(QDialog):
    def __init__(
        self,
        tx_ground_m: float,
        rx_ground_m: float,
        distance_km: float,
        parent: Optional[QWidget] = None,
        k_factor: float = 4.0 / 3.0,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Калькулятор горизонту")
        self.setMinimumWidth(420)
        self._k_factor = k_factor

        self._tx_ground = QLabel(f"{tx_ground_m:.1f} м", self)
        self._rx_ground = QLabel(f"{rx_ground_m:.1f} м", self)

        self._tx_antenna = QLineEdit(self)
        self._rx_antenna = QLineEdit(self)
        self._tx_total = QLineEdit(self)
        self._rx_total = QLineEdit(self)
        self._distance = QLineEdit(self)
        self._tx_horizon = QLineEdit(self)
        self._visibility = QLineEdit(self)

        for field in (self._tx_total, self._rx_total, self._distance, self._tx_horizon, self._visibility):
            field.setReadOnly(True)

        validator = QDoubleValidator(0.0, 8000.0, 2, self)
        validator.setLocale(QLocale.c())
        self._tx_antenna.setValidator(validator)
        self._rx_antenna.setValidator(validator)

        self._tx_antenna.textChanged.connect(self._update)
        self._rx_antenna.textChanged.connect(self._update)

        intro = QLabel(
            "Горизонт розраховується по TX (абсолютна висота місцевості + антена).\n"
            "RX використовується лише для перевірки, чи є радіовидимість.\n"
            "Рослинність і забудова не враховані — реальний горизонт буде меншим.",
            self,
        )
        intro.setWordWrap(True)

        form = QFormLayout()
        form.addRow(QLabel("Висота місцевості TX (м):"), self._tx_ground)
        form.addRow(QLabel("Висота місцевості RX (м):"), self._rx_ground)
        form.addRow(QLabel("Висота антени TX (м):"), self._tx_antenna)
        form.addRow(QLabel("Висота антени RX (м):"), self._rx_antenna)
        form.addRow(QLabel("Абсолютна висота TX (м):"), self._tx_total)
        form.addRow(QLabel("Абсолютна висота RX (м):"), self._rx_total)
        form.addRow(QLabel("Дистанція між точками (км):"), self._distance)
        form.addRow(QLabel("Горизонт TX (км):"), self._tx_horizon)
        form.addRow(QLabel("Радіовидимість:"), self._visibility)

        close_btn = QPushButton("Закрити", self)
        close_btn.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(close_btn)
        self.setLayout(layout)

        self._tx_ground_m = tx_ground_m
        self._rx_ground_m = rx_ground_m
        self._distance_km = max(distance_km, 0.0)
        self._update()

    def _update(self) -> None:
        tx_ant = self._parse_float(self._tx_antenna)
        rx_ant = self._parse_float(self._rx_antenna)
        self._distance.setText(f"{self._distance_km:.2f}")

        if tx_ant is None:
            self._tx_total.setText("")
            self._tx_horizon.setText("")
            self._visibility.setText("")
        else:
            tx_total = self._tx_ground_m + tx_ant
            self._tx_total.setText(f"{tx_total:.1f}")
            tx_horizon = self._radio_horizon_km(tx_total)
            self._tx_horizon.setText(f"{tx_horizon:.2f}")

        if rx_ant is None:
            self._rx_total.setText("")
        else:
            rx_total = self._rx_ground_m + rx_ant
            self._rx_total.setText(f"{rx_total:.1f}")

        if tx_ant is None or rx_ant is None:
            self._visibility.setText("")
            return

        tx_total = self._tx_ground_m + tx_ant
        rx_total = self._rx_ground_m + rx_ant
        tx_horizon = self._radio_horizon_km(tx_total)
        rx_horizon = self._radio_horizon_km(rx_total)
        visible = self._distance_km <= (tx_horizon + rx_horizon)
        self._visibility.setText("Є" if visible else "Немає")

    def _radio_horizon_km(self, total_m: float) -> float:
        height = max(total_m, 0.0)
        return 3.57 * math.sqrt(self._k_factor) * math.sqrt(height)

    @staticmethod
    def _parse_float(field: QLineEdit) -> Optional[float]:
        text = field.text().strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
