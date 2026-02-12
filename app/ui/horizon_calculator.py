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
        profile_distances_km: list[float] | None = None,
        profile_elevations_m: list[float] | None = None,
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
        self._radio_visibility = QLineEdit(self)
        self._terrain_los = QLineEdit(self)
        self._visibility = QLineEdit(self)

        for field in (
            self._tx_total,
            self._rx_total,
            self._distance,
            self._tx_horizon,
            self._radio_visibility,
            self._terrain_los,
            self._visibility,
        ):
            field.setReadOnly(True)

        validator = QDoubleValidator(0.0, 8000.0, 2, self)
        validator.setLocale(QLocale.c())
        self._tx_antenna.setValidator(validator)
        self._rx_antenna.setValidator(validator)

        self._tx_antenna.textChanged.connect(self._update)
        self._rx_antenna.textChanged.connect(self._update)

        intro = QLabel(
            "Горизонт розраховується по TX (абсолютна висота місцевості + антена).\n"
            "RX використовується для перевірки, чи є радіовидимість (горизонт).\n"
            "Додатково перевіряється LOS по профілю траси між точками.\n"
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
        form.addRow(QLabel("Радіовидимість (горизонт):"), self._radio_visibility)
        form.addRow(QLabel("LOS по трасі:"), self._terrain_los)
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
        self._profile_distances_km = profile_distances_km or []
        self._profile_elevations_m = profile_elevations_m or []
        self._update()

    def _update(self) -> None:
        tx_ant = self._parse_float(self._tx_antenna)
        rx_ant = self._parse_float(self._rx_antenna)
        self._distance.setText(f"{self._distance_km:.2f}")

        if tx_ant is None:
            self._tx_total.setText("")
            self._tx_horizon.setText("")
            self._radio_visibility.setText("")
            self._terrain_los.setText("")
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
            self._radio_visibility.setText("")
            self._terrain_los.setText("")
            self._visibility.setText("")
            return

        tx_total = self._tx_ground_m + tx_ant
        rx_total = self._rx_ground_m + rx_ant
        tx_horizon = self._radio_horizon_km(tx_total)
        rx_horizon = self._radio_horizon_km(rx_total)
        radio_visible = self._distance_km <= (tx_horizon + rx_horizon)
        self._radio_visibility.setText("Є" if radio_visible else "Немає")

        terrain_los = self._terrain_los_visible(tx_ant, rx_ant)
        self._terrain_los.setText("Є" if terrain_los else "Немає")

        visible = radio_visible and terrain_los
        self._visibility.setText("Є" if visible else "Немає")

    def _radio_horizon_km(self, total_m: float) -> float:
        height = max(total_m, 0.0)
        return 3.57 * math.sqrt(self._k_factor) * math.sqrt(height)

    def _terrain_los_visible(self, tx_ant_m: float, rx_ant_m: float) -> bool:
        if len(self._profile_distances_km) < 2 or len(self._profile_elevations_m) < 2:
            return True
        if len(self._profile_distances_km) != len(self._profile_elevations_m):
            return True

        total_km = max(self._profile_distances_km[-1], 0.0)
        if total_km <= 0.0:
            return True

        start_h = self._profile_elevations_m[0] + tx_ant_m
        end_h = self._profile_elevations_m[-1] + rx_ant_m

        for i in range(1, len(self._profile_elevations_m) - 1):
            dist_km = self._profile_distances_km[i]
            frac = dist_km / total_km
            expected_h = start_h + (end_h - start_h) * frac
            if self._profile_elevations_m[i] > expected_h:
                return False
        return True

    @staticmethod
    def _parse_float(field: QLineEdit) -> Optional[float]:
        text = field.text().strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
