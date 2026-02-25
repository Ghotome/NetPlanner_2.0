from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QLocale
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.propagation_model import PropagationModelConfig


class PropagationSettingsDialog(QDialog):
    def __init__(self, model: PropagationModelConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Параметри моделі поширення")
        self.setMinimumWidth(460)
        self._current_model = model
        self._result_model = model
        self._apply_all = False

        self._k_factor = QLineEdit(self)
        self._fresnel_factor = QLineEdit(self)
        self._obstruction_grace = QLineEdit(self)
        self._horizon_extension = QLineEdit(self)
        self._green_threshold = QLineEdit(self)
        self._yellow_threshold = QLineEdit(self)
        self._red_threshold = QLineEdit(self)
        self._field_specs: list[tuple[str, QLineEdit, float, float]] = []

        self._k_factor.setValidator(self._make_validator(0.5, 2.0, 3))
        self._fresnel_factor.setValidator(self._make_validator(0.0, 1.0, 3))
        self._obstruction_grace.setValidator(self._make_validator(0.0, 200.0, 2))
        self._horizon_extension.setValidator(self._make_validator(0.0, 100.0, 2))
        self._green_threshold.setValidator(self._make_validator(-40.0, 40.0, 2))
        self._yellow_threshold.setValidator(self._make_validator(-40.0, 40.0, 2))
        self._red_threshold.setValidator(self._make_validator(-40.0, 40.0, 2))
        self._field_specs = [
            ("k-factor", self._k_factor, 0.5, 2.0),
            ("Коефіцієнт Френеля", self._fresnel_factor, 0.0, 1.0),
            ("Максимальна висота перешкоди", self._obstruction_grace, 0.0, 200.0),
            ("Запас за горизонтом", self._horizon_extension, 0.0, 100.0),
            ("Поріг зеленої зони", self._green_threshold, -40.0, 40.0),
            ("Поріг жовтої зони", self._yellow_threshold, -40.0, 40.0),
            ("Поріг червоної зони", self._red_threshold, -40.0, 40.0),
        ]

        self._set_fields_from_model(model)

        intro = QLabel(
            "Глобальні параметри моделі застосовуються тільки до нових розрахунків.\n"
            "Автоперерахунок всіх антен вимкнено за замовчуванням.\n"
            "Щоб застосувати зміни до всіх антен, натисніть 'Застосувати'.\n",
            self,
        )
        intro.setWordWrap(True)

        form = QFormLayout()
        form.addRow(QLabel("k-factor атмосфери:"), self._k_factor)
        form.addRow(QLabel("Коефіцієнт Френеля (0..1):"), self._fresnel_factor)
        form.addRow(QLabel("Максимальна висота перешкоди (м):"), self._obstruction_grace)
        form.addRow(QLabel("Запас за горизонтом (км):"), self._horizon_extension)
        form.addRow(QLabel("Поріг зеленої зони Δ (dB):"), self._green_threshold)
        form.addRow(QLabel("Поріг жовтої зони Δ (dB):"), self._yellow_threshold)
        form.addRow(QLabel("Поріг червоної зони Δ (dB):"), self._red_threshold)

        ranges = QLabel(
            "Діапазони: k_factor = 0.5-2.0,коефіцієнт Френеля = 0-1, висота перешкоди 0-200 м, запас розрахунків за горизонтом = 0-100 км.",
            self,
        )
        ranges.setWordWrap(True)
        self._validation_hint = QLabel("", self)
        self._validation_hint.setWordWrap(True)
        self._validation_hint.setStyleSheet("color: #dc2626; font-weight: 600;")
        self._validation_hint.hide()

        self._apply_btn = QPushButton("Застосувати", self)
        self._apply_btn.clicked.connect(self._apply_only)
        self._apply_all_btn = QPushButton("Застосувати все", self)
        self._apply_all_btn.setToolTip(
            "Перерахувати всі застосовані антени на всіх сайтах.\n"
            "Може зайняти багато часу і ресурсів."
        )
        self._apply_all_btn.clicked.connect(self._apply_and_recalculate_all)
        reset_btn = QPushButton("Скинути до типових", self)
        reset_btn.setToolTip("Відновити типові параметри моделі.")
        reset_btn.clicked.connect(self._reset_to_defaults)
        cancel_btn = QPushButton("Скасувати", self)
        cancel_btn.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self._apply_btn)
        buttons.addWidget(self._apply_all_btn)
        buttons.addWidget(reset_btn)
        buttons.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(ranges)
        layout.addWidget(self._validation_hint)
        layout.addLayout(buttons)
        self.setLayout(layout)

    def result_model(self) -> PropagationModelConfig:
        return self._result_model

    def should_recalculate_all(self) -> bool:
        return self._apply_all

    def _apply_only(self) -> None:
        model = self._build_model()
        if model is None:
            return
        self._result_model = model
        self._apply_all = False
        self.accept()

    def _apply_and_recalculate_all(self) -> None:
        model = self._build_model()
        if model is None:
            return
        self._result_model = model
        self._apply_all = True
        self.accept()

    def _build_model(self) -> Optional[PropagationModelConfig]:
        parsed_values = self._validate_inputs()
        if parsed_values is None:
            return None
        k_factor = parsed_values["k_factor"]
        fresnel_factor = parsed_values["fresnel_factor"]
        obstruction_grace = parsed_values["obstruction_grace_m"]
        horizon_extension = parsed_values["horizon_extension_km"]
        green_threshold = parsed_values["green_threshold_db"]
        yellow_threshold = parsed_values["yellow_threshold_db"]
        red_threshold = parsed_values["red_threshold_db"]
        return PropagationModelConfig(
            model_version=self._current_model.model_version,
            k_factor=k_factor,
            fresnel_factor=fresnel_factor,
            obstruction_grace_m=obstruction_grace,
            horizon_extension_km=horizon_extension,
            green_threshold_db=green_threshold,
            yellow_threshold_db=yellow_threshold,
            red_threshold_db=red_threshold,
        )

    def _validate_inputs(self) -> Optional[dict[str, float]]:
        self._validation_hint.hide()
        self._validation_hint.clear()
        parsed: dict[str, float] = {}
        mapping = {
            self._k_factor: "k_factor",
            self._fresnel_factor: "fresnel_factor",
            self._obstruction_grace: "obstruction_grace_m",
            self._horizon_extension: "horizon_extension_km",
            self._green_threshold: "green_threshold_db",
            self._yellow_threshold: "yellow_threshold_db",
            self._red_threshold: "red_threshold_db",
        }
        for _, field, _, _ in self._field_specs:
            self._set_field_error(field, None)

        for label, field, lower, upper in self._field_specs:
            text = field.text().strip()
            if not text:
                self._set_field_error(field, f"{label}: обов'язкове поле. Діапазон {lower}..{upper}.")
                return None
            try:
                value = float(text)
            except ValueError:
                self._set_field_error(field, f"{label}: очікується число. Діапазон {lower}..{upper}.")
                return None
            if value < lower or value > upper:
                self._set_field_error(field, f"{label}: поза діапазоном {lower}..{upper}.")
                return None
            key = mapping[field]
            parsed[key] = value

        if parsed["green_threshold_db"] < parsed["yellow_threshold_db"]:
            self._set_field_error(
                self._green_threshold,
                "Пороги зон некоректні: зелена зона повинна бути >= жовтої.",
            )
            return None
        if parsed["yellow_threshold_db"] < parsed["red_threshold_db"]:
            self._set_field_error(
                self._yellow_threshold,
                "Пороги зон некоректні: жовта зона повинна бути >= червоної.",
            )
            return None
        return parsed

    def _set_field_error(self, field: QLineEdit, message: str | None) -> None:
        if not message:
            field.setStyleSheet("")
            field.setToolTip("")
            return
        field.setStyleSheet("border: 1px solid #dc2626;")
        field.setToolTip(message)
        self._validation_hint.setText(message)
        self._validation_hint.show()
        field.setFocus()

    def _set_fields_from_model(self, model: PropagationModelConfig) -> None:
        self._k_factor.setText(f"{model.k_factor:.3f}")
        self._fresnel_factor.setText(f"{model.fresnel_factor:.3f}")
        self._obstruction_grace.setText(f"{model.obstruction_grace_m:.2f}")
        self._horizon_extension.setText(f"{model.horizon_extension_km:.2f}")
        self._green_threshold.setText(f"{model.green_threshold_db:.2f}")
        self._yellow_threshold.setText(f"{model.yellow_threshold_db:.2f}")
        self._red_threshold.setText(f"{model.red_threshold_db:.2f}")
        for _, field, _, _ in self._field_specs:
            self._set_field_error(field, None)
        self._validation_hint.hide()

    def _reset_to_defaults(self) -> None:
        defaults = PropagationModelConfig(model_version=self._current_model.model_version)
        self._set_fields_from_model(defaults)

    def _make_validator(self, bottom: float, top: float, decimals: int) -> QDoubleValidator:
        validator = QDoubleValidator(bottom, top, decimals, self)
        validator.setLocale(QLocale.c())
        return validator
