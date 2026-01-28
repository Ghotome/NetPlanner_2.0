from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QCursor, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolTip,
    QTextEdit,
    QVBoxLayout,
)

from app.domain import CableType, Device, DeviceLink, DeviceType, LinkType, Site


class PortHandle(QGraphicsEllipseItem):
    def __init__(self, parent: "DeviceNodeItem", side: str) -> None:
        super().__init__(-4, -4, 8, 8, parent)
        self.side = side
        self.setBrush(QBrush(Qt.GlobalColor.darkGray))
        self.setPen(QPen(Qt.GlobalColor.black, 1))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)


class DeviceNodeItem(QGraphicsEllipseItem):
    def __init__(self, device: Device, on_port_pressed) -> None:
        super().__init__(-22, -22, 44, 44)
        self.device = device
        self._hovering = False
        self._hover_token = None
        self._tooltip_pos = None
        self._on_port_pressed = on_port_pressed
        self.setBrush(QBrush(Qt.GlobalColor.white))
        self.setPen(QPen(Qt.GlobalColor.black, 1))
        self.setFlags(
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        label = QGraphicsTextItem(device.name, self)
        label.setPos(-20, 26)
        self._ports = self._create_ports()

    def itemChange(self, change, value):
        if change == QGraphicsEllipseItem.GraphicsItemChange.ItemPositionHasChanged:
            self.device.position = (value.x(), value.y())
            for link in getattr(self, "_links", []):
                link.update_position()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._hovering = True
        self._hover_token = object()
        self._tooltip_pos = (
            event.screenPos() if hasattr(event, "screenPos") else QCursor.pos()
        )
        QToolTip.showText(self._tooltip_pos, self.device.name)
        token = self._hover_token

        def show_notes():
            if not self._hovering or token is not self._hover_token:
                return
            notes = self.device.notes_text or ""
            text = self.device.name if not notes else f"{self.device.name}\n{notes}"
            pos = self._tooltip_pos or QCursor.pos()
            QToolTip.showText(pos, text)

        QTimer.singleShot(1500, show_notes)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovering = False
        self._hover_token = None
        QToolTip.hideText()
        super().hoverLeaveEvent(event)

    def _create_ports(self) -> dict[str, PortHandle]:
        ports = {
            "north": PortHandle(self, "north"),
            "east": PortHandle(self, "east"),
            "south": PortHandle(self, "south"),
            "west": PortHandle(self, "west"),
        }
        self._position_ports(ports)
        for port in ports.values():
            port.mousePressEvent = self._make_port_click_handler(port)
        return ports

    def _position_ports(self, ports: dict[str, PortHandle]) -> None:
        ports["north"].setPos(0, -22)
        ports["south"].setPos(0, 22)
        ports["west"].setPos(-22, 0)
        ports["east"].setPos(22, 0)

    def _make_port_click_handler(self, port: PortHandle):
        def handler(event):
            self._on_port_pressed(self, port.side)
            return QGraphicsEllipseItem.mousePressEvent(port, event)

        return handler

    def port_scene_pos(self, side: str) -> QPointF:
        port = self._ports.get(side)
        if port is None:
            return self.scenePos()
        return port.scenePos()


class DeviceLinkItem(QGraphicsLineItem):
    def __init__(self, a: DeviceNodeItem, b: DeviceNodeItem, side_a: str, side_b: str) -> None:
        super().__init__()
        self._a = a
        self._b = b
        self._side_a = side_a
        self._side_b = side_b
        self.setPen(QPen(Qt.GlobalColor.darkGray, 2))
        self._label = QGraphicsTextItem(self)
        self.update_position()

        for node in (a, b):
            if not hasattr(node, "_links"):
                node._links = []
            node._links.append(self)

    def update_position(self) -> None:
        a_pos = self._a.port_scene_pos(self._side_a)
        b_pos = self._b.port_scene_pos(self._side_b)
        self.setLine(a_pos.x(), a_pos.y(), b_pos.x(), b_pos.y())
        mid_x = (a_pos.x() + b_pos.x()) / 2
        mid_y = (a_pos.y() + b_pos.y()) / 2
        self._label.setPos(mid_x + 6, mid_y + 6)

    def set_label(self, text: str) -> None:
        self._label.setPlainText(text)


class NetworkView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent=None) -> None:
        super().__init__(scene, parent)
        self._on_drag_move = None
        self._on_drag_end = None

    def set_drag_handlers(self, on_drag_move, on_drag_end) -> None:
        self._on_drag_move = on_drag_move
        self._on_drag_end = on_drag_end

    def mouseMoveEvent(self, event):
        if self._on_drag_move is not None:
            self._on_drag_move(self.mapToScene(event.pos()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._on_drag_end is not None:
            self._on_drag_end(self.mapToScene(event.pos()))
        super().mouseReleaseEvent(event)


class SiteDevicesDialog(QDialog):
    def __init__(self, site: Site, parent=None) -> None:
        super().__init__(parent)
        self._site = site
        self.setWindowTitle(f"Пристрої сайту: {site.name}")
        self.setStyleSheet("background:#e5e7eb;")
        self.resize(900, 600)

        self._scene = QGraphicsScene(self)
        self._view = NetworkView(self._scene, self)
        self._view.setRenderHints(self._view.renderHints())
        self._view.setBackgroundBrush(QBrush(Qt.GlobalColor.lightGray))
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._open_context_menu)
        self._view.set_drag_handlers(self._on_drag_move, self._on_drag_end)

        self._drag_start: tuple[DeviceNodeItem, str] | None = None
        self._drag_line: QGraphicsLineItem | None = None

        top = QVBoxLayout()
        top.addWidget(QLabel("Мережа сайту"))
        top.addWidget(self._view)

        actions = QHBoxLayout()
        top.addLayout(actions)

        buttons = QHBoxLayout()
        close_btn = QPushButton("Закрити", self)
        close_btn.clicked.connect(self.accept)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)
        top.addLayout(buttons)

        self.setLayout(top)
        self._refresh_scene()

    def _refresh_scene(self) -> None:
        self._scene.clear()
        self._node_items = {}
        for device in self._add_or_update_nodes():
            self._node_items[device.device.id] = device

        for link in self._site.links.values():
            a = self._node_items.get(link.device_a_id)
            b = self._node_items.get(link.device_b_id)
            if a and b:
                item = DeviceLinkItem(a, b, link.port_a, link.port_b)
                kind_value = link.link_type.value if hasattr(link.link_type, "value") else str(link.link_type)
                item.set_label(self._link_label(kind_value))
                self._scene.addItem(item)

    def _add_or_update_nodes(self) -> list[DeviceNodeItem]:
        items = []
        x = 0
        for device in self._site.devices.values():
            item = DeviceNodeItem(device, self._on_port_pressed)
            pos = device.position or (x, 0)
            item.setPos(QPointF(pos[0], pos[1]))
            item.setToolTip(device.name)
            self._scene.addItem(item)
            items.append(item)
            x += 80
        return items

    def _open_context_menu(self, pos) -> None:
        menu = QMenu(self)
        action_map = {}
        action_map = {menu.addAction("Додати пристрій"): "add"}
        chosen = menu.exec(self._view.mapToGlobal(pos))
        if chosen is None:
            return
        if action_map.get(chosen) != "add":
            return
        scene_pos = self._view.mapToScene(pos)
        dialog = DeviceFormDialog(self, scene_pos.x(), scene_pos.y())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        device = dialog.to_device()
        self._site.add_device(device)
        self._refresh_scene()

    def _confirm_action(self, title: str, message: str) -> bool:
        return (
            QMessageBox.question(
                self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            == QMessageBox.StandardButton.Yes
        )

    @staticmethod
    def _link_label(kind_value: str) -> str:
        return {
            "fast_eth": "Fast Ethernet",
            "gig_eth": "Gigabit Ethernet",
            "optical": "Оптика",
        }.get(kind_value, kind_value)

    def _on_port_pressed(self, item: DeviceNodeItem, side: str) -> None:
        self._drag_start = (item, side)
        start_pos = item.port_scene_pos(side)
        self._drag_line = QGraphicsLineItem(start_pos.x(), start_pos.y(), start_pos.x(), start_pos.y())
        self._drag_line.setPen(QPen(Qt.GlobalColor.darkGray, 2, Qt.PenStyle.DashLine))
        self._scene.addItem(self._drag_line)

    def _on_drag_move(self, scene_pos: QPointF) -> None:
        if self._drag_line is None:
            return
        line = self._drag_line.line()
        self._drag_line.setLine(line.x1(), line.y1(), scene_pos.x(), scene_pos.y())

    def _on_drag_end(self, scene_pos: QPointF) -> None:
        if self._drag_line is None or self._drag_start is None:
            return
        if self._drag_line is not None:
            self._scene.removeItem(self._drag_line)
        self._drag_line = None

        item = self._scene.itemAt(scene_pos, self._view.transform())
        while item is not None and not isinstance(item, PortHandle):
            item = item.parentItem()
        if item is None:
            self._drag_start = None
            return

        a, a_side = self._drag_start
        b = item.parentItem()
        if not isinstance(b, DeviceNodeItem):
            self._drag_start = None
            return
        b_side = item.side

        dialog = LinkFormDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._drag_start = None
            return
        link = DeviceLink(
            id=uuid4().hex[:8],
            device_a_id=a.device.id,
            device_b_id=b.device.id,
            port_a=a_side,
            port_b=b_side,
            link_type=dialog.link_type(),
            cable_type=dialog.cable_type(),
        )
        self._site.links[link.id] = link
        self._drag_start = None
        self._refresh_scene()


class DeviceFormDialog(QDialog):
    def __init__(self, parent=None, pos_x: float = 0.0, pos_y: float = 0.0) -> None:
        super().__init__(parent)
        self.setWindowTitle("Опис пристрою")
        self.setMinimumWidth(420)

        self._name = QLineEdit(self)
        self._type = QComboBox(self)
        device_options = [
            ("Маршрутизатор", DeviceType.ROUTER),
            ("Комутатор", DeviceType.SWITCH),
            ("PoE комутатор", DeviceType.POE_SWITCH),
            ("Точка доступу", DeviceType.AP),
            ("Ретранслятор", DeviceType.REPEATER),
            ("Антена", DeviceType.ANTENNA),
        ]
        for label, dtype in device_options:
            self._type.addItem(label, dtype)
        self._ip = QLineEdit(self)
        self._port = QLineEdit(self)
        self._notes = QTextEdit(self)

        self._pos_label = QLabel(f"{pos_x:.1f}, {pos_y:.1f}", self)
        self._pos_x = pos_x
        self._pos_y = pos_y

        form = QVBoxLayout()
        form.addWidget(QLabel("Назва"))
        form.addWidget(self._name)
        form.addWidget(QLabel("Тип"))
        form.addWidget(self._type)
        form.addWidget(QLabel("IP"))
        form.addWidget(self._ip)
        form.addWidget(QLabel("Порт"))
        form.addWidget(self._port)
        form.addWidget(QLabel("Позиція (x, y)"))
        form.addWidget(self._pos_label)
        form.addWidget(QLabel("Нотатки"))
        form.addWidget(self._notes)

        actions = QHBoxLayout()
        save_btn = QPushButton("Зберегти", self)
        cancel_btn = QPushButton("Скасувати", self)
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        actions.addStretch(1)
        actions.addWidget(save_btn)
        actions.addWidget(cancel_btn)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(actions)
        self.setLayout(layout)

    def to_device(self) -> Device:
        name = self._name.text().strip() or "Пристрій"
        dtype = self._type.currentData()
        notes = self._notes.toPlainText().strip() or None
        return Device(
            id=uuid4().hex[:8],
            name=name,
            device_type=dtype,
            ip_address=self._ip.text().strip() or None,
            port=self._port.text().strip() or None,
            position=(self._pos_x, self._pos_y),
            notes_text=notes,
        )


class LinkFormDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Параметри лінка")
        self.setMinimumWidth(320)

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

        form = QVBoxLayout()
        form.addWidget(QLabel("Тип лінка"))
        form.addWidget(self._link_type)
        form.addWidget(QLabel("Тип кабелю"))
        form.addWidget(self._cable_type)

        actions = QHBoxLayout()
        save_btn = QPushButton("Зберегти", self)
        cancel_btn = QPushButton("Скасувати", self)
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        actions.addStretch(1)
        actions.addWidget(save_btn)
        actions.addWidget(cancel_btn)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(actions)
        self.setLayout(layout)

    def link_type(self) -> LinkType:
        return self._link_type.currentData()

    def cable_type(self) -> CableType:
        return self._cable_type.currentData()
