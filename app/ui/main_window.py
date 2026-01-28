from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from uuid import uuid4

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import QMainWindow, QMenu, QMessageBox, QSplitter, QWidget

from app.domain import GeoPoint, Link, LinkKind, NetworkProject, Site, SiteKind
from app.elevation import ElevationProvider
from app.ui.inspector import InspectorPanel
from app.ui.link_dialog import SiteLinkDialog
from app.ui.map_view import MapView
from app.ui.project_tree import ProjectTree
from app.ui.site_dialog import SiteDevicesDialog


class MainWindow(QMainWindow):
    def __init__(self, project: NetworkProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project = project

        self.setWindowTitle("Планування мереж")
        self.resize(1280, 720)

        self.project_tree = ProjectTree(self)
        self.project_tree.set_project(project)
        self.project_tree.itemSelectionChanged.connect(self._on_tree_selection_changed)

        self.map_view = MapView(
            on_show_context_menu=self._on_map_context_menu,
            on_request_move_node=self._on_map_request_move_node,
            on_request_site_link=self._on_map_request_site_link,
            on_request_delete_link=self._on_map_request_delete_link,
            on_select_link=self._on_map_select_link,
            on_prefetch_elevation=self._on_prefetch_elevation,
            on_select_node=self._on_map_select_node,
            parent=self,
        )

        self.inspector = InspectorPanel(self)
        self.inspector.link_updated.connect(self._on_inspector_link_updated)
        self._elevation = ElevationProvider()
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.timeout.connect(self._prefetch_elevation_for_view)
        self._pending_bounds = None
        self._pending_zoom = None

        splitter = QSplitter(self)
        splitter.addWidget(self.project_tree)
        splitter.addWidget(self.map_view)
        splitter.addWidget(self.inspector)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([220, 900, 260])

        self.setCentralWidget(splitter)
        self._init_toolbar()
        self._site_counter = 1
        self._link_mode = False

    def _init_toolbar(self) -> None:
        toolbar = self.addToolBar("Головна")
        toolbar.addAction("Новий проєкт")
        self._add_link_action = toolbar.addAction("Додати лінк")
        self._add_link_action.setCheckable(True)
        self._add_link_action.toggled.connect(self._toggle_link_mode)
        self._elevation_action = toolbar.addAction("Шар висот")
        self._elevation_action.setCheckable(True)
        self._elevation_action.toggled.connect(self._toggle_elevation_layer)

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
        self.project_tree.add_node(site.id, f"{site.name} ({site.kind.value})")
        self.map_view.add_marker(site.id, site.name, self._site_kind_label(site.kind.value), lat, lon)
        self.inspector.show_site(site)

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
                        self._link_info(link),
                        link.distance_km,
                    )
                    self.map_view.update_link(
                        link.id,
                        a.location.lat,
                        a.location.lon,
                        b.location.lat,
                        b.location.lon,
                    )
        if self.project_tree.currentItem() is not None:
            current_id = self.project_tree.currentItem().data(0, Qt.ItemDataRole.UserRole)
            if current_id == site_id:
                self.inspector.show_site(site)

    def _on_map_select_node(self, site_id: str) -> None:
        self.project_tree.select_node(site_id)
        site = self._project.sites.get(site_id)
        self.inspector.show_site(site)
        self.map_view.focus_marker(site_id)
        if site is None:
            return
        elevation = self._elevation.get_elevation(site.location.lat, site.location.lon)
        self.inspector.set_site_elevation(elevation, self._elevation.available)
        dialog = SiteDevicesDialog(site, self)
        dialog.exec()

    def _on_map_select_link(self, link_id: str) -> None:
        link = self._project.links.get(link_id)
        if link is None:
            return
        site_a = self._project.sites.get(link.site_a_id)
        site_b = self._project.sites.get(link.site_b_id)
        self.project_tree.select_link(link_id)
        self.inspector.show_link(link, site_a.name if site_a else "—", site_b.name if site_b else "—")

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
            self._link_info(link),
            link.distance_km,
            site_a.location.lat,
            site_a.location.lon,
            site_b.location.lat,
            site_b.location.lon,
        )

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
                self._link_info(link),
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
    def _link_info(link: Link) -> str:
        kind_value = link.kind.value if hasattr(link.kind, "value") else str(link.kind)
        distance_text = f"{link.distance_km:.2f} км" if link.distance_km is not None else "-"
        if kind_value in ("ptp", "ptmp"):
            return (
                f"Тип: {kind_value}\\n"
                f"Частота: {link.frequency_ghz or '-'} ГГц\\n"
                f"SSID: {link.ssid or '-'}\\n"
                f"Пароль: {link.password or '-'}\\n"
                f"Дистанція: {distance_text}"
            )
        return (
            "Тип: Ethernet\\n"
            f"Лінк: {link.link_type.value if hasattr(link.link_type, 'value') else (link.link_type or '-')}"
            "\\n"
            f"Кабель: {link.cable_type.value if hasattr(link.cable_type, 'value') else (link.cable_type or '-')}"
            "\\n"
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
