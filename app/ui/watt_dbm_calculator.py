from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QLocale
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget, QPushButton


class WattDbmCalculatorDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Конвертер Вт ↔ dBm")
        self.setMinimumWidth(360)

        self._watts = QLineEdit(self)
        self._dbm = QLineEdit(self)

        watts_validator = QDoubleValidator(0.0, 1_000_000.0, 6, self)
        watts_validator.setLocale(QLocale.c())
        dbm_validator = QDoubleValidator(-200.0, 100.0, 3, self)
        dbm_validator.setLocale(QLocale.c())

        self._watts.setValidator(watts_validator)
        self._dbm.setValidator(dbm_validator)

        self._watts.textChanged.connect(self._from_watts)
        self._dbm.textChanged.connect(self._from_dbm)

        intro = QLabel("Введіть значення у Ваттах або dBm — результат рахується одразу.", self)
        intro.setWordWrap(True)

        form = QFormLayout()
        form.addRow(QLabel("Потужність (Вт):"), self._watts)
        form.addRow(QLabel("Потужність (dBm):"), self._dbm)

        close_btn = QPushButton("Закрити", self)
        close_btn.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(close_btn)
        self.setLayout(layout)

    def _from_watts(self) -> None:
        if self._watts.hasFocus() is False:
            return
        value = self._parse_float(self._watts)
        if value is None:
            self._set_text(self._dbm, "")
            return
        if value <= 0.0:
            self._set_text(self._dbm, "")
            return
        dbm = 10.0 * math.log10(value * 1000.0)
        self._set_text(self._dbm, f"{dbm:.3f}")

    def _from_dbm(self) -> None:
        if self._dbm.hasFocus() is False:
            return
        value = self._parse_float(self._dbm)
        if value is None:
            self._set_text(self._watts, "")
            return
        watts = (10.0 ** (value / 10.0)) / 1000.0
        self._set_text(self._watts, f"{watts:.6f}".rstrip("0").rstrip("."))

    @staticmethod
    def _parse_float(field: QLineEdit) -> Optional[float]:
        text = field.text().strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _set_text(field: QLineEdit, value: str) -> None:
        block = field.blockSignals(True)
        field.setText(value)
        field.blockSignals(block)
