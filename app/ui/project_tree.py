from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from app.domain import NetworkProject


class ProjectTree(QTreeWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabel("Проєкт")
        self._nodes_item = QTreeWidgetItem(["Сайти"])
        self._links_item = QTreeWidgetItem(["Лінки"])
        self._node_items = {}
        self._link_items = {}
        self.addTopLevelItem(self._nodes_item)
        self.addTopLevelItem(self._links_item)
        self.expandAll()

    def set_project(self, project: NetworkProject) -> None:
        self._nodes_item.takeChildren()
        self._links_item.takeChildren()
        self._node_items.clear()
        self._link_items.clear()

        for site in project.sites.values():
            item = QTreeWidgetItem([f"{site.name} ({site.kind.value})"])
            item.setData(0, Qt.ItemDataRole.UserRole, site.id)
            self._nodes_item.addChild(item)
            self._node_items[site.id] = item

            for device in site.devices.values():
                dtype = device.device_type.value if hasattr(device.device_type, "value") else str(device.device_type)
                child = QTreeWidgetItem([f"{device.name} ({dtype})"])
                child.setData(0, Qt.ItemDataRole.UserRole, f"{site.id}:{device.id}")
                item.addChild(child)

        for link in project.links.values():
            kind_value = link.kind.value if hasattr(link.kind, "value") else str(link.kind)
            item = QTreeWidgetItem([f"{link.name} ({self._link_label(kind_value)})"])
            item.setData(0, Qt.ItemDataRole.UserRole, link.id)
            self._links_item.addChild(item)
            self._link_items[link.id] = item

        self.expandAll()

    def add_node(self, node_id: str, label: str) -> None:
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.ItemDataRole.UserRole, node_id)
        self._nodes_item.addChild(item)
        self._node_items[node_id] = item
        self.expandAll()

    def select_node(self, node_id: str) -> None:
        item = self._node_items.get(node_id)
        if item is None:
            return
        self.setCurrentItem(item)

    def select_link(self, link_id: str) -> None:
        item = self._link_items.get(link_id)
        if item is None:
            return
        self.setCurrentItem(item)

    @staticmethod
    def _link_label(kind_value: str) -> str:
        return {
            "ptp": "PtP",
            "ptmp": "PtMP",
            "ethernet": "Ethernet",
        }.get(kind_value, kind_value)
