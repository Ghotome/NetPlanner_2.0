from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QMenu, QMessageBox, QSplitter, QWidget

from app.domain import GeoPoint, NetworkProject, Site, SiteKind
from app.ui.inspector import InspectorPanel
from app.ui.map_view import MapView
from app.ui.project_tree import ProjectTree
from app.ui.site_dialog import SiteDevicesDialog


class MainWindow(QMainWindow):
    def __init__(self, project: NetworkProject, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project = project

        self.setWindowTitle("Планиування мереж")
        self.resize(1280, 720)

        self.project_tree = ProjectTree(self)
        self.project_tree.set_project(project)
        self.project_tree.itemSelectionChanged.connect(self._on_tree_selection_changed)

        self.map_view = MapView(
            on_show_context_menu=self._on_map_context_menu,
            on_request_move_node=self._on_map_request_move_node,
            on_select_node=self._on_map_select_node,
            parent=self,
        )

        self.inspector = InspectorPanel(self)

        splitter = QSplitter(self)
        splitter.addWidget(self.project_tree)
        splitter.addWidget(self.map_view)
        splitter.addWidget(self.inspector)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)

        self.setCentralWidget(splitter)
        self._init_toolbar()
        self._site_counter = 1

    def _init_toolbar(self) -> None:
        toolbar = self.addToolBar("Головна")
        toolbar.addAction("Новий проєкт")
        toolbar.addAction("Add Link")

    def _confirm_action(self, title: str, message: str) -> bool:
        return (
            QMessageBox.question(
                self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            == QMessageBox.StandardButton.Yes
        )

    def _on_map_context_menu(self, lat: float, lon: float, x: int, y: int) -> None:
        menu = QMenu(self)
        menu.setTitle("Створити")

        actions = [
            ("Створити CORE зону", SiteKind.CORE),
            ("Створити POP зону", SiteKind.POP),
            ("Створити CPE зону", SiteKind.CPE),
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
            "Підтвердження створення",
            f"Створиити {kind.value.upper()} зону '{name}' в точці {lat:.6f}, {lon:.6f}?",
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
        self.map_view.add_marker(site.id, site.name, site.kind.value, lat, lon)
        self.inspector.show_site(site)

    def _on_map_request_move_node(
        self, site_id: str, lat: float, lon: float, prev_lat: float, prev_lon: float
    ) -> None:
        site = self._project.sites.get(site_id)
        if site is None:
            return
        confirm = self._confirm_action(
            "Підтвердження переміщення",
            f"Перемістити '{site.name}' в {lat:.6f}, {lon:.6f}?",
        )
        if not confirm:
            self.map_view.move_marker(site_id, prev_lat, prev_lon)
            return
        site.location = GeoPoint(lat=lat, lon=lon)
        if self.project_tree.currentItem() is not None:
            current_id = self.project_tree.currentItem().data(0, Qt.ItemDataRole.UserRole)
            if current_id == site_id:
                self.inspector.show_site(site)

    def _on_map_select_node(self, site_id: str) -> None:
        self.project_tree.select_node(site_id)
        site = self._project.sites.get(site_id)
        self.inspector.show_site(site)
        self.map_view.focus_marker(site_id)
        if site is not None:
            dialog = SiteDevicesDialog(site, self)
            dialog.exec()

    def _on_tree_selection_changed(self) -> None:
        item = self.project_tree.currentItem()
        if item is None:
            self.inspector.show_site(None)
            return
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        site_id = node_id.split(":", 1)[0] if isinstance(node_id, str) else node_id
        site = self._project.sites.get(site_id)
        self.inspector.show_site(site)
        if site is not None:
            self.map_view.focus_marker(site.id)
