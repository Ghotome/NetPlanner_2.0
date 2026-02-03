from __future__ import annotations

from PySide6.QtCore import QLocale
from PySide6.QtGui import QDoubleValidator, QValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.domain import CableType, LinkKind, LinkType


class SiteLinkDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Параметри лінка")
        self.setMinimumWidth(320)

        self._kind = QComboBox(self)
        options = [
            ("PtP", LinkKind.PTP),
            ("PtMP", LinkKind.PTMP),
            ("Ethernet", LinkKind.ETHERNET),
        ]
        for label, kind in options:
            self._kind.addItem(label, kind)
        self._kind.currentIndexChanged.connect(self._toggle_fields)

        self._frequency = QLineEdit(self)
        freq_validator = QDoubleValidator(0.0001, 30.0, 6, self)
        freq_validator.setLocale(QLocale.c())
        self._frequency.setValidator(freq_validator)
        self._frequency_hint = QLabel("Діапазон: 0.0001–30 ГГц.", self)
        self._frequency_hint.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        self._frequency.textChanged.connect(self._validate_fields)
        self._ssid = QLineEdit(self)
        self._password = QLineEdit(self)
        self._password.setEchoMode(QLineEdit.EchoMode.Normal)
        self._name = QLineEdit(self)
        self._notes = QTextEdit(self)

        self._link_type = QComboBox(self)
        link_options = [
            ("Fast Ethernet", LinkType.FAST_ETH),
            ("Gigabit Ethernet", LinkType.GIG_ETH),
            ("Оптика", LinkType.OPTICAL),
        ]
        for label, ltype in link_options:
            self._link_type.addItem(label, ltype)

        self._cable_type = QComboBox(self)
        cable_options = [
            ("Зовнішній", CableType.OUTDOOR),
            ("Внутрішній", CableType.INDOOR),
        ]
        for label, ctype in cable_options:
            self._cable_type.addItem(label, ctype)

        self._label_frequency = QLabel("Частота (ГГц)")
        self._label_ssid = QLabel("SSID")
        self._label_password = QLabel("Пароль")
        self._label_eth_type = QLabel("Тип лінка (Ethernet)")
        self._label_cable = QLabel("Тип кабелю")

        form = QVBoxLayout()
        form.addWidget(QLabel("Назва лінка"))
        form.addWidget(self._name)
        form.addWidget(QLabel("Тип лінка"))
        form.addWidget(self._kind)
        form.addWidget(self._label_frequency)
        form.addWidget(self._frequency)
        form.addWidget(self._frequency_hint)
        form.addWidget(self._label_ssid)
        form.addWidget(self._ssid)
        form.addWidget(self._label_password)
        form.addWidget(self._password)
        form.addWidget(self._label_eth_type)
        form.addWidget(self._link_type)
        form.addWidget(self._label_cable)
        form.addWidget(self._cable_type)
        form.addWidget(QLabel("Нотатки"))
        form.addWidget(self._notes)

        actions = QHBoxLayout()
        self._save_btn = QPushButton("Зберегти", self)
        cancel_btn = QPushButton("Скасувати", self)
        self._save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        actions.addStretch(1)
        actions.addWidget(self._save_btn)
        actions.addWidget(cancel_btn)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(actions)
        self.setLayout(layout)
        self._toggle_fields()
        self._validate_fields()

    def link_kind(self) -> LinkKind:
        return self._kind.currentData()

    def link_name(self) -> str:
        return self._name.text().strip()

    def link_label(self) -> str:
        return self._kind.currentText()

    def frequency_ghz(self) -> float | None:
        value = self._frequency.text().strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None


    def ssid(self) -> str | None:
        return self._ssid.text().strip() or None

    def password(self) -> str | None:
        return self._password.text().strip() or None

    def notes_text(self) -> str | None:
        return self._notes.toPlainText().strip() or None

    def ethernet_link_type(self) -> LinkType | None:
        return self._link_type.currentData()

    def ethernet_cable_type(self) -> CableType | None:
        return self._cable_type.currentData()

    def _toggle_fields(self) -> None:
        kind = self.link_kind()
        is_wireless = kind in (LinkKind.PTP, LinkKind.PTMP)
        for widget in (self._label_frequency, self._frequency, self._label_ssid, self._ssid, self._label_password, self._password):
            widget.setVisible(is_wireless)
        self._frequency_hint.setVisible(is_wireless)
        for widget in (self._label_eth_type, self._link_type, self._label_cable, self._cable_type):
            widget.setVisible(not is_wireless)
        self._validate_fields()

    def _validate_fields(self) -> None:
        kind = self.link_kind()
        is_wireless = kind in (LinkKind.PTP, LinkKind.PTMP)
        valid = True
        if is_wireless:
            valid = self._is_field_valid(self._frequency)
            self._set_field_validity(self._frequency, valid)
        else:
            self._set_field_validity(self._frequency, True)
        self._save_btn.setEnabled(valid)

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

    def accept(self) -> None:
        kind = self.link_kind()
        if kind in (LinkKind.PTP, LinkKind.PTMP):
            value = self._frequency.text().strip()
            if value:
                try:
                    float(value)
                except ValueError:
                    QMessageBox.warning(self, "Помилка", "Частота повинна бути числом.")
                    return
        super().accept()
