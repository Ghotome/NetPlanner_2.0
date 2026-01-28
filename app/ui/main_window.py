from __future__ import annotations

from datetime import datetime
from math import asin, atan2, cos, radians, sin, sqrt
from uuid import uuid4

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QTreeWidgetItem,
    QWidget,
)

from app.domain import GeoPoint, Link, LinkKind, NetworkProject, Site, SiteKind, StatusState
from app.elevation import ElevationProvider
from app.link_analyzer import LinkAnalyzer
from app.project_io import load_project, save_project
from app.monitoring import PingChecker
from app.ui.monitoring_panel import MonitoringPanel
from app.ui.inspector import InspectorPanel
from app.ui.link_profile_dialog import LinkProfileDialog
from app.ui.link_dialog import SiteLinkDialog
from app.ui.map_view import MapView
from app.ui.project_tree import ProjectTree
from app.ui.site_dialog import SiteDevicesDialog
from app.ui.monitoring_panel import MonitoringPanel


class MainWindow(QMainWindow):
    def __init__(self, project: NetworkProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project = project

        self.setWindowTitle("Планування мереж")
        self.resize(1280, 720)

        self.project_tree = ProjectTree(self)
        self.project_tree.set_project(project)
        self.project_tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self.project_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)

        self.map_view = MapView(
            on_show_context_menu=self._on_map_context_menu,
            on_request_move_node=self._on_map_request_move_node,
            on_request_site_link=self._on_map_request_site_link,
            on_request_delete_link=self._on_map_request_delete_link,
            on_select_link=self._on_map_select_link,
            on_prefetch_elevation=self._on_prefetch_elevation,
            on_request_rename_site=self._on_map_request_rename_site,
            on_select_node=self._on_map_select_node,
            on_open_site=self._on_map_open_site,
            parent=self,
        )

        self.inspector = InspectorPanel(self)
        self.inspector.link_updated.connect(self._on_inspector_link_updated)
        self.inspector.link_analyze_requested.connect(self._on_link_analyze_requested)
        self.inspector.site_updated.connect(self._on_site_updated)
        self.monitoring_panel = MonitoringPanel(self)
        self._elevation = ElevationProvider()
        self._link_analyzer = LinkAnalyzer(self._elevation)
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.timeout.connect(self._prefetch_elevation_for_view)
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
        self._init_toolbar()
        self._init_menu_bar()
        self._apply_styles()
        self._site_counter = 1
        self.destroyed.connect(self._cleanup_on_close)
        self._link_mode = False
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

    def _init_toolbar(self) -> None:
        toolbar = self.addToolBar("Головна")
        new_action = toolbar.addAction("Новий проєкт")
        new_action.triggered.connect(self._new_project)
        open_action = toolbar.addAction("Відкрити")
        open_action.triggered.connect(self._open_project)
        save_action = toolbar.addAction("Зберегти")
        save_action.triggered.connect(self._save_project)
        save_as_action = toolbar.addAction("Зберегти як")
        save_as_action.triggered.connect(self._save_project_as)
        self._add_link_action = toolbar.addAction("Додати лінк")
        self._add_link_action.setCheckable(True)
        self._add_link_action.toggled.connect(self._toggle_link_mode)
        self._elevation_action = toolbar.addAction("Шар висот")
        self._elevation_action.setCheckable(True)
        self._elevation_action.toggled.connect(self._toggle_elevation_layer)
        self._coverage_action = toolbar.addAction("Покриття")
        self._coverage_action.setCheckable(True)
        self._coverage_action.setChecked(True)
        self._coverage_action.toggled.connect(self._toggle_coverage_layer)

    def _confirm_action(self, title: str, message: str) -> bool:
        return (
            QMessageBox.question(
                self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            == QMessageBox.StandardButton.Yes
        )

    def _toggle_link_mode(self, enabled: bool) -> None:
        self._link_mode = enabled
        self.map_view.set_link_mode(enabled)
        if enabled:
            self.statusBar().showMessage("Перетягніть лінію між сайтами")
        else:
            self.statusBar().clearMessage()

    def _toggle_elevation_layer(self, enabled: bool) -> None:
        self.map_view.set_elevation_layer(enabled)
        if enabled:
            self._schedule_elevation_prefetch()

    def _toggle_coverage_layer(self, enabled: bool) -> None:
        self.map_view.set_coverage_visible(enabled)

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

        edit_menu = menu.addMenu("Правка")
        edit_menu.addAction("Перейменувати", self._rename_selected, "F2")

        view_menu = menu.addMenu("Вигляд")
        view_menu.addAction(self._elevation_action)
        view_menu.addAction(self._coverage_action)

        tools_menu = menu.addMenu("Інструменти")
        tools_menu.addAction(self._add_link_action)

        help_menu = menu.addMenu("Довідка")
        help_menu.addAction("Про програму", self._about)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f6f7fb; }
            QToolBar { background: rgba(255,255,255,0.85); border-bottom: 1px solid #e5e7eb; }
            QSplitter::handle { background: #e5e7eb; }
            QTreeWidget, QListWidget { background: rgba(255,255,255,0.9); border: 1px solid #e5e7eb; }
            QLineEdit, QComboBox { background: #fff; border: 1px solid #e5e7eb; padding: 4px; border-radius: 4px; }
            QPushButton { background: #f3f4f6; border: 1px solid #e5e7eb; padding: 6px 8px; border-radius: 6px; }
            QPushButton:hover { background: #e5e7eb; }
            QLabel { color: #111827; }
            """
        )

    def _about(self) -> None:
        QMessageBox.information(self, "Про програму", "Network Planner v1.0.0")

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
        if site.antenna.antenna_type is None:
            site.antenna.antenna_type = "sector"
            site.antenna.azimuth_deg = 0.0
            site.antenna.beamwidth_deg = 120.0
            site.antenna.gain_dbi = 12.0
        self._project.add_site(site)
        self.project_tree.add_node(site.id, f"{site.name} ({site.kind.value})")
        self.map_view.add_marker(site.id, site.name, self._site_kind_label(site.kind.value), lat, lon)
        self._update_site_coverage(site)
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
                        self._link_label(link.kind),
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
        self._update_site_coverage(site)
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
            self.map_view.update_marker_label(site.id, site.name, self._site_kind_label(site.kind.value))
            self._update_site_coverage(site)
            self.project_tree.set_project(self._project)
            self._dirty = True

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
            self._update_site_coverage(site)

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
        self._ping_checker.set_devices(self._all_devices())
        self._refresh_monitoring()

    def _schedule_elevation_prefetch(self) -> None:
        self._prefetch_timer.start(400)

    def _prefetch_elevation_for_view(self) -> None:
        if self._pending_bounds is None or self._pending_zoom is None:
            return
        self._elevation.prefetch_tiles(self._pending_bounds, self._pending_zoom)

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
        link = Link(
            id=uuid4().hex[:8],
            name=f"{site_a.name} ↔ {site_b.name}",
            kind=kind,
            site_a_id=site_a.id,
            site_b_id=site_b.id,
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
            dialog.link_label(),
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
        site_a = self._project.sites.get(link.site_a_id)
        site_b = self._project.sites.get(link.site_b_id)
        if site_a and site_b:
            link.distance_km = self._distance_km(
                site_a.location.lat, site_a.location.lon, site_b.location.lat, site_b.location.lon
            )
            self.map_view.update_link_meta(
                link.id,
                self._link_label(link.kind),
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
        site.antenna.antenna_type = data.get("antenna_type")
        site.antenna.azimuth_deg = data.get("azimuth_deg")
        site.antenna.beamwidth_deg = data.get("beamwidth_deg")
        site.antenna.gain_dbi = data.get("gain_dbi")
        site.antenna.height_m = data.get("height_m")
        self._update_site_coverage(site)
        for link in self._project.links.values():
            if link.site_a_id == site.id or link.site_b_id == site.id:
                site_a = self._project.sites.get(link.site_a_id)
                site_b = self._project.sites.get(link.site_b_id)
                if site_a and site_b:
                    self.map_view.update_link_meta(
                        link.id,
                        self._link_label(link.kind),
                        self._link_kind_value(link.kind),
                        self._link_info(link, site_a),
                        link.distance_km,
                    )
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
    def _link_kind_value(kind: object) -> str:
        return kind.value if hasattr(kind, "value") else str(kind)

    @staticmethod
    def _link_label(kind: object) -> str:
        value = kind.value if hasattr(kind, "value") else str(kind)
        return {"ptp": "PtP", "ptmp": "PtMP", "ethernet": "Ethernet"}.get(value, value)

    @staticmethod
    def _link_info(link: Link, site_a: Site | None = None) -> str:
        kind_value = link.kind.value if hasattr(link.kind, "value") else str(link.kind)
        distance_text = f"{link.distance_km:.2f} км" if link.distance_km is not None else "-"
        antenna_height = site_a.antenna.height_m if site_a and site_a.antenna else None
        if kind_value in ("ptp", "ptmp"):
            return (
                f"Тип: {kind_value}\\n"
                f"Частота: {link.frequency_ghz or '-'} ГГц\\n"
                f"Висота антени: {antenna_height or '-'} м\\n"
                f"SSID: {link.ssid or '-'}\\n"
                f"Пароль: {link.password or '-'}\\n"
                f"Дистанція: {distance_text}"
            )
        return (
            "Тип: Ethernet | "
            f"Лінк: {link.link_type.value if hasattr(link.link_type, 'value') else (link.link_type or '-')}"
            " | "
            f"Кабель: {link.cable_type.value if hasattr(link.cable_type, 'value') else (link.cable_type or '-')}"
            " | "
            f"Дистанція: {distance_text}"
        )

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        return r * c

    def _update_site_coverage(self, site: Site) -> None:
        antenna = site.antenna
        if antenna is None or antenna.beamwidth_deg is None or antenna.gain_dbi is None:
            self.map_view.remove_coverage(site.id)
            return
        beamwidth = antenna.beamwidth_deg
        azimuth = antenna.azimuth_deg or 0.0
        if antenna.antenna_type == "omni":
            beamwidth = 360.0
        range_km = max(0.2, (antenna.gain_dbi or 0) * 0.2)
        color = self._coverage_color(antenna.antenna_type)
        tooltip = (
            f"{site.name} | Азимут: {azimuth}° | Сектор: {beamwidth}° | "
            f"Gain: {antenna.gain_dbi or '-'} dBi"
        )
        points = self._coverage_points_with_dem(site, azimuth, beamwidth, range_km)
        if points:
            self.map_view.update_coverage_points(site.id, points, color, tooltip)
        else:
            self.map_view.update_coverage(
                site.id,
                site.location.lat,
                site.location.lon,
                azimuth,
                beamwidth,
                range_km,
                color,
                tooltip,
            )

    def _cleanup_on_close(self) -> None:
        if self._dirty:
            self._autosave()
        self._elevation.clear_cache()

    def _new_project(self) -> None:
        if self._dirty and not self._confirm_action("Підтвердження", "Є незбережені зміни. Продовжити?"):
            return
        self._project = NetworkProject(id="default", name="Новий проєкт")
        self._project_path = None
        self._dirty = False
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
        self.project_tree.set_project(self._project)
        self.map_view.clear_all()
        for site in self._project.sites.values():
            self.map_view.add_marker(
                site.id,
                site.name,
                self._site_kind_label(site.kind.value),
                site.location.lat,
                site.location.lon,
            )
            self._update_site_coverage(site)
        for link in self._project.links.values():
            site_a = self._project.sites.get(link.site_a_id)
            site_b = self._project.sites.get(link.site_b_id)
            if site_a and site_b:
                self.map_view.add_link(
                    link.id,
                    self._link_label(link.kind),
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
        chosen = menu.exec(self.project_tree.viewport().mapToGlobal(pos))
        if chosen != rename_action:
            return

        if isinstance(node_id, str) and ":" in node_id:
            site_id, device_id = node_id.split(":", 1)
            site = self._project.sites.get(site_id)
            if not site:
                return
            device = site.devices.get(device_id)
            if not device:
                return
            new_name, ok = QInputDialog.getText(self, "Перейменувати пристрій", "Нова назва:", text=device.name)
            if ok and new_name.strip():
                device.name = new_name.strip()
        elif isinstance(node_id, str) and node_id in self._project.links:
            link = self._project.links.get(node_id)
            if not link:
                return
            new_name, ok = QInputDialog.getText(self, "Перейменувати лінк", "Нова назва:", text=link.name)
            if ok and new_name.strip():
                link.name = new_name.strip()
                site_a = self._project.sites.get(link.site_a_id)
                if site_a:
                    self.map_view.update_link_meta(
                        link.id,
                        self._link_label(link.kind),
                        self._link_kind_value(link.kind),
                        self._link_info(link, site_a),
                        link.distance_km,
                    )
        else:
            site = self._project.sites.get(node_id)
            if not site:
                return
            new_name, ok = QInputDialog.getText(self, "Перейменувати сайт", "Нова назва:", text=site.name)
            if ok and new_name.strip():
                site.name = new_name.strip()
                self.map_view.update_marker_label(site.id, site.name, self._site_kind_label(site.kind.value))
                self._update_site_coverage(site)

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
            if device.metadata.get("manual_status"):
                return
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

    def _coverage_points_with_dem(
        self, site: Site, azimuth: float, beamwidth: float, range_km: float
    ) -> list | None:
        if not self._elevation.available:
            return None
        elevation = self._elevation.get_elevation(site.location.lat, site.location.lon)
        if elevation is None:
            return None
        base_height = elevation + (site.antenna.height_m or 0)
        step_km = max(0.2, range_km / 12)
        points = [[site.location.lat, site.location.lon]]
        start = azimuth - beamwidth / 2
        end = azimuth + beamwidth / 2
        for angle in range(int(start), int(end) + 1, max(1, int(beamwidth / 20))):
            last_lat = site.location.lat
            last_lon = site.location.lon
            for dist in self._frange(step_km, range_km, step_km):
                lat, lon = self._destination_point(site.location.lat, site.location.lon, angle, dist)
                elev = self._elevation.get_elevation(lat, lon)
                if elev is not None and elev > base_height:
                    break
                last_lat, last_lon = lat, lon
            points.append([last_lat, last_lon])
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
