from __future__ import annotations

from datetime import datetime
import base64
import io
import os
import sys
from pathlib import Path
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import asin, atan2, ceil, cos, degrees, floor, log10, radians, sin, sqrt
from uuid import uuid4
from threading import Lock

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QToolTip,
    QTreeWidgetItem,
    QDialog,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QAction, QPalette

from app.coverage import CoverageCalculator
from app.domain import AntennaParams, GeoPoint, Link, LinkKind, NetworkProject, Site, SiteKind, StatusState
from app.elevation import ElevationProvider
from app.link_analyzer import LinkAnalyzer, LinkProfile
from app.project_io import load_project, save_project
from app.monitoring import PingChecker
from app.ui.monitoring_panel import MonitoringPanel
from app.ui.inspector import InspectorPanel
from app.ui.link_profile_dialog import LinkProfileDialog
from app.ui.link_dialog import SiteLinkDialog
from app.ui.eirp_calculator import EirpCalculatorDialog
from app.ui.horizon_calculator import HorizonCalculatorDialog
from app.ui.watt_dbm_calculator import WattDbmCalculatorDialog
from app.ui.frequency_calculator import FrequencyCalculatorDialog
from app.ui.map_view import MapView
from app.ui.project_tree import ProjectTree
from app.ui.site_dialog import SiteDevicesDialog
from app.ui.monitoring_panel import MonitoringPanel

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None


