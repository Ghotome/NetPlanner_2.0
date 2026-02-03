from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QBrush, QColor, QCursor, QDesktopServices, QIntValidator, QPen, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
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
import subprocess
import sys

from app.domain import CableType, Device, DeviceLink, DeviceType, LinkType, Site, StatusState


class PortHandle(QGraphicsEllipseItem):
    def __init__(self, parent: "DeviceNodeItem", side: str) -> None:
        super().__init__(-4, -4, 8, 8, parent)
        self.side = side
        self.setBrush(QBrush(Qt.GlobalColor.darkGray))
        self.setPen(QPen(Qt.GlobalColor.black, 1))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)


class DeviceNodeItem(QGraphicsEllipseItem):
    _icon_cache: dict[str, QPixmap] = {}
    _icon_dir = Path(__file__).resolve().parent / "icons" / "site_view"

    def __init__(self, device: Device, on_port_pressed, on_device_menu) -> None:
        super().__init__(-22, -22, 44, 44)
        self.device = device
        self._hovering = False
        self._hover_token = None
        self._tooltip_pos = None
        self._on_port_pressed = on_port_pressed
        self._on_device_menu = on_device_menu
        self.setBrush(QBrush(Qt.GlobalColor.transparent))
        self.setPen(QPen(Qt.GlobalColor.transparent, 0))
        self.setFlags(
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        self._icon_item = QGraphicsPixmapItem(self)
        label = QGraphicsTextItem(device.name, self)
        label.setPos(-20, 26)
        self._ports = self._create_ports()
        self._apply_status_style()

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

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._on_device_menu(self, event.screenPos())
            return
        super().mousePressEvent(event)

    def _apply_status_style(self) -> None:
        self._update_icon()

    def _update_icon(self) -> None:
        base = {
            DeviceType.ROUTER: "router",
            DeviceType.SWITCH: "switch",
            DeviceType.POE_SWITCH: "poe_switch",
            DeviceType.AP: "ap",
            DeviceType.REPEATER: "repeater",
        }.get(self.device.device_type, "router")
        status = {
            StatusState.UP: "up",
            StatusState.DOWN: "down",
            StatusState.DEGRADED: "down",
            StatusState.UNKNOWN: "down",
        }.get(self.device.status.state, "down")

        filename = f"{base}_{status}.png"
        if base == "poe_switch" and status == "down":
            filename = "poe_swithc_down.png"
        path = self._icon_dir / filename
        if not path.exists() and status != "up":
            path = self._icon_dir / f"{base}_up.png"
        if not path.exists():
            return
        key = str(path)
        pixmap = self._icon_cache.get(key)
        if pixmap is None:
            pixmap = QPixmap(key)
            self._icon_cache[key] = pixmap
        if pixmap.isNull():
            return
        self._icon_item.setPixmap(pixmap)
        self._icon_item.setOffset(-pixmap.width() / 2, -pixmap.height() / 2)

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
    def __init__(
        self,
        a: DeviceNodeItem,
        b: DeviceNodeItem,
        side_a: str,
        side_b: str,
        link_id: str,
        on_delete,
    ) -> None:
        super().__init__()
        self._a = a
        self._b = b
        self._side_a = side_a
        self._side_b = side_b
        self._link_id = link_id
        self._on_delete = on_delete
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

    def contextMenuEvent(self, event):  # noqa: N802
        menu = QMenu()
        delete_action = menu.addAction("Видалити лінк")
        chosen = menu.exec(event.screenPos())
        if chosen == delete_action:
            self._on_delete(self._link_id)


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
        self._apply_dialog_style(self)
        self.resize(900, 600)

        self._scene = QGraphicsScene(self)
        self._view = NetworkView(self._scene, self)
        self._view.setRenderHints(self._view.renderHints())
        self._view.setBackgroundBrush(QBrush(QApplication.palette().color(QPalette.Window)))
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

    @staticmethod
    def _apply_dialog_style(widget: QDialog) -> None:
        palette = QApplication.palette()
        window_color = palette.color(QPalette.Window)
        base_color = palette.color(QPalette.Base)
        text_color = palette.color(QPalette.Text)
        button_color = palette.color(QPalette.Button)
        button_text_color = palette.color(QPalette.ButtonText)
        highlight_color = palette.color(QPalette.Highlight)
        highlight_text_color = palette.color(QPalette.HighlightedText)
        mid_color = palette.color(QPalette.Mid)
        dark_color = palette.color(QPalette.Dark)

        def is_light(color) -> bool:
            return (0.2126 * color.redF() + 0.7152 * color.greenF() + 0.0722 * color.blueF()) > 0.55

        if is_light(window_color):
            text_color = QColor("#0f1720")
            label_color = QColor("#0f1720")
            base_color = QColor("#f8fafc")
            border_color = QColor("#94a3b8")
        else:
            label_color = text_color
            border_color = mid_color

        window = window_color.name()
        base = base_color.name()
        text = text_color.name()
        button = button_color.name()
        button_text = button_text_color.name()
        highlight = highlight_color.name()
        highlight_text = highlight_text_color.name()
        border = border_color.name()
        label = label_color.name()
        button_hover = button_color.lighter(112).name()
        widget.setStyleSheet(
            """
            QDialog {{
              background: {window};
              color: {text};
            }}
            QLabel {{
              color: {label};
              font-weight: 600;
            }}
            QLineEdit, QComboBox, QTextEdit {{
              background: {base};
              color: {text};
              border: 1px solid {border};
              border-radius: 6px;
              padding: 6px;
            }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
              border: 1px solid {highlight};
            }}
            QComboBox::drop-down {{
              border-left: 1px solid {border};
            }}
            QComboBox QAbstractItemView {{
              background: {base};
              color: {text};
              selection-background-color: {highlight};
              selection-color: {highlight_text};
            }}
            QTextEdit {{
              padding: 6px;
            }}
            QPushButton {{
              background: {button};
              color: {button_text};
              border: 1px solid {border};
              padding: 6px 12px;
              border-radius: 8px;
            }}
            QPushButton:hover {{
              background: {button_hover};
            }}
            """.format(
                window=window,
                base=base,
                text=text,
                label=label,
                button=button,
                button_text=button_text,
                highlight=highlight,
                highlight_text=highlight_text,
                border=border,
                button_hover=button_hover,
            )
        )

    def _refresh_scene(self) -> None:
        self._scene.clear()
        self._node_items = {}
        for device in self._add_or_update_nodes():
            self._node_items[device.device.id] = device

        for link in self._site.links.values():
            a = self._node_items.get(link.device_a_id)
            b = self._node_items.get(link.device_b_id)
            if a and b:
                item = DeviceLinkItem(a, b, link.port_a, link.port_b, link.id, self._delete_device_link)
                kind_value = link.link_type.value if hasattr(link.link_type, "value") else str(link.link_type)
                item.set_label(self._link_label(kind_value))
                self._scene.addItem(item)

    def _add_or_update_nodes(self) -> list[DeviceNodeItem]:
        items = []
        x = 0
        for device in self._site.devices.values():
            item = DeviceNodeItem(device, self._on_port_pressed, self._on_device_menu)
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

    def _on_device_menu(self, item: DeviceNodeItem, screen_pos) -> None:
        menu = QMenu(self)
        open_web = menu.addAction("Відкрити WebFig")
        open_ssh = menu.addAction("Відкрити SSH")
        menu.addSeparator()
        status_up = menu.addAction("Статус: UP")
        status_down = menu.addAction("Статус: DOWN")
        status_deg = menu.addAction("Статус: DEGRADED")
        toggle_uplink = menu.addAction("Перемкнути uplink")
        delete_device = menu.addAction("Видалити пристрій")
        chosen = menu.exec(screen_pos)
        if chosen == open_web:
            self._open_webfig(item.device)
        elif chosen == open_ssh:
            self._open_ssh(item.device)
        elif chosen == status_up:
            item.device.status.state = StatusState.UP
            item.device.metadata["manual_status"] = True
        elif chosen == status_down:
            item.device.status.state = StatusState.DOWN
            item.device.metadata["manual_status"] = True
        elif chosen == status_deg:
            item.device.status.state = StatusState.DEGRADED
            item.device.metadata["manual_status"] = True
        elif chosen == toggle_uplink:
            item.device.is_uplink = not item.device.is_uplink
        elif chosen == delete_device:
            if self._confirm_action("Підтвердження", f"Видалити пристрій '{item.device.name}'?"):
                self._site.remove_device(item.device.id)
        self._refresh_scene()

    def _delete_device_link(self, link_id: str) -> None:
        link = self._site.links.get(link_id)
        if link is None:
            return
        if not self._confirm_action("Підтвердження", "Видалити лінк між пристроями?"):
            return
        self._site.links.pop(link_id, None)
        self._refresh_scene()

    def _open_webfig(self, device: Device) -> None:
        if not device.ip_address:
            QMessageBox.information(self, "WebFig", "У пристрою немає IP адреси.")
            return
        port = device.ports.get("web") if device.ports else None
        if port is None:
            port = (device.port or "").strip()
        host = device.ip_address
        if port:
            host = f"{host}:{port}"
        url = QUrl(f"https://{host}/")
        QDesktopServices.openUrl(url)

    def _open_ssh(self, device: Device) -> None:
        if not device.ip_address:
            QMessageBox.information(self, "SSH", "У пристрою немає IP адреси.")
            return
        ip = device.ip_address
        port = device.ports.get("ssh") if device.ports else None
        try:
            if sys.platform.startswith("win"):
                if port:
                    subprocess.Popen(["cmd", "/c", "start", "ssh", "-p", str(port), ip])
                else:
                    subprocess.Popen(["cmd", "/c", "start", "ssh", ip])
            elif sys.platform == "darwin":
                if port:
                    cmd = f"ssh -p {port} {ip}"
                else:
                    cmd = f"ssh {ip}"
                subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{cmd}"'])
            else:
                if port:
                    subprocess.Popen(["x-terminal-emulator", "-e", "ssh", "-p", str(port), ip])
                else:
                    subprocess.Popen(["x-terminal-emulator", "-e", "ssh", ip])
        except Exception:
            QMessageBox.information(self, "SSH", "Не вдалося відкрити SSH клієнт.")

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
        SiteDevicesDialog._apply_dialog_style(self)

        self._name = QLineEdit(self)
        self._type = QComboBox(self)
        device_options = [
            ("Маршрутизатор", DeviceType.ROUTER),
            ("Комутатор", DeviceType.SWITCH),
            ("PoE комутатор", DeviceType.POE_SWITCH),
            ("Точка доступу", DeviceType.AP),
            ("Ретранслятор", DeviceType.REPEATER),
        ]
        for label, dtype in device_options:
            self._type.addItem(label, dtype)
        self._ip = QLineEdit(self)
        self._port_rows = []
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
        form.addWidget(QLabel("Порти"))
        self._ports_container = QVBoxLayout()
        self._add_port_btn = QPushButton("Додати порт", self)
        self._add_port_btn.clicked.connect(self._add_port_row)
        form.addLayout(self._ports_container)
        form.addWidget(self._add_port_btn)
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

    def _add_port_row(self) -> None:
        types = self._available_port_types()
        if not types:
            QMessageBox.information(self, "Порти", "Всі типи портів уже додані.")
            return
        row = QHBoxLayout()
        type_box = QComboBox(self)
        for value, label in types:
            type_box.addItem(label, value)
        value_edit = QLineEdit(self)
        value_edit.setValidator(QIntValidator(1, 65535, self))
        remove_btn = QPushButton("✕", self)
        remove_btn.setFixedWidth(28)

        def remove_row():
            self._ports_container.removeItem(row)
            for widget in (type_box, value_edit, remove_btn):
                widget.deleteLater()
            self._port_rows[:] = [r for r in self._port_rows if r[0] is not type_box]

        remove_btn.clicked.connect(remove_row)
        row.addWidget(type_box)
        row.addWidget(value_edit)
        row.addWidget(remove_btn)
        self._ports_container.addLayout(row)
        self._port_rows.append((type_box, value_edit))

    def _available_port_types(self) -> list[tuple[str, str]]:
        used = {box.currentData() for box, _ in self._port_rows}
        options = [("web", "Web"), ("ssh", "SSH"), ("snmp", "SNMP")]
        return [(value, label) for value, label in options if value not in used]

    def accept(self) -> None:
        types = [box.currentData() for box, _ in self._port_rows]
        if len(types) != len(set(types)):
            QMessageBox.warning(self, "Порти", "Кожен тип порту може бути лише один раз.")
            return
        for _, value in self._port_rows:
            text = value.text().strip()
            if not text:
                continue
            try:
                port = int(text)
            except ValueError:
                QMessageBox.warning(self, "Порти", "Порт має бути числом.")
                return
            if not (1 <= port <= 65535):
                QMessageBox.warning(self, "Порти", "Порт має бути в межах 1–65535.")
                return
        super().accept()

    def to_device(self) -> Device:
        name = self._name.text().strip() or "Пристрій"
        dtype = self._type.currentData()
        notes = self._notes.toPlainText().strip() or None
        ports = {}
        for box, value in self._port_rows:
            text = value.text().strip()
            if not text:
                continue
            ports[box.currentData()] = int(text)
        return Device(
            id=uuid4().hex[:8],
            name=name,
            device_type=dtype,
            ip_address=self._ip.text().strip() or None,
            ports=ports,
            position=(self._pos_x, self._pos_y),
            notes_text=notes,
        )


class LinkFormDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Параметри лінка")
        self.setMinimumWidth(320)
        SiteDevicesDialog._apply_dialog_style(self)

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
