from __future__ import annotations

from PySide6.QtCore import Qt, QLocale
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QLabel, QVBoxLayout


class FrequencyCalculatorDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Калькулятор частоти")
        self.setMinimumWidth(340)

        self._updating = False

        self._khz = QLineEdit(self)
        self._mhz = QLineEdit(self)
        self._ghz = QLineEdit(self)

        self._khz.setPlaceholderText("1000 – 30000000")
        self._mhz.setPlaceholderText("1 – 30000")
        self._ghz.setPlaceholderText("0.001 – 30")

        khz_validator = QDoubleValidator(1000.0, 30000000.0, 6, self)
        mhz_validator = QDoubleValidator(1.0, 30000.0, 6, self)
        ghz_validator = QDoubleValidator(0.001, 30.0, 6, self)
        for v in (khz_validator, mhz_validator, ghz_validator):
            v.setNotation(QDoubleValidator.Notation.StandardNotation)
            v.setLocale(QLocale.c())

        self._khz.setValidator(khz_validator)
        self._mhz.setValidator(mhz_validator)
        self._ghz.setValidator(ghz_validator)

        self._khz.textChanged.connect(lambda _t: self._on_change("khz"))
        self._mhz.textChanged.connect(lambda _t: self._on_change("mhz"))
        self._ghz.textChanged.connect(lambda _t: self._on_change("ghz"))

        form = QFormLayout()
        form.addRow(QLabel("кГц:"), self._khz)
        form.addRow(QLabel("МГц:"), self._mhz)
        form.addRow(QLabel("ГГц:"), self._ghz)

        hint = QLabel("Діапазон: 1 МГц – 30 ГГц (еквівалент у всіх полях).", self)
        hint.setStyleSheet("color: #9aa0a6; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addStretch(1)

    def _on_change(self, source: str) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            if source == "khz":
                value = self._parse_value(self._khz.text())
                if value is None:
                    self._clear_others()
                else:
                    self._mhz.setText(self._format(value / 1000.0))
                    self._ghz.setText(self._format(value / 1_000_000.0))
            elif source == "mhz":
                value = self._parse_value(self._mhz.text())
                if value is None:
                    self._clear_others()
                else:
                    self._khz.setText(self._format(value * 1000.0))
                    self._ghz.setText(self._format(value / 1000.0))
            else:
                value = self._parse_value(self._ghz.text())
                if value is None:
                    self._clear_others()
                else:
                    self._mhz.setText(self._format(value * 1000.0))
                    self._khz.setText(self._format(value * 1_000_000.0))
        finally:
            self._updating = False

    def _clear_others(self) -> None:
        if self._khz.hasFocus():
            self._mhz.clear()
            self._ghz.clear()
        elif self._mhz.hasFocus():
            self._khz.clear()
            self._ghz.clear()
        else:
            self._khz.clear()
            self._mhz.clear()

    @staticmethod
    def _parse_value(text: str) -> float | None:
        text = text.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _format(value: float) -> str:
        return f"{value:.6f}".rstrip("0").rstrip(".")