class MainWindow(QMainWindow):
    prefetch_finished = Signal(int)
    coverage_result_ready = Signal(str, int, object)
    coverage_tile_ready = Signal(str, int, object)

    def __init__(self, project: NetworkProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project = project

        self.setWindowTitle("NetPlanner 2.0")
        self.resize(1280, 720)
        self.setMinimumSize(900, 600)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        self.project_tree = ProjectTree(self)
        self.project_tree.set_project(project)
        self.project_tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self.project_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)

        self.map_view = MapView(
            on_show_context_menu=self._on_map_context_menu,
            on_show_site_menu=self._on_map_site_menu,
            on_show_link_menu=self._on_map_link_menu,
            on_report_height=self._on_report_height,
            on_map_click=self._on_map_click,
            on_request_move_node=self._on_map_request_move_node,
            on_request_site_link=self._on_map_request_site_link,
            on_request_delete_link=self._on_map_request_delete_link,
            on_select_link=self._on_map_select_link,
            on_prefetch_elevation=self._on_prefetch_elevation,
            on_request_rename_site=self._on_map_request_rename_site,
            on_select_node=self._on_map_select_node,
            on_open_site=self._on_map_open_site,
            on_set_height_mode=self._set_height_mode_from_map,
            on_set_azimuth_mode=self._set_azimuth_mode_from_map,
            on_set_ruler_mode=self._set_ruler_mode_from_map,
            on_set_los_mode=self._set_los_mode_from_map,
            on_open_eirp=self._open_eirp_calculator,
            on_open_horizon=self._open_horizon_calculator,
            on_open_power=self._open_power_calculator,
            on_open_frequency=self._open_frequency_calculator,
            parent=self,
        )

        self.inspector = InspectorPanel(self)
        self.inspector.link_updated.connect(self._on_inspector_link_updated)
        self.inspector.link_analyze_requested.connect(self._on_link_analyze_requested)
        self.inspector.site_updated.connect(self._on_site_updated)
        self.monitoring_panel = MonitoringPanel(self)
        self._elevation = ElevationProvider(tile_cache_size=128)
        self._link_analyzer = LinkAnalyzer(self._elevation)
        self._coverage_calc = CoverageCalculator()
        self._bg_executor = ThreadPoolExecutor(max_workers=2)
        self._prefetch_token = 0
        self._coverage_job_seq = 0
        self._coverage_job_for_key: dict[str, int] = {}
        self._busy_count = 0
        self.prefetch_finished.connect(self._finish_prefetch)
        self.coverage_result_ready.connect(self._apply_coverage_result)
        self.coverage_tile_ready.connect(self._apply_coverage_tile)
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.timeout.connect(self._prefetch_elevation_for_view)
        self._memory_limit_mb = 2048
        self._memory_guard_timer = QTimer(self)
        self._memory_guard_timer.setInterval(20000)
        self._memory_guard_timer.timeout.connect(self._enforce_memory_limit)
        self._memory_guard_timer.start()
        self._pending_bounds = None
        self._pending_zoom = None
        self._site_status_cache: dict[str, StatusState] = {}
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(1000)
        self._monitor_timer.timeout.connect(self._refresh_monitoring)
        self._monitor_timer.start()

        right_splitter = QSplitter(Qt.Orientation.Vertical, self)
        right_splitter.addWidget(self.inspector)
        right_splitter.addWidget(self.monitoring_panel)
        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 1)

        splitter = QSplitter(self)
        splitter.addWidget(self.project_tree)
        splitter.addWidget(self.map_view)
        splitter.addWidget(right_splitter)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([220, 900, 260])

        self.setCentralWidget(splitter)
        self._init_actions()
        self._init_menu_bar()
        self._apply_styles()
        self._site_counter = 1
        self.destroyed.connect(self._cleanup_on_close)
        self._pending_link_site_id: str | None = None
        self._height_mode = False
        self._height_timer = QTimer(self)
        self._height_timer.setSingleShot(True)
        self._height_timer.timeout.connect(self._show_height_tooltip)
        self._pending_height: tuple[float, float, int, int] | None = None
        self._los_mode = False
        self._los_points: list[tuple[float, float]] = []
        self._horizon_mode = False
        self._horizon_points: list[tuple[float, float]] = []
        self._project_path: str | None = None
        self._dirty = False
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(20000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()
        self._ping_checker = PingChecker(self._all_devices())
        self._ping_checker.status_updated.connect(self._on_device_ping_status)
        self._ping_checker.start()

        self.project_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.project_tree.customContextMenuRequested.connect(self._on_tree_context_menu)

    def closeEvent(self, event):  # noqa: N802
        if self._dirty:
            response = QMessageBox.question(
                self,
                "Зберегти зміни?",
                "Є незбережені зміни. Зберегти перед виходом?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if response == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if response == QMessageBox.StandardButton.Yes:
                self._save_project()
        self._cleanup_on_close()
        super().closeEvent(event)

    def _init_actions(self) -> None:
        self._elevation_action = QAction("Шар висот", self)
        self._elevation_action.setCheckable(True)
        self._elevation_action.toggled.connect(self._toggle_elevation_layer)

        self._coverage_action = QAction("Покриття", self)
        self._coverage_action.setCheckable(True)
        self._coverage_action.setChecked(True)
        self._coverage_action.toggled.connect(self._toggle_coverage_layer)

        self._height_action = QAction("Визначити висоту", self)
        self._height_action.setCheckable(True)
        self._height_action.toggled.connect(self._toggle_height_mode)

        self._azimuth_action = QAction("Азимут", self)
        self._azimuth_action.setCheckable(True)
        self._azimuth_action.toggled.connect(self._toggle_azimuth_mode)

        self._ruler_action = QAction("Лінійка", self)
        self._ruler_action.setCheckable(True)
        self._ruler_action.toggled.connect(self._toggle_ruler_mode)

        self._eirp_action = QAction("Калькулятор EIRP", self)
        self._eirp_action.triggered.connect(self._open_eirp_calculator)

        self._los_action = QAction("Розрахувати пряму видимість", self)
        self._los_action.setCheckable(True)
        self._los_action.toggled.connect(self._toggle_los_mode)

    def _confirm_action(self, title: str, message: str) -> bool:
        return (
            QMessageBox.question(
                self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            == QMessageBox.StandardButton.Yes
        )

    def _toggle_elevation_layer(self, enabled: bool) -> None:
        self.map_view.set_elevation_layer(enabled)
        if enabled:
            self._schedule_elevation_prefetch()

    def _toggle_coverage_layer(self, enabled: bool) -> None:
        self.map_view.set_coverage_visible(enabled)

    def _toggle_height_mode(self, enabled: bool) -> None:
        self._height_mode = enabled
        self._pending_height = None
        self.map_view.set_height_mode(enabled)
        if not enabled:
            QToolTip.hideText()
            self.statusBar().clearMessage()
        else:
            self.statusBar().showMessage("Наведіть курсор на точку на мапі для заміру висоти.")

    def _toggle_azimuth_mode(self, enabled: bool) -> None:
        if enabled and self._height_action.isChecked():
            self._height_action.setChecked(False)
        if enabled and self._los_mode:
            self._los_mode = False
            self._los_points = []
            self.map_view.set_los_mode(False)
            if self._los_action.isChecked():
                self._los_action.setChecked(False)
            self.statusBar().clearMessage()
        if enabled and self._ruler_action.isChecked():
            self._ruler_action.setChecked(False)
        self.map_view.set_azimuth_mode(enabled)
        if enabled:
            self.statusBar().showMessage("Натисніть ЛКМ, щоб розпочати. Натисніть ЛКМ, щоб завершити вимірювання.")
        else:
            self.statusBar().clearMessage()

    def _toggle_ruler_mode(self, enabled: bool) -> None:
        if enabled and self._height_action.isChecked():
            self._height_action.setChecked(False)
        if enabled and self._los_mode:
            self._los_mode = False
            self._los_points = []
            self.map_view.set_los_mode(False)
            if self._los_action.isChecked():
                self._los_action.setChecked(False)
            self.statusBar().clearMessage()
        if enabled and self._azimuth_action.isChecked():
            self._azimuth_action.setChecked(False)
        self.map_view.set_ruler_mode(enabled)
        if enabled:
            self.statusBar().showMessage("Натисніть ЛКМ в зоні мапи, щоб додати точку виміру. Натисніть ПКМ, щоб завершити вимірювання.")
        else:
            self.statusBar().clearMessage()

    def _set_height_mode_from_map(self, enabled: bool) -> None:
        self._height_action.setChecked(enabled)

    def _set_azimuth_mode_from_map(self, enabled: bool) -> None:
        self._azimuth_action.setChecked(enabled)

    def _set_ruler_mode_from_map(self, enabled: bool) -> None:
        self._ruler_action.setChecked(enabled)

    def _set_los_mode_from_map(self, enabled: bool) -> None:
        self._los_action.setChecked(enabled)

    def _init_menu_bar(self) -> None:
        menu = self.menuBar()
        menu.setNativeMenuBar(False)
        menu.clear()
        file_menu = menu.addMenu("Файл")
        file_menu.addAction("Новий проєкт", self._new_project, "Ctrl+N")
        file_menu.addAction("Відкрити", self._open_project, "Ctrl+O")
        file_menu.addAction("Зберегти", self._save_project, "Ctrl+S")
        file_menu.addAction("Зберегти як", self._save_project_as, "Ctrl+Shift+S")
        file_menu.addSeparator()
        file_menu.addAction("Вихід", self.close, "Ctrl+Q")

        help_menu = menu.addMenu("Довідка")
        help_menu.addAction("Про програму", self._about)

    def _apply_styles(self) -> None:
        palette = QApplication.palette()
        window = palette.color(QPalette.Window).name()
        base = palette.color(QPalette.Base).name()
        text = palette.color(QPalette.Text).name()
        button = palette.color(QPalette.Button).name()
        button_text = palette.color(QPalette.ButtonText).name()
        mid = palette.color(QPalette.Mid).name()
        dark = palette.color(QPalette.Dark).name()
        highlight = palette.color(QPalette.Highlight).name()
        highlight_text = palette.color(QPalette.HighlightedText).name()
        self.setStyleSheet(
            f"""
            QMainWindow {{ background: {window}; }}
            QToolBar {{ background: {window}; border-bottom: 1px solid {mid}; }}
            QSplitter::handle {{ background: {mid}; }}
            QTreeWidget, QListWidget {{ background: {base}; border: 1px solid {mid}; }}
            QLineEdit, QComboBox {{ background: {base}; color: {text}; border: 1px solid {dark}; padding: 4px; border-radius: 4px; }}
            QLineEdit:focus, QComboBox:focus {{ border: 1px solid {highlight}; }}
            QPushButton {{ background: {button}; color: {button_text}; border: 1px solid {dark}; padding: 6px 10px; border-radius: 6px; font-weight: 600; }}
            QPushButton:hover {{ background: {mid}; }}
            QPushButton:pressed {{ background: {highlight}; color: {highlight_text}; }}
            QLabel {{ color: {text}; }}
            QComboBox QAbstractItemView {{
                background: {base};
                color: {text};
                selection-background-color: {highlight};
                selection-color: {highlight_text};
                outline: 1px solid {mid};
            }}
            QComboBox QAbstractItemView::item:selected {{
                border: 1px solid {highlight_text};
            }}
            """
        )

    def _about(self) -> None:
        QMessageBox.information(self, "Про програму", "NetPlaner v2.0\nBy R & Mr. GPT")

    def _show_user_guide(self) -> None:
        guide_path = Path(__file__).resolve().parents[1] / "USER_GUIDE.md"
        if not guide_path.exists():
            QMessageBox.information(self, "Гайд користувача", "Файл USER_GUIDE.md не знайдено.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Гайд користувача")
        dialog.resize(760, 600)
        text = QTextEdit(dialog)
        text.setReadOnly(True)
        text.setPlainText(guide_path.read_text(encoding="utf-8"))
        layout = QVBoxLayout(dialog)
        layout.addWidget(text)
        dialog.setLayout(layout)
        dialog.exec()

    def _on_map_context_menu(self, lat: float, lon: float, x: int, y: int) -> None:
        menu = QMenu(self)
        menu.setTitle("Створити")

        actions = [
            ("Створити CORE сайт", SiteKind.CORE),
            ("Створити POP сайт", SiteKind.POP),
            ("Створити CPE сайт", SiteKind.CPE),
        ]

        action_map = {}
        for label, kind in actions:
            action_map[menu.addAction(label)] = kind

        chosen = menu.exec(self.map_view.mapToGlobal(QPoint(x, y)))
        if chosen is None:
            return
        kind = action_map.get(chosen)
        if kind is None:
            return

        name = f"{kind.value.upper()} {self._site_counter}"
        confirm = self._confirm_action(
            "Підтвердження",
            f"Створити {kind.value.upper()} сайт '{name}' у точці {lat:.6f}, {lon:.6f}?",
        )
        if not confirm:
            return

        site_id = uuid4().hex[:8]
        self._site_counter += 1
        site = Site(
            id=site_id,
            name=name,
            kind=kind,
            location=GeoPoint(lat=lat, lon=lon),
        )
        self._project.add_site(site)
        site_kind_value = self._site_kind_value(site)
        self.project_tree.add_node(site.id, f"{site.name} ({site_kind_value})")
        self.map_view.add_marker(site.id, site.name, self._site_kind_label(site_kind_value), lat, lon)
        self.inspector.show_site(site)
        self._dirty = True
        self._ping_checker.set_devices(self._all_devices())
        self._refresh_monitoring()

    def _on_map_request_move_node(
        self, site_id: str, lat: float, lon: float, prev_lat: float, prev_lon: float
    ) -> None:
        site = self._project.sites.get(site_id)
        if site is None:
            return
        confirm = self._confirm_action(
            "Підтвердження",
            f"Перемістити '{site.name}' у {lat:.6f}, {lon:.6f}?",
        )
        if not confirm:
            self.map_view.move_marker(site_id, prev_lat, prev_lon)
            return
        site.location = GeoPoint(lat=lat, lon=lon)
        for link in self._project.links.values():
            if link.site_a_id == site_id or link.site_b_id == site_id:
                a = self._project.sites.get(link.site_a_id)
                b = self._project.sites.get(link.site_b_id)
                if a and b:
                    link.distance_km = self._distance_km(
                        a.location.lat, a.location.lon, b.location.lat, b.location.lon
                    )
                    self.map_view.update_link_meta(
                        link.id,
                        self._link_display_label(link),
                        self._link_kind_value(link.kind),
                        self._link_info(link, a),
                        link.distance_km,
                    )
                    self.map_view.update_link(
                        link.id,
                        a.location.lat,
                        a.location.lon,
                        b.location.lat,
                        b.location.lon,
                    )
        self._update_site_coverages(site)
        if self.project_tree.currentItem() is not None:
            current_id = self.project_tree.currentItem().data(0, Qt.ItemDataRole.UserRole)
            if current_id == site_id:
                self.inspector.show_site(site)
        self._dirty = True

    def _on_map_select_node(self, site_id: str) -> None:
        self.project_tree.select_node(site_id)
        site = self._project.sites.get(site_id)
        self.inspector.show_site(site)
        self.map_view.focus_marker(site_id)
        if self._pending_link_site_id and self._pending_link_site_id != site_id:
            start_id = self._pending_link_site_id
            self._pending_link_site_id = None
            self.statusBar().clearMessage()
            self._on_map_request_site_link(start_id, site_id)
        if site is None:
            return
        elevation = self._elevation.get_elevation(site.location.lat, site.location.lon)
        self.inspector.set_site_elevation(elevation, self._elevation.available)
        self._ping_checker.set_devices(self._all_devices())
        self._refresh_monitoring()

    def _on_map_open_site(self, site_id: str) -> None:
        self._open_site_dialog(site_id)

    def _on_map_select_link(self, link_id: str) -> None:
        link = self._project.links.get(link_id)
        if link is None:
            return
        site_a = self._project.sites.get(link.site_a_id)
        site_b = self._project.sites.get(link.site_b_id)
        self.project_tree.select_link(link_id)
        self.inspector.show_link(link, site_a.name if site_a else "—", site_b.name if site_b else "—")

    def _on_map_request_rename_site(self, site_id: str) -> None:
        site = self._project.sites.get(site_id)
        if not site:
            return
        new_name, ok = QInputDialog.getText(self, "Перейменувати сайт", "Нова назва:", text=site.name)
        if ok and new_name.strip():
            site.name = new_name.strip()
            self.map_view.update_marker_label(site.id, site.name, self._site_kind_label(self._site_kind_value(site)))
            self._update_site_coverages(site)
            self.project_tree.set_project(self._project)
            self._dirty = True

    def _on_report_height(self, lat: float, lon: float, x: int, y: int) -> None:
        if not self._height_mode:
            return
        self._pending_height = (lat, lon, x, y)
        self._height_timer.start(120)

    def _show_height_tooltip(self) -> None:
        if not self._pending_height:
            return
        lat, lon, x, y = self._pending_height
        if not self._elevation.available:
            text = "Немає даних (Pillow?)"
        else:
            elev = self._elevation.get_elevation(lat, lon)
            text = "—" if elev is None else f"Висота: {elev:.1f} м"
        pos = self.map_view.mapToGlobal(QPoint(x, y))
        QToolTip.showText(pos, text, self.map_view)

    def _open_eirp_calculator(self) -> None:
        antenna = None
        item = self.project_tree.currentItem()
        if item is not None:
            node_id = item.data(0, Qt.ItemDataRole.UserRole)
            site_id = node_id.split(":", 1)[0] if isinstance(node_id, str) else node_id
            site = self._project.sites.get(site_id)
            if site:
                antenna = next((a for a in site.antennas if a.applied), None) or (
                    site.antennas[0] if site.antennas else None
                )
        dialog = EirpCalculatorDialog(antenna, self)
        dialog.exec()

    def _toggle_los_mode(self, enabled: bool) -> None:
        if enabled:
            QMessageBox.information(
                self,
                "LOS",
                "Оберіть 2 точки на мапі для розрахунку траекторії прямої видимості між ними.",
            )
            self._los_mode = True
            self._los_points = []
            self.map_view.set_los_mode(True)
            self.statusBar().showMessage("LOS: оберіть 2 точки на мапі")
        else:
            self._los_mode = False
            self._los_points = []
            self.map_view.set_los_mode(False)
            self.statusBar().clearMessage()

    def _open_horizon_calculator(self) -> None:
        QMessageBox.information(
            self,
            "Горизонт",
            "Оберіть 2 точки на мапі: передавач і приймач.\n"
            "Після вибору буде доступне введення висоти антен для розрахунку горизонту.\n"
            "Рослинність і забудова не враховані, реальний горизонт буде меншим.",
        )
        self._horizon_mode = True
        self._horizon_points = []
        self.map_view.clear_horizon_points()
        self.statusBar().showMessage("Горизонт: оберіть 2 точки на мапі")

    def _open_power_calculator(self) -> None:
        dialog = WattDbmCalculatorDialog(self)
        dialog.exec()

    def _open_frequency_calculator(self) -> None:
        dialog = FrequencyCalculatorDialog(self)
        dialog.exec()

    def _on_map_click(self, lat: float, lon: float) -> None:
        if self._horizon_mode:
            self._horizon_points.append((lat, lon))
            self.map_view.add_horizon_point(lat, lon)
            if len(self._horizon_points) < 2:
                self.statusBar().showMessage("Горизонт: оберіть другу точку")
                return
            a, b = self._horizon_points
            self._horizon_mode = False
            self._horizon_points = []
            self.statusBar().clearMessage()
            self._open_horizon_dialog(a, b)
            return

        if not self._los_mode:
            return
        self._los_points.append((lat, lon))
        if len(self._los_points) < 2:
            self.statusBar().showMessage("LOS: оберіть другу точку")
            return
        a, b = self._los_points
        self._los_mode = False
        self._los_points = []
        self.map_view.set_los_mode(False)
        self.statusBar().clearMessage()
        if self._los_action.isChecked():
            self._los_action.setChecked(False)
        self._run_los_between_points(a, b)

    def _open_horizon_dialog(self, a: tuple[float, float], b: tuple[float, float]) -> None:
        if not self._elevation.available:
            QMessageBox.warning(self, "Горизонт", "Немає даних висот (Pillow?)")
            self.map_view.clear_horizon_points()
            return
        lat1, lon1 = a
        lat2, lon2 = b
        elev_a = self._elevation.get_elevation(lat1, lon1)
        elev_b = self._elevation.get_elevation(lat2, lon2)
        if elev_a is None or elev_b is None:
            QMessageBox.warning(self, "Горизонт", "Немає даних висот для обраних точок")
            self.map_view.clear_horizon_points()
            return
        distance_km = self._distance_km(lat1, lon1, lat2, lon2)
        dialog = HorizonCalculatorDialog(elev_a, elev_b, distance_km, self)
        dialog.exec()
        self.map_view.clear_horizon_points()

    def _run_los_between_points(self, a: tuple[float, float], b: tuple[float, float]) -> None:
        if not self._elevation.available:
            QMessageBox.warning(self, "LOS", "Немає даних висот (Pillow?)")
            return
        lat1, lon1 = a
        lat2, lon2 = b
        samples = 40
        total_km = self._distance_km(lat1, lon1, lat2, lon2)
        distances = []
        elevations = []
        for i in range(samples + 1):
            t = i / samples
            lat = lat1 + (lat2 - lat1) * t
            lon = lon1 + (lon2 - lon1) * t
            elev = self._elevation.get_elevation(lat, lon)
            if elev is None:
                QMessageBox.warning(self, "LOS", "Немає даних висот для траси")
                return
            elevations.append(elev)
            distances.append(total_km * t)
        start = elevations[0]
        end = elevations[-1]
        blocked = False
        max_obstruction = 0.0
        for i in range(1, len(elevations) - 1):
            expected = start + (end - start) * (distances[i] / total_km if total_km else 0.0)
            obstruction = elevations[i] - expected
            if obstruction > 0:
                blocked = True
                max_obstruction = max(max_obstruction, obstruction)
        status = "LOS OK" if not blocked else "Blocked"
        profile = LinkProfile(
            distances_km=distances,
            elevations_m=elevations,
            los_ok=not blocked,
            clearance_needed_m=max_obstruction if blocked else 0.0,
            status=status,
        )
        dialog = LinkProfileDialog(profile, self)
        dialog.exec()

    def _on_map_site_menu(self, site_id: str, x: int, y: int) -> None:
        site = self._project.sites.get(site_id)
        if not site:
            return
        menu = QMenu(self)
        rename_action = menu.addAction("Перейменувати")
        link_action = menu.addAction("Створити лінк")
        delete_action = menu.addAction("Видалити сайт")
        chosen = menu.exec(self.map_view.mapToGlobal(QPoint(x, y)))
        if chosen == rename_action:
            self._on_map_request_rename_site(site_id)
            return
        if chosen == link_action:
            self._pending_link_site_id = site_id
            self.statusBar().showMessage("Оберіть цільовий сайт для лінку")
            return
        if chosen == delete_action:
            self._delete_site(site_id)

    def _on_map_link_menu(self, link_id: str, x: int, y: int) -> None:
        link = self._project.links.get(link_id)
        if not link:
            return
        self.project_tree.select_link(link_id)
        site_a = self._project.sites.get(link.site_a_id)
        site_b = self._project.sites.get(link.site_b_id)
        self.inspector.show_link(
            link,
            site_a.name if site_a else "—",
            site_b.name if site_b else "—",
        )
        menu = QMenu(self)
        delete_action = menu.addAction("Видалити лінк")
        chosen = menu.exec(self.map_view.mapToGlobal(QPoint(x, y)))
        if chosen == delete_action:
            self._on_map_request_delete_link(link_id)

    def _on_tree_selection_changed(self) -> None:
        item = self.project_tree.currentItem()
        if item is None:
            self.inspector.show_site(None)
            return
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        site_id = node_id.split(":", 1)[0] if isinstance(node_id, str) else node_id
        if isinstance(site_id, str) and site_id in self._project.links:
            link = self._project.links.get(site_id)
            if link is None:
                return
            site_a = self._project.sites.get(link.site_a_id)
            site_b = self._project.sites.get(link.site_b_id)
            self.inspector.show_link(
                link,
                site_a.name if site_a else "—",
                site_b.name if site_b else "—",
            )
            return
        site = self._project.sites.get(site_id)
        self.inspector.show_site(site)
        if site is not None:
            elevation = self._elevation.get_elevation(site.location.lat, site.location.lon)
            self.inspector.set_site_elevation(elevation, self._elevation.available)
            self.map_view.focus_marker(site.id)
            self._update_site_coverages(site)

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if item is None:
            return
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not node_id:
            return
        site_id = node_id.split(":", 1)[0] if isinstance(node_id, str) else node_id
        if isinstance(site_id, str) and site_id in self._project.sites:
            self._open_site_dialog(site_id)

    def _open_site_dialog(self, site_id: str) -> None:
        site = self._project.sites.get(site_id)
        if site is None:
            return
        dialog = SiteDevicesDialog(site, self)
        dialog.exec()
        self.project_tree.set_project(self._project)
        self.project_tree.select_node(site.id)
        self._ping_checker.set_devices(self._all_devices())
        self._refresh_monitoring()

    def _schedule_elevation_prefetch(self) -> None:
        self._prefetch_timer.start(400)

    def _prefetch_elevation_for_view(self) -> None:
        if self._pending_bounds is None or self._pending_zoom is None:
            return
        bounds = self._pending_bounds
        zoom = self._pending_zoom
        self._prefetch_token += 1
        token = self._prefetch_token
        self._set_busy("Завантаження висот…")
        future = self._bg_executor.submit(self._elevation.prefetch_tiles, bounds, zoom)
        future.add_done_callback(lambda _f, t=token: self.prefetch_finished.emit(t))

    def _on_prefetch_elevation(
        self, south: float, west: float, north: float, east: float, zoom: int
    ) -> None:
        self._pending_bounds = (south, west, north, east)
        self._pending_zoom = int(zoom)
        self._schedule_elevation_prefetch()


    def _on_map_request_site_link(self, site_a_id: str, site_b_id: str) -> None:
        site_a = self._project.sites.get(site_a_id)
        site_b = self._project.sites.get(site_b_id)
        if site_a is None or site_b is None:
            return

        dialog = SiteLinkDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        kind = dialog.link_kind()
        is_wireless = kind in (LinkKind.PTP, LinkKind.PTMP)
        name = dialog.link_name() or f"{site_a.name} ↔ {site_b.name}"
        link = Link(
            id=uuid4().hex[:8],
            name=name,
            kind=kind,
            site_a_id=site_a.id,
            site_b_id=site_b.id,
            notes_text=dialog.notes_text(),
            frequency_ghz=dialog.frequency_ghz() if is_wireless else None,
            ssid=dialog.ssid() if is_wireless else None,
            password=dialog.password() if is_wireless else None,
            link_type=None if is_wireless else dialog.ethernet_link_type(),
            cable_type=None if is_wireless else dialog.ethernet_cable_type(),
            distance_km=self._distance_km(site_a.location.lat, site_a.location.lon, site_b.location.lat, site_b.location.lon),
        )
        self._project.add_link(link)
        self.project_tree.set_project(self._project)
        self.map_view.add_link(
            link.id,
            self._link_display_label(link),
            self._link_kind_value(link.kind),
            self._link_info(link, site_a),
            link.distance_km,
            site_a.location.lat,
            site_a.location.lon,
            site_b.location.lat,
            site_b.location.lon,
        )
        self._dirty = True

    def _on_map_request_delete_link(self, link_id: str) -> None:
        link = self._project.links.get(link_id)
        if link is None:
            return
        confirm = self._confirm_action(
            "Підтвердження",
            f"Видалити лінк '{link.name}'?",
        )
        if not confirm:
            return
        self._project.remove_link(link_id)
        self.project_tree.set_project(self._project)
        self.map_view.remove_link(link_id)
        self._dirty = True

    def _delete_site(self, site_id: str) -> None:
        site = self._project.sites.get(site_id)
        if not site:
            return
        if not self._confirm_action("Підтвердження", f"Видалити сайт '{site.name}'?"):
            return
        links_to_remove = [
            link_id
            for link_id, link in self._project.links.items()
            if link.site_a_id == site_id or link.site_b_id == site_id
        ]
        for link_id in links_to_remove:
            self.map_view.remove_link(link_id)
        self._project.remove_site(site_id)
        for antenna in site.antennas:
            coverage_id = self._coverage_key(site_id, antenna.id)
            self.map_view.remove_coverage(coverage_id)
            self._coverage_job_for_key.pop(coverage_id, None)
        self.map_view.remove_marker(site_id)
        self.project_tree.set_project(self._project)
        self.inspector.show_site(None)
        self._dirty = True

    def _on_inspector_link_updated(self, link_id: str, data: dict) -> None:
        link = self._project.links.get(link_id)
        if link is None:
            return
        link.name = data["name"]
        link.kind = data["kind"]
        link.frequency_ghz = data["frequency_ghz"]
        link.ssid = data["ssid"]
        link.password = data["password"]
        link.link_type = data["link_type"]
        link.cable_type = data["cable_type"]
        link.notes_text = data.get("notes_text")
        site_a = self._project.sites.get(link.site_a_id)
        site_b = self._project.sites.get(link.site_b_id)
        if site_a and site_b:
            link.distance_km = self._distance_km(
                site_a.location.lat, site_a.location.lon, site_b.location.lat, site_b.location.lon
            )
            self.map_view.update_link_meta(
                link.id,
                self._link_display_label(link),
                self._link_kind_value(link.kind),
                self._link_info(link, site_a),
                link.distance_km,
            )
            self.map_view.update_link(
                link.id,
                site_a.location.lat,
                site_a.location.lon,
                site_b.location.lat,
                site_b.location.lon,
            )
        self.project_tree.set_project(self._project)
        self.inspector.show_link(link, site_a.name if site_a else "—", site_b.name if site_b else "—")
        self._dirty = True

    def _on_site_updated(self, site_id: str, data: dict) -> None:
        site = self._project.sites.get(site_id)
        if site is None:
            return
        location_changed = False
        env_changed = False
        if "name" in data and data["name"]:
            site.name = data["name"]
        if "kind" in data and data["kind"] is not None:
            kind = data["kind"]
            if isinstance(kind, str):
                try:
                    kind = SiteKind(kind)
                except ValueError:
                    kind = SiteKind.POP
            site.kind = kind
        lat = data.get("lat")
        lon = data.get("lon")
        if lat is not None and lon is not None:
            site.location = GeoPoint(lat=lat, lon=lon, altitude_m=site.location.altitude_m)
            location_changed = True
        env_value = data.get("environment")
        if env_value:
            if site.metadata.get("environment") != env_value:
                site.metadata["environment"] = env_value
                env_changed = True

        def update_antenna(target: AntennaParams, payload: dict) -> None:
            target.name = payload.get("name") or target.name
            target.antenna_type = payload.get("antenna_type")
            target.azimuth_deg = payload.get("azimuth_deg")
            target.beamwidth_deg = payload.get("beamwidth_deg")
            target.gain_dbi = payload.get("gain_dbi")
            target.height_m = payload.get("height_m")
            target.frequency_ghz = payload.get("frequency_ghz")
            target.tx_power_dbm = payload.get("tx_power_dbm")
            target.mcs = payload.get("mcs")
            target.rx_gain_dbi = payload.get("rx_gain_dbi")
            target.rx_height_m = payload.get("rx_height_m")
            target.rx_sensitivity_dbm = payload.get("rx_sensitivity_dbm")
            target.channel_width_mhz = payload.get("channel_width_mhz")
            target.misc_losses_db = payload.get("misc_losses_db")
            target.link_margin_db = payload.get("link_margin_db")
            if "applied" in payload:
                target.applied = bool(payload.get("applied"))

        antenna_payload = data.get("antenna")
        if isinstance(antenna_payload, dict):
            antenna_id = antenna_payload.get("id") or uuid4().hex[:8]
            antenna = next((a for a in site.antennas if a.id == antenna_id), None)
            if antenna is None:
                antenna = AntennaParams(id=antenna_id)
                site.antennas.append(antenna)
            update_antenna(antenna, antenna_payload)
            if data.get("apply"):
                antenna.applied = True
                self._update_antenna_coverage(site, antenna)

        antennas_payload = data.get("antennas")
        if isinstance(antennas_payload, list):
            old_ids = {a.id for a in site.antennas}
            new_antennas: list[AntennaParams] = []
            for payload in antennas_payload:
                if not isinstance(payload, dict):
                    continue
                antenna_id = payload.get("id") or uuid4().hex[:8]
                antenna = AntennaParams(id=antenna_id)
                update_antenna(antenna, payload)
                new_antennas.append(antenna)
            site.antennas = new_antennas
            new_ids = {a.id for a in site.antennas}
            for removed_id in old_ids - new_ids:
                self.map_view.remove_coverage(self._coverage_key(site.id, removed_id))
                self._coverage_job_for_key.pop(self._coverage_key(site.id, removed_id), None)
            if data.get("apply_all"):
                for antenna in site.antennas:
                    antenna.applied = True
                    self._update_antenna_coverage(site, antenna)
        kind_value = site.kind.value if hasattr(site.kind, "value") else str(site.kind)
        self.map_view.update_marker_label(site.id, site.name, self._site_kind_label(kind_value))
        self.map_view.move_marker(site.id, site.location.lat, site.location.lon)
        self.inspector.show_site(site)
        if location_changed or env_changed:
            self._update_site_coverages(site)
        for link in self._project.links.values():
            if link.site_a_id == site.id or link.site_b_id == site.id:
                site_a = self._project.sites.get(link.site_a_id)
                site_b = self._project.sites.get(link.site_b_id)
                if site_a and site_b:
                    link.distance_km = self._distance_km(
                        site_a.location.lat,
                        site_a.location.lon,
                        site_b.location.lat,
                        site_b.location.lon,
                    )
                    self.map_view.update_link_meta(
                        link.id,
                        self._link_display_label(link),
                        self._link_kind_value(link.kind),
                        self._link_info(link, site_a),
                        link.distance_km,
                    )
                    self.map_view.update_link(
                        link.id,
                        site_a.location.lat,
                        site_a.location.lon,
                        site_b.location.lat,
                        site_b.location.lon,
                    )
        self.project_tree.set_project(self._project)
        self._dirty = True

    def _on_link_analyze_requested(self, link_id: str) -> None:
        link = self._project.links.get(link_id)
        if link is None:
            return
        site_a = self._project.sites.get(link.site_a_id)
        site_b = self._project.sites.get(link.site_b_id)
        if site_a is None or site_b is None:
            return
        profile = self._link_analyzer.analyze(site_a, site_b, samples=30)
        dialog = LinkProfileDialog(profile, self)
        dialog.exec()

    @staticmethod
    def _site_kind_label(kind_value: str) -> str:
        return {
            "core": "CORE",
            "pop": "POP",
            "cpe": "CPE",
        }.get(kind_value, kind_value)

    @staticmethod
    def _site_kind_value(site: Site) -> str:
        return site.kind.value if hasattr(site.kind, "value") else str(site.kind)

    @staticmethod
    def _link_kind_value(kind: object) -> str:
        return kind.value if hasattr(kind, "value") else str(kind)

    @staticmethod
    def _link_label(kind: object) -> str:
        value = kind.value if hasattr(kind, "value") else str(kind)
        return {"ptp": "PtP", "ptmp": "PtMP", "ethernet": "Ethernet"}.get(value, value)

    @staticmethod
    def _link_display_label(link: Link) -> str:
        kind_label = MainWindow._link_label(link.kind)
        name = link.name or "Лінк"
        return f"{name} ({kind_label})"

    @staticmethod
    def _link_info(link: Link, site_a: Site | None = None) -> str:
        kind_value = link.kind.value if hasattr(link.kind, "value") else str(link.kind)
        distance_text = f"{link.distance_km:.2f} км" if link.distance_km is not None else "-"
        antenna = (
            next((a for a in site_a.antennas if a.applied), None)
            if site_a and site_a.antennas
            else None
        ) or (site_a.antennas[0] if site_a and site_a.antennas else None)
        antenna_height = antenna.height_m if antenna else None
        notes_text = f"\nНотатки: {link.notes_text}" if link.notes_text else ""
        if kind_value in ("ptp", "ptmp"):
            freq_mhz = (link.frequency_ghz * 1000.0) if link.frequency_ghz is not None else None
            return (
                f"Тип: {kind_value}\\n"
                f"Частота: {freq_mhz or '-'} МГц\\n"
                f"Висота антени: {antenna_height or '-'} м\\n"
                f"SSID: {link.ssid or '-'}\\n"
                f"Пароль: {link.password or '-'}\\n"
                f"Дистанція: {distance_text}"
                f"{notes_text}"
            )
        return (
            "Тип: Ethernet | "
            f"Лінк: {link.link_type.value if hasattr(link.link_type, 'value') else (link.link_type or '-')}"
            " | "
            f"Кабель: {link.cable_type.value if hasattr(link.cable_type, 'value') else (link.cable_type or '-')}"
            " | "
            f"Дистанція: {distance_text}"
            f"{notes_text}"
        )

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        return r * c

    @staticmethod
    def _coverage_key(site_id: str, antenna_id: str) -> str:
        return f"{site_id}:{antenna_id}"

    def _update_site_coverages(self, site: Site) -> None:
        for antenna in site.antennas:
            if antenna.applied:
                self._update_antenna_coverage(site, antenna)
            else:
                coverage_id = self._coverage_key(site.id, antenna.id)
                self.map_view.remove_coverage(coverage_id)
                self._coverage_job_for_key.pop(coverage_id, None)

    def _update_antenna_coverage(self, site: Site, antenna: AntennaParams) -> None:
        coverage_id = self._coverage_key(site.id, antenna.id)
        if antenna.beamwidth_deg is None or antenna.gain_dbi is None:
            self.map_view.remove_coverage(coverage_id)
            return
        beamwidth = antenna.beamwidth_deg
        azimuth = (antenna.azimuth_deg or 0.0) % 360.0
        if antenna.antenna_type == "omni":
            beamwidth = 360.0
        if beamwidth is None:
            self.map_view.remove_coverage(coverage_id)
            return
        beamwidth = self._clamp_beamwidth(beamwidth)
        site_snapshot = Site(
            id=site.id,
            name=site.name,
            kind=site.kind,
            location=GeoPoint(
                lat=site.location.lat,
                lon=site.location.lon,
                altitude_m=site.location.altitude_m,
            ),
            antennas=[],
        )
        antenna_snapshot = replace(antenna)
        self._coverage_job_seq += 1
        job_id = self._coverage_job_seq
        self._coverage_job_for_key[coverage_id] = job_id
        self.map_view.remove_coverage(coverage_id)
        self._set_busy("Розрахунок покриття…")
        future = self._bg_executor.submit(
            self._compute_coverage_data,
            site_snapshot,
            antenna_snapshot,
            azimuth,
            beamwidth,
            coverage_id,
            job_id,
        )
        future.add_done_callback(lambda f, key=coverage_id, jid=job_id: self._on_coverage_done(key, jid, f))

    def _cleanup_on_close(self) -> None:
        if self._dirty:
            self._autosave()
        self._bg_executor.shutdown(wait=False)
        self._elevation.clear_cache()

    def _new_project(self) -> None:
        if self._dirty and not self._confirm_action("Підтвердження", "Є незбережені зміни. Продовжити?"):
            return
        self._project = NetworkProject(id="default", name="Новий проєкт")
        self._project_path = None
        self._dirty = False
        self._coverage_job_for_key.clear()
        self.project_tree.set_project(self._project)
        self.map_view.clear_all()
        self.inspector.show_site(None)
        self._ping_checker.set_devices([])
        self._refresh_monitoring()

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Відкрити проєкт", "", "NetProj (*.netproj)")
        if not path:
            return
        self._project = load_project(path)
        self._project_path = path
        self._dirty = False
        self._coverage_job_for_key.clear()
        self.project_tree.set_project(self._project)
        self.map_view.clear_all()
        for site in self._project.sites.values():
            self.map_view.add_marker(
                site.id,
                site.name,
                self._site_kind_label(self._site_kind_value(site)),
                site.location.lat,
                site.location.lon,
            )
            self._update_site_coverages(site)
        for link in self._project.links.values():
            site_a = self._project.sites.get(link.site_a_id)
            site_b = self._project.sites.get(link.site_b_id)
            if site_a and site_b:
                self.map_view.add_link(
                    link.id,
                    self._link_display_label(link),
                    self._link_kind_value(link.kind),
                    self._link_info(link, site_a),
                    link.distance_km,
                    site_a.location.lat,
                    site_a.location.lon,
                    site_b.location.lat,
                    site_b.location.lon,
                )
        self._ping_checker.set_devices(self._all_devices())
        self._refresh_monitoring()

    def _save_project(self) -> None:
        if not self._project_path:
            self._save_project_as()
            return
        save_project(self._project_path, self._project)
        self._dirty = False

    def _save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Зберегти проєкт", "", "NetProj (*.netproj)")
        if not path:
            return
        if not path.endswith(".netproj"):
            path += ".netproj"
        self._project_path = path
        save_project(path, self._project)
        self._dirty = False

    def _autosave(self) -> None:
        if not self._project_path:
            return
        save_project(self._project_path, self._project)
        self._dirty = False

    def _on_tree_context_menu(self, pos: QPoint) -> None:
        item = self.project_tree.itemAt(pos)
        if item is None:
            return
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        rename_action = menu.addAction("Перейменувати")
        delete_action = menu.addAction("Видалити")
        chosen = menu.exec(self.project_tree.viewport().mapToGlobal(pos))
        if chosen not in (rename_action, delete_action):
            return

        if isinstance(node_id, str) and ":" in node_id:
            site_id, device_id = node_id.split(":", 1)
            site = self._project.sites.get(site_id)
            if not site:
                return
            device = site.devices.get(device_id)
            if not device:
                return
            if chosen == delete_action:
                if self._confirm_action("Підтвердження", f"Видалити пристрій '{device.name}'?"):
                    site.remove_device(device_id)
            else:
                new_name, ok = QInputDialog.getText(
                    self, "Перейменувати пристрій", "Нова назва:", text=device.name
                )
                if ok and new_name.strip():
                    device.name = new_name.strip()
        elif isinstance(node_id, str) and node_id in self._project.links:
            link = self._project.links.get(node_id)
            if not link:
                return
            if chosen == delete_action:
                self._on_map_request_delete_link(link.id)
            else:
                new_name, ok = QInputDialog.getText(self, "Перейменувати лінк", "Нова назва:", text=link.name)
                if ok and new_name.strip():
                    link.name = new_name.strip()
                    site_a = self._project.sites.get(link.site_a_id)
                    if site_a:
                        self.map_view.update_link_meta(
                            link.id,
                            self._link_display_label(link),
                            self._link_kind_value(link.kind),
                            self._link_info(link, site_a),
                            link.distance_km,
                        )
        else:
            site = self._project.sites.get(node_id)
            if not site:
                return
            if chosen == delete_action:
                self._delete_site(site.id)
            else:
                new_name, ok = QInputDialog.getText(self, "Перейменувати сайт", "Нова назва:", text=site.name)
                if ok and new_name.strip():
                    site.name = new_name.strip()
                    self.map_view.update_marker_label(
                        site.id, site.name, self._site_kind_label(self._site_kind_value(site))
                    )
                    self._update_site_coverages(site)

        self.project_tree.set_project(self._project)
        self._dirty = True

    def _rename_selected(self) -> None:
        item = self.project_tree.currentItem()
        if item is None:
            return
        pos = self.project_tree.visualItemRect(item).center()
        self._on_tree_context_menu(pos)

    def _all_devices(self) -> list:
        devices = []
        for site in self._project.sites.values():
            devices.extend(site.devices.values())
        return devices

    def _on_device_ping_status(self, device_id: str, state: str, rtt_ms: float) -> None:
        for site in self._project.sites.values():
            device = site.devices.get(device_id)
            if device is None:
                continue
            device.status.state = StatusState(state)
            device.status.last_seen = datetime.utcnow()
            device.status.rtt_ms = rtt_ms
            break
        self._refresh_monitoring()

    def _refresh_monitoring(self) -> None:
        problems = []
        total = len(self._project.sites)
        up_count = 0
        for site in self._project.sites.values():
            status = self._site_status(site)
            if status == StatusState.UP:
                up_count += 1
            else:
                problems.append(f"{site.name} — {status.value}")
            previous = self._site_status_cache.get(site.id)
            if previous and previous != status:
                self.monitoring_panel.add_event(
                    f"{datetime.utcnow().strftime('%H:%M:%S')} {site.name}: {previous.value} → {status.value}"
                )
            self._site_status_cache[site.id] = status
            self.map_view.set_marker_status(site.id, status.value)
        percent = (up_count / total * 100) if total else 0.0
        self.monitoring_panel.set_availability(percent)
        self.monitoring_panel.set_problems(problems)

    @staticmethod
    def _site_status(site: Site) -> StatusState:
        devices = list(site.devices.values())
        if not devices:
            return StatusState.UNKNOWN
        uplinks = [d for d in devices if d.is_uplink]
        if any(d.status.state == StatusState.DOWN for d in uplinks):
            return StatusState.DOWN
        if any(d.status.state == StatusState.DOWN for d in devices):
            return StatusState.DEGRADED
        if all(d.status.state == StatusState.UP for d in devices):
            return StatusState.UP
        return StatusState.UNKNOWN

    @staticmethod
    def _coverage_color(antenna_type: str | None) -> str:
        return {
            "omni": "#22c55e",
            "sector": "#0ea5e9",
            "directional": "#f97316",
        }.get(antenna_type or "", "#22c55e")

    @staticmethod
    def _apply_channel_width(antenna: AntennaParams) -> AntennaParams:
        if antenna.rx_sensitivity_dbm is None:
            return antenna
        bw_mhz = antenna.channel_width_mhz
        if bw_mhz is None or bw_mhz <= 0:
            return antenna
        ref_mhz = 20.0
        if bw_mhz <= 0:
            return antenna
        rx_sens = antenna.rx_sensitivity_dbm + (10.0 * log10(bw_mhz / ref_mhz))
        return replace(antenna, rx_sensitivity_dbm=rx_sens)

    @staticmethod
    def _environment_loss_db(env_type: str, distance_km: float, freq_ghz: float) -> float:
        presets = {
            "open": (0.0, 0.1),
            "mixed": (2.0, 0.4),
            "urban": (6.0, 0.8),
            "vegetation": (4.0, 0.9),
        }
        base_db, per_km = presets.get(env_type, presets["mixed"])
        if freq_ghz < 0.3:
            freq_factor = 0.5
        elif freq_ghz < 1.0:
            freq_factor = 0.7
        elif freq_ghz < 6.0:
            freq_factor = 1.0
        elif freq_ghz < 11.0:
            freq_factor = 1.2
        elif freq_ghz < 18.0:
            freq_factor = 1.4
        else:
            freq_factor = 1.6
        return max(0.0, (base_db + per_km * distance_km) * freq_factor)

    @staticmethod
    def _clamp_beamwidth(value: float) -> float:
        if value <= 0:
            return 1.0
        if value > 360.0:
            return 360.0
        return value

    @staticmethod
    def _get_rss_mb() -> float | None:
        try:
            import psutil  # type: ignore

            return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        except Exception:
            try:
                import resource

                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                if sys.platform == "darwin":
                    return rss / (1024 * 1024)
                return rss / 1024
            except Exception:
                return None

    def _enforce_memory_limit(self) -> None:
        rss_mb = self._get_rss_mb()
        if rss_mb is None or rss_mb < self._memory_limit_mb:
            return
        self._elevation.clear_cache()
        self.map_view.clear_web_cache()

    def _set_busy(self, message: str | None) -> None:
        if message:
            was_idle = self._busy_count == 0
            self._busy_count += 1
            self.statusBar().showMessage(message)
            if was_idle:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            return
        if self._busy_count > 0:
            self._busy_count -= 1
        if self._busy_count == 0:
            self.statusBar().clearMessage()
            QApplication.restoreOverrideCursor()

    def _finish_prefetch(self, token: int) -> None:
        if token != self._prefetch_token:
            self._set_busy(None)
            return
        self._set_busy(None)

    def _compute_coverage_data(
        self,
        site: Site,
        antenna: AntennaParams,
        azimuth: float,
        beamwidth: float,
        coverage_id: str | None = None,
        job_id: int | None = None,
    ) -> dict | None:
        site_elevation = None
        if self._elevation.available:
            site_elevation = self._elevation.get_elevation(site.location.lat, site.location.lon)
        antenna_eff = self._apply_channel_width(antenna)
        coverage = self._coverage_calc.estimate_range_km(
            antenna_eff,
            site_elevation_m=site_elevation,
            beamwidth_deg=beamwidth,
        )
        range_km = coverage.range_km
        color = self._coverage_color(antenna.antenna_type)
        antenna_name = antenna.name or "Антена"
        tooltip = (
            f"{site.name} | {antenna_name} | Азимут: {azimuth}° | Сектор: {beamwidth}° | "
            f"Gain: {antenna.gain_dbi or '-'} dBi"
        )
        horizon_limit_km = self._radio_horizon_limit_km(antenna, site_elevation_m=site_elevation)
        if horizon_limit_km is not None:
            range_km = min(range_km, horizon_limit_km)
        tile_callback = None
        if coverage_id and job_id:
            tile_callback = lambda tile: self.coverage_tile_ready.emit(coverage_id, job_id, tile)
        env_type = site.metadata.get("environment") or self._project.metadata.get("environment") or "mixed"
        raster_ok = self._coverage_raster_tiles(
            site,
            antenna_eff,
            azimuth,
            beamwidth,
            range_km,
            horizon_limit_km=horizon_limit_km,
            site_elevation=site_elevation,
            step_km=0.5,
            tile_size=64,
            env_type=env_type,
            on_tile=tile_callback,
        )
        if raster_ok:
            return {
                "mode": "raster_done",
                "tooltip": tooltip,
            }
        bands = self._coverage_gradient_bands(
            site,
            antenna_eff,
            azimuth,
            beamwidth,
            range_km,
            site_elevation,
            horizon_limit_km=horizon_limit_km,
        )
        if bands:
            return {
                "mode": "bands",
                "bands": bands,
                "tooltip": tooltip,
            }
        points = self._coverage_points_with_dem(site, antenna_eff, azimuth, beamwidth, range_km, site_elevation)
        if points:
            return {
                "mode": "points",
                "points": points,
                "color": color,
                "tooltip": tooltip,
            }
        return {
            "mode": "simple",
            "lat": site.location.lat,
            "lon": site.location.lon,
            "azimuth": azimuth,
            "beamwidth": beamwidth,
            "range_km": range_km,
            "color": color,
            "tooltip": tooltip,
        }

    def _on_coverage_done(self, coverage_id: str, job_id: int, future) -> None:
        try:
            result = future.result()
        except Exception:
            result = None
        self.coverage_result_ready.emit(coverage_id, job_id, result)

    def _apply_coverage_result(self, coverage_id: str, job_id: int, result) -> None:
        if self._coverage_job_for_key.get(coverage_id) != job_id:
            self._set_busy(None)
            return
        site_id = coverage_id.split(":", 1)[0]
        antenna_id = coverage_id.split(":", 1)[1] if ":" in coverage_id else ""
        site = self._project.sites.get(site_id)
        if site is None:
            self._set_busy(None)
            return
        antenna = next((a for a in site.antennas if a.id == antenna_id and a.applied), None)
        if antenna is None:
            self.map_view.remove_coverage(coverage_id)
            self._set_busy(None)
            return
        if result is None:
            self.map_view.remove_coverage(coverage_id)
            self._set_busy(None)
            return
        mode = result.get("mode")
        if mode == "raster_done":
            self._set_busy(None)
            return
        elif mode == "bands":
            self.map_view.update_coverage_bands(coverage_id, result["bands"], result["tooltip"])
        elif mode == "points":
            self.map_view.update_coverage_points(coverage_id, result["points"], result["color"], result["tooltip"])
        else:
            self.map_view.update_coverage(
                coverage_id,
                result["lat"],
                result["lon"],
                result["azimuth"],
                result["beamwidth"],
                result["range_km"],
                result["color"],
                result["tooltip"],
            )
        self._set_busy(None)

    def _apply_coverage_tile(self, coverage_id: str, job_id: int, tile: dict) -> None:
        if self._coverage_job_for_key.get(coverage_id) != job_id:
            return
        if not tile:
            return
        self.map_view.update_coverage_raster_tile(coverage_id, tile["data_url"], tile["bounds"])

    def _coverage_points_with_dem(
        self,
        site: Site,
        antenna: AntennaParams,
        azimuth: float,
        beamwidth: float,
        range_km: float,
        site_elevation: float | None = None,
    ) -> list | None:
        distances = self._coverage_los_distances(
            site,
            antenna,
            azimuth,
            beamwidth,
            range_km,
            site_elevation,
            allowed_diffraction_db=6.0,
            use_fresnel=True,
        )
        if not distances:
            return None
        return self._coverage_points_from_distances(site, distances, range_km)

    def _coverage_raster_tiles(
        self,
        site: Site,
        antenna: AntennaParams,
        azimuth: float,
        beamwidth: float,
        range_km: float,
        horizon_limit_km: float | None = None,
        site_elevation: float | None = None,
        step_km: float = 0.5,
        tile_size: int = 64,
        env_type: str = "mixed",
        on_tile=None,
    ) -> bool:
        if Image is None:
            return False
        if not self._elevation.available:
            return False
        freq_ghz = antenna.frequency_ghz
        tx_power = antenna.tx_power_dbm
        rx_sens = antenna.rx_sensitivity_dbm
        if freq_ghz is None or freq_ghz <= 0 or tx_power is None or rx_sens is None:
            return False
        rx_gain = antenna.rx_gain_dbi or 0.0
        tx_gain = antenna.gain_dbi or 0.0
        losses = antenna.misc_losses_db or 0.0
        margin = antenna.link_margin_db or 0.0
        actual_eirp = tx_power + tx_gain - losses
        required_base = rx_sens + margin + losses - rx_gain

        effective_range_km = range_km
        if horizon_limit_km is not None:
            effective_range_km = min(effective_range_km, horizon_limit_km)
        if effective_range_km <= 0:
            return False

        lat = site.location.lat
        lon = site.location.lon
        cos_lat = cos(radians(lat))
        if abs(cos_lat) < 1e-6:
            return None
        lat_per_km = 1.0 / 110.574
        lon_per_km = 1.0 / (111.320 * cos_lat)
        max_extent_km = effective_range_km

        size = int((max_extent_km * 2.0) / step_km) + 1
        if size <= 1:
            return False
        center = size // 2

        site_elev = site_elevation
        if site_elev is None:
            site_elev = self._elevation.get_elevation(lat, lon)
        if site_elev is None:
            return False
        base_height = site_elev + (antenna.height_m or 0.0)
        rx_height_m = antenna.rx_height_m if antenna.rx_height_m is not None else 2.0
        if rx_height_m < 0:
            rx_height_m = 0.0

        half_bw = beamwidth / 2.0
        use_bw = beamwidth < 360.0 - 1e-3
        earth_radius_m = 6371000.0 * 1.1
        wavelength_m = 0.3 / freq_ghz
        fresnel_factor = 0.6
        base_fspl = 92.45 + (20.0 * log10(freq_ghz))
        max_workers = min(4, os.cpu_count() or 4)
        cache_lock = Lock()
        elev_cache: dict[tuple[float, float], float | None] = {}
        cache_limit = 20000

        x_km_list = [(i - center) * step_km for i in range(size)]
        y_km_list = [(center - j) * step_km for j in range(size)]
        lat_list = [lat + (y_km * lat_per_km) for y_km in y_km_list]
        lon_list = [lon + (x_km * lon_per_km) for x_km in x_km_list]

        def delta_eirp_for(distance_km: float, diff_loss_db: float, env_loss_db: float) -> float:
            fspl = base_fspl + (20.0 * log10(distance_km))
            return actual_eirp - required_base - fspl - diff_loss_db - env_loss_db

        def tile_bounds(x0: int, y0: int, w: int, h: int) -> list[float]:
            x1 = x0 + w - 1
            y1 = y0 + h - 1
            left_km = (x0 - center - 0.5) * step_km
            right_km = (x1 - center + 0.5) * step_km
            top_km = (center - y0 + 0.5) * step_km
            bottom_km = (center - y1 - 0.5) * step_km
            north = lat + (top_km * lat_per_km)
            south = lat + (bottom_km * lat_per_km)
            west = lon + (left_km * lon_per_km)
            east = lon + (right_km * lon_per_km)
            return [min(south, north), min(west, east), max(south, north), max(west, east)]

        def sector_bounds_xy() -> tuple[int, int, int, int]:
            if not use_bw:
                return 0, size - 1, 0, size - 1
            def in_sector(angle: float) -> bool:
                delta = (angle - azimuth + 540.0) % 360.0 - 180.0
                return abs(delta) <= half_bw
            angles = [azimuth - half_bw, azimuth + half_bw]
            for cand in (0.0, 90.0, 180.0, 270.0):
                if in_sector(cand):
                    angles.append(cand)
            xs = [0.0]
            ys = [0.0]
            for ang in angles:
                rad = radians(ang)
                xs.append(sin(rad) * max_extent_km)
                ys.append(cos(rad) * max_extent_km)
            min_x = min(xs)
            max_x = max(xs)
            min_y = min(ys)
            max_y = max(ys)
            i_min = max(0, int(floor(min_x / step_km + center)))
            i_max = min(size - 1, int(ceil(max_x / step_km + center)))
            j_min = max(0, int(floor(center - max_y / step_km)))
            j_max = min(size - 1, int(ceil(center - min_y / step_km)))
            return i_min, i_max, j_min, j_max

        def adaptive_step(distance_km: float) -> float:
            if distance_km <= 3.0:
                step = 0.2
            elif distance_km <= 8.0:
                step = 0.3
            elif distance_km <= 15.0:
                step = 0.4
            elif distance_km <= 30.0:
                step = 0.6
            else:
                step = 0.8
            if step >= distance_km:
                step = max(0.1, distance_km / 2.0)
            return step

        def elevation_cached(lat_q: float, lon_q: float) -> float | None:
            key = (round(lat_q, 4), round(lon_q, 4))
            if key in elev_cache:
                return elev_cache[key]
            elev_val = self._elevation.get_elevation(lat_q, lon_q)
            with cache_lock:
                if len(elev_cache) >= cache_limit:
                    elev_cache.clear()
                elev_cache[key] = elev_val
            return elev_val

        any_tiles = False
        i_min, i_max, j_min, j_max = sector_bounds_xy()

        def compute_tile(tile_x: int, tile_y: int, tile_w: int, tile_h: int) -> dict | None:
            image = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
            pixels = image.load()
            tile_has = False
            local_cache: dict[tuple[float, float], float | None] = {}

            def elev_local(lat_q: float, lon_q: float) -> float | None:
                key = (round(lat_q, 4), round(lon_q, 4))
                if key in local_cache:
                    return local_cache[key]
                if key in elev_cache:
                    val = elev_cache[key]
                    local_cache[key] = val
                    return val
                val = elevation_cached(lat_q, lon_q)
                local_cache[key] = val
                return val

            for j in range(tile_h):
                global_j = tile_y + j
                if global_j < j_min or global_j > j_max:
                    continue
                y_km = y_km_list[global_j]
                lat_row = lat_list[global_j]
                for i in range(tile_w):
                    global_i = tile_x + i
                    if global_i < i_min or global_i > i_max:
                        continue
                    x_km = x_km_list[global_i]
                    dist_km = sqrt(x_km * x_km + y_km * y_km)
                    if dist_km <= 0 or dist_km > effective_range_km:
                        continue
                    bearing = (degrees(atan2(x_km, y_km)) + 360.0) % 360.0
                    if use_bw:
                        delta = (bearing - azimuth + 540.0) % 360.0 - 180.0
                        if abs(delta) > half_bw:
                            continue
                    lon_col = lon_list[global_i]
                    target_elev = elev_local(lat_row, lon_col)
                    if target_elev is None:
                        continue
                    env_loss = self._environment_loss_db(env_type, dist_km, freq_ghz)
                    delta_no_diff = delta_eirp_for(dist_km, 0.0, env_loss)
                    if delta_no_diff < -5.0:
                        continue
                    target_height = target_elev + rx_height_m
                    diff_loss = 0.0
                    blocked = False
                    step_path_km = adaptive_step(dist_km)
                    for d_km in self._frange(step_path_km, dist_km, step_path_km):
                        if d_km >= dist_km:
                            break
                        frac = d_km / dist_km
                        x_s = x_km * frac
                        y_s = y_km * frac
                        lat_s = lat + (y_s * lat_per_km)
                        lon_s = lon + (x_s * lon_per_km)
                        elev_s = elev_local(lat_s, lon_s)
                        if elev_s is None:
                            blocked = True
                            break
                        los_height = base_height + (target_height - base_height) * frac
                        clearance = 0.0
                        d2_km = dist_km - d_km
                        if dist_km > 0:
                            r1 = 17.32 * ((d_km * d2_km) / (freq_ghz * dist_km)) ** 0.5
                            clearance = fresnel_factor * r1
                        d1_m = d_km * 1000.0
                        d2_m = d2_km * 1000.0
                        bulge_m = (d1_m * d2_m) / (2.0 * earth_radius_m)
                        base_los = los_height - clearance
                        elev_eff = elev_s + bulge_m
                        excess = elev_eff - base_los
                        if excess > 20.0:
                            blocked = True
                            break
                        if excess > 0:
                            v = excess * (2.0 * (d1_m + d2_m) / (wavelength_m * d1_m * d2_m)) ** 0.5
                            loss_db = 6.9 + 20.0 * log10(((v - 0.1) ** 2 + 1) ** 0.5 + v - 0.1)
                            if loss_db > diff_loss:
                                diff_loss = loss_db
                    if blocked:
                        continue
                    delta_eirp = delta_eirp_for(dist_km, diff_loss, env_loss)
                    if delta_eirp >= 5.0:
                        pixels[i, j] = (0, 200, 83, 160)
                        tile_has = True
                    elif delta_eirp >= 0.0:
                        pixels[i, j] = (255, 208, 0, 160)
                        tile_has = True
                    elif delta_eirp >= -5.0:
                        pixels[i, j] = (255, 23, 68, 160)
                        tile_has = True
            if not tile_has:
                return None
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
            return {
                "data_url": data_url,
                "bounds": tile_bounds(tile_x, tile_y, tile_w, tile_h),
            }

        tiles = []
        for tile_y in range(0, size, tile_size):
            tile_h = min(tile_size, size - tile_y)
            if tile_y + tile_h - 1 < j_min or tile_y > j_max:
                continue
            for tile_x in range(0, size, tile_size):
                tile_w = min(tile_size, size - tile_x)
                if tile_x + tile_w - 1 < i_min or tile_x > i_max:
                    continue
                tiles.append((tile_x, tile_y, tile_w, tile_h))

        if not tiles:
            return False

        with ThreadPoolExecutor(max_workers=min(max_workers, len(tiles))) as tile_pool:
            futures = [
                tile_pool.submit(compute_tile, tile_x, tile_y, tile_w, tile_h)
                for tile_x, tile_y, tile_w, tile_h in tiles
            ]
            for future in as_completed(futures):
                result = future.result()
                if result is None:
                    continue
                any_tiles = True
                if on_tile:
                    on_tile(result)
        return any_tiles

    def _coverage_gradient_bands(
        self,
        site: Site,
        antenna: AntennaParams,
        azimuth: float,
        beamwidth: float,
        range_km: float,
        site_elevation: float | None = None,
        horizon_limit_km: float | None = None,
    ) -> list | None:
        freq_ghz = antenna.frequency_ghz
        if freq_ghz is None or freq_ghz <= 0:
            return None
        tx_power = antenna.tx_power_dbm
        rx_sens = antenna.rx_sensitivity_dbm
        if tx_power is None or rx_sens is None:
            return None
        tx_gain = antenna.gain_dbi or 0.0
        rx_gain = antenna.rx_gain_dbi or 0.0
        losses = antenna.misc_losses_db or 0.0
        margin = antenna.link_margin_db or 0.0
        actual_eirp = tx_power + tx_gain - losses
        required_base = rx_sens + margin + losses - rx_gain

        def range_for_delta(delta_db: float) -> float | None:
            fspl_max = actual_eirp - required_base - delta_db
            if fspl_max <= 0:
                return None
            term = (fspl_max - 92.45 - (20.0 * log10(freq_ghz))) / 20.0
            return 10 ** term

        green_range = range_for_delta(5.0)
        yellow_range = range_for_delta(0.0)
        red_range = range_for_delta(-5.0)
        if green_range is None or yellow_range is None or red_range is None:
            return None

        max_range = red_range
        if self._coverage_calc.max_range_km is not None:
            max_range = min(max_range, self._coverage_calc.max_range_km)
        if horizon_limit_km is not None:
            max_range = min(max_range, horizon_limit_km)
        max_range = max(max_range, self._coverage_calc.min_range_km)
        green_range = max(min(green_range, max_range), self._coverage_calc.min_range_km)
        yellow_range = max(min(yellow_range, max_range), self._coverage_calc.min_range_km)
        red_range = max(min(red_range, max_range), self._coverage_calc.min_range_km)

        distances_red = self._coverage_los_distances(
            site,
            antenna,
            azimuth,
            beamwidth,
            max_range,
            site_elevation,
            allowed_diffraction_db=12.0,
            use_fresnel=False,
        )
        if not distances_red:
            return None
        distances_yellow = self._coverage_los_distances(
            site,
            antenna,
            azimuth,
            beamwidth,
            max_range,
            site_elevation,
            allowed_diffraction_db=6.0,
            use_fresnel=False,
        )
        if not distances_yellow:
            distances_yellow = distances_red
        distances_green = self._coverage_los_distances(
            site,
            antenna,
            azimuth,
            beamwidth,
            max_range,
            site_elevation,
            allowed_diffraction_db=0.0,
            use_fresnel=True,
        )
        if not distances_green:
            distances_green = distances_yellow

        bands = []
        red_points = self._coverage_points_from_distances(site, distances_red, red_range)
        yellow_points = self._coverage_points_from_distances(site, distances_yellow, yellow_range)
        green_points = self._coverage_points_from_distances(site, distances_green, green_range)
        if red_points:
            bands.append({"color": "#ef4444", "latlngs": red_points})
        if yellow_points:
            bands.append({"color": "#f59e0b", "latlngs": yellow_points})
        if green_points:
            bands.append({"color": "#22c55e", "latlngs": green_points})
        return bands if bands else None

    @staticmethod
    def _radio_horizon_limit_km(
        antenna: AntennaParams,
        site_elevation_m: float | None = None,
        default_rx_height_m: float = 2.0,
    ) -> float | None:
        ground_m = max(site_elevation_m or 0.0, 0.0)
        tx_height = antenna.height_m or 0.0
        if tx_height < 0:
            tx_height = 0.0
        rx_height = antenna.rx_height_m if antenna.rx_height_m is not None else default_rx_height_m
        if rx_height < 0:
            rx_height = 0.0
        horizon_km = 3.57 * (sqrt(tx_height + ground_m) + sqrt(rx_height))
        return horizon_km + 10.0

    def _coverage_los_distances(
        self,
        site: Site,
        antenna: AntennaParams,
        azimuth: float,
        beamwidth: float,
        range_km: float,
        site_elevation: float | None = None,
        allowed_diffraction_db: float = 0.0,
        use_fresnel: bool = True,
        obstruction_grace_m: float = 20.0,
    ) -> list[tuple[int, float]] | None:
        if not self._elevation.available:
            return None
        elevation = site_elevation
        if elevation is None:
            elevation = self._elevation.get_elevation(site.location.lat, site.location.lon)
        if elevation is None:
            return None
        base_height = elevation + (antenna.height_m or 0)
        rx_height_m = antenna.rx_height_m
        if rx_height_m is None:
            rx_height_m = 2.0
        fresnel_factor = 0.6
        freq_ghz = antenna.frequency_ghz
        freq_valid = freq_ghz is not None and freq_ghz > 0
        wavelength_m = 0.3 / freq_ghz if freq_valid else None
        earth_radius_m = 6371000.0 * 1.1
        step_km = max(0.2, range_km / 12)
        distances: list[tuple[int, float]] = []
        start = azimuth - beamwidth / 2
        end = azimuth + beamwidth / 2
        prev_dist_km: float | None = None
        max_jump_km = max(0.5, range_km / 30)
        for angle in range(int(start), int(end) + 1, max(2, int(beamwidth / 20))):
            samples: list[tuple[float, float | None, float, float]] = []
            for dist in self._frange(step_km, range_km, step_km):
                lat, lon = self._destination_point(site.location.lat, site.location.lon, angle, dist)
                elev = self._elevation.get_elevation(lat, lon)
                samples.append((dist, elev, lat, lon))

            last_ok = None
            base_stride = max(1, len(samples) // 50)
            for idx, (dist, elev, lat, lon) in enumerate(samples):
                if dist <= 0:
                    last_ok = (lat, lon)
                    continue
                if elev is None:
                    break
                target_height = elev + rx_height_m
                los_ok = True
                stride = 1 if idx < base_stride * 2 else base_stride
                for j in range(0, idx, stride):
                    d1, elev_j, _, _ = samples[j]
                    if elev_j is None:
                        continue
                    d2 = dist - d1
                    if d2 <= 0:
                        continue
                    los_height = base_height + (target_height - base_height) * (d1 / dist)
                    clearance = 0.0
                    if use_fresnel and freq_valid:
                        r1 = 17.32 * ((d1 * d2) / (freq_ghz * dist)) ** 0.5
                        clearance = fresnel_factor * r1
                    d1_m = d1 * 1000.0
                    d2_m = d2 * 1000.0
                    bulge_m = (d1_m * d2_m) / (2.0 * earth_radius_m)
                    base_los = los_height - clearance if use_fresnel else los_height
                    elev_eff = elev_j + bulge_m
                    excess = elev_eff - base_los
                    if excess > 0:
                        if excess > obstruction_grace_m:
                            los_ok = False
                            break
                        if not freq_valid or not wavelength_m:
                            los_ok = False
                            break
                        h_m = excess
                        v = h_m * (2.0 * (d1_m + d2_m) / (wavelength_m * d1_m * d2_m)) ** 0.5
                        loss_db = 6.9 + 20.0 * log10(((v - 0.1) ** 2 + 1) ** 0.5 + v - 0.1)
                        if loss_db > allowed_diffraction_db:
                            los_ok = False
                            break
                if not los_ok:
                    break
                last_ok = (lat, lon)

            dist_km = 0.0
            if last_ok is not None:
                dist_km = self._distance_km(
                    site.location.lat,
                    site.location.lon,
                    last_ok[0],
                    last_ok[1],
                )
                if prev_dist_km is not None and dist_km > prev_dist_km + max_jump_km:
                    dist_km = prev_dist_km + max_jump_km
            prev_dist_km = dist_km
            distances.append((angle, dist_km))
        return distances

    def _coverage_points_from_distances(
        self,
        site: Site,
        distances: list[tuple[int, float]],
        range_km: float,
    ) -> list:
        points = [[site.location.lat, site.location.lon]]
        prev_dist_km: float | None = None
        max_jump_km = max(0.5, range_km / 30)
        for angle, dist_km in distances:
            dist = min(range_km, dist_km)
            if prev_dist_km is not None and dist > prev_dist_km + max_jump_km:
                dist = prev_dist_km + max_jump_km
            if dist <= 0:
                points.append([site.location.lat, site.location.lon])
            else:
                lat, lon = self._destination_point(site.location.lat, site.location.lon, angle, dist)
                points.append([lat, lon])
            prev_dist_km = dist
        points.append([site.location.lat, site.location.lon])
        return points

    @staticmethod
    def _destination_point(lat: float, lon: float, bearing: float, distance_km: float) -> tuple[float, float]:
        r = 6371.0
        brng = radians(bearing)
        d = distance_km / r
        lat1 = radians(lat)
        lon1 = radians(lon)
        lat2 = asin(sin(lat1) * cos(d) + cos(lat1) * sin(d) * cos(brng))
        lon2 = lon1 + atan2(sin(brng) * sin(d) * cos(lat1), cos(d) - sin(lat1) * sin(lat2))
        return (lat2 * 180 / 3.141592653589793, lon2 * 180 / 3.141592653589793)

    @staticmethod
    def _frange(start: float, stop: float, step: float):
        value = start
        while value <= stop:
            yield value
            value += step
