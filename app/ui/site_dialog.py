from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QDesktopServices,
    QIntValidator,
    QKeySequence,
    QPen,
    QPalette,
    QPixmap,
    QRegularExpressionValidator,
    QShortcut,
)
from PySide6.QtCore import QRegularExpression
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
    QInputDialog,
    QPushButton,
    QToolTip,
    QTextEdit,
    QVBoxLayout,
    QStyle,
)
import subprocess
import ipaddress
import sys

from app.domain import CableType, Device, DeviceLink, DeviceType, LinkType, Site, StatusState


class DeviceNodeItem(QGraphicsEllipseItem):
    _icon_cache: dict[str, QPixmap] = {}
    _icon_dir = Path(__file__).resolve().parent / "icons" / "site_view"

    def __init__(self, device: Device, on_device_menu, on_device_left_click=None, on_device_double_click=None) -> None:
        super().__init__(-22, -22, 44, 44)
        self.device = device
        self._hovering = False
        self._hover_token = None
        self._tooltip_pos = None
        self._on_device_menu = on_device_menu
        self._on_device_left_click = on_device_left_click
        self._on_device_double_click = on_device_double_click
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
        self._icon_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._icon_item.setAcceptHoverEvents(False)
        label = QGraphicsTextItem(device.name, self)
        label.setPos(-20, 26)
        label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        label.setAcceptHoverEvents(False)
        self._label_item = label
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
        if event.button() == Qt.MouseButton.LeftButton and self._on_device_left_click is not None:
            if self._on_device_left_click(self):
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._on_device_double_click is not None:
            if self._on_device_double_click(self):
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

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

    def set_link_source_highlight(self, enabled: bool) -> None:
        if enabled:
            self.setPen(QPen(QColor(34, 197, 94), 2))
        else:
            self.setPen(QPen(Qt.GlobalColor.transparent, 0))

    def port_scene_pos(self, side: str) -> QPointF:
        offsets = {
            "north": QPointF(0.0, -22.0),
            "south": QPointF(0.0, 22.0),
            "west": QPointF(-22.0, 0.0),
            "east": QPointF(22.0, 0.0),
        }
        offset = offsets.get(side, QPointF(0.0, 0.0))
        return self.scenePos() + offset


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
        sp = getattr(QStyle.StandardPixmap, "SP_TrashIcon", None)
        if sp is not None:
            delete_action.setIcon(QApplication.style().standardIcon(sp))
        chosen = menu.exec(event.screenPos())
        if chosen == delete_action:
            self._on_delete(self._link_id)


class NetworkView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent=None) -> None:
        super().__init__(scene, parent)


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

        self._pending_link_device_id: str | None = None
        self._last_deleted_device: tuple[Device, list[DeviceLink]] | None = None

        top = QVBoxLayout()
        top.addWidget(QLabel("Мережа сайту"))
        self._default_hint = "ПКМ по пристрою для дій. F2 перейменувати, Ctrl+Z відмінити видалення."
        self._hint_label = QLabel(self._default_hint)
        self._hint_label.setWordWrap(True)
        self._hint_label.setStyleSheet("font-weight: 500;")
        top.addWidget(self._hint_label)
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
        self._toast_label = QLabel("", self)
        self._toast_label.setStyleSheet(
            "QLabel { background: rgba(15, 23, 32, 220); color: white; "
            "border-radius: 8px; padding: 8px 12px; font-weight: 600; }"
        )
        self._toast_label.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast_label.hide)
        self._rename_shortcut = QShortcut(QKeySequence("F2"), self)
        self._rename_shortcut.activated.connect(self._rename_selected_device)
        self._undo_shortcut = QShortcut(QKeySequence.Undo, self)
        self._undo_shortcut.activated.connect(self._undo_last_device_delete)
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
        if self._pending_link_device_id and self._pending_link_device_id not in self._node_items:
            self._pending_link_device_id = None

        for link in self._site.links.values():
            a = self._node_items.get(link.device_a_id)
            b = self._node_items.get(link.device_b_id)
            if a and b:
                item = DeviceLinkItem(a, b, link.port_a, link.port_b, link.id, self._delete_device_link)
                kind_value = link.link_type.value if hasattr(link.link_type, "value") else str(link.link_type)
                item.set_label(self._link_label(kind_value))
                self._scene.addItem(item)
        self._sync_pending_link_ui()

    def _add_or_update_nodes(self) -> list[DeviceNodeItem]:
        items = []
        x = 0
        for device in self._site.devices.values():
            item = DeviceNodeItem(
                device,
                self._on_device_menu,
                self._on_device_left_click,
                self._on_device_double_click,
            )
            pos = device.position or (x, 0)
            item.setPos(QPointF(pos[0], pos[1]))
            item.setToolTip(device.name)
            self._scene.addItem(item)
            items.append(item)
            x += 80
        return items

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and self._pending_link_device_id:
            self._pending_link_device_id = None
            self._sync_pending_link_ui()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self._toast_label.isVisible():
            self._position_toast()

    def _on_device_left_click(self, item: DeviceNodeItem) -> bool:
        if self._pending_link_device_id is None:
            return False
        if self._pending_link_device_id == item.device.id:
            self._show_toast("Оберіть інший пристрій для створення лінка.")
            return True
        source_item = self._node_items.get(self._pending_link_device_id)
        self._pending_link_device_id = None
        self._sync_pending_link_ui()
        if source_item is None:
            return True
        self._create_device_link(source_item, item)
        return True

    def _on_device_double_click(self, item: DeviceNodeItem) -> bool:
        if self._edit_device(item):
            self._refresh_scene()
        return True

    def _sync_pending_link_ui(self) -> None:
        source_item = self._node_items.get(self._pending_link_device_id) if self._pending_link_device_id else None
        for node in self._node_items.values():
            node.set_link_source_highlight(source_item is not None and node.device.id == source_item.device.id)
        if source_item is None:
            self._hint_label.setText(self._default_hint)
        else:
            self._hint_label.setText(
                f"Створення лінка: джерело '{source_item.device.name}'. Натисніть ЛКМ по цільовому пристрою або Esc."
            )

    @staticmethod
    def _sp(name: str):
        return getattr(QStyle.StandardPixmap, name, None)

    def _set_action_icon(self, action, sp_name: str) -> None:
        if action is None:
            return
        sp = self._sp(sp_name)
        if sp is not None:
            action.setIcon(self.style().standardIcon(sp))

    def _position_toast(self) -> None:
        self._toast_label.adjustSize()
        x = max(12, (self.width() - self._toast_label.width()) // 2)
        y = max(12, self.height() - self._toast_label.height() - 16)
        self._toast_label.move(x, y)

    def _show_toast(self, text: str, duration_ms: int = 2200) -> None:
        self._toast_label.setText(text)
        self._position_toast()
        self._toast_label.show()
        self._toast_label.raise_()
        self._toast_timer.start(duration_ms)

    @staticmethod
    def _normalized_ip(device: Device) -> str | None:
        ip_value = (device.ip_address or "").strip()
        if not ip_value:
            return None
        try:
            ipaddress.ip_address(ip_value)
        except ValueError:
            return None
        return ip_value

    @staticmethod
    def _port_from_value(value: object) -> int | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            port = int(text)
        except (TypeError, ValueError):
            return None
        if not (1 <= port <= 65535):
            return None
        return port

    def _device_web_host(self, device: Device) -> str | None:
        ip_value = self._normalized_ip(device)
        if ip_value is None:
            return None
        port = self._port_from_value((device.ports or {}).get("web"))
        if port is None:
            port = self._port_from_value(device.port)
        return f"{ip_value}:{port}" if port is not None else ip_value

    def _device_ssh_command(self, device: Device) -> str | None:
        ip_value = self._normalized_ip(device)
        if ip_value is None:
            return None
        port = self._port_from_value((device.ports or {}).get("ssh"))
        return f"ssh -p {port} {ip_value}" if port is not None else f"ssh {ip_value}"

    @staticmethod
    def _device_summary(device: Device) -> str:
        dtype = device.device_type.value if hasattr(device.device_type, "value") else str(device.device_type)
        status = device.status.state.value if hasattr(device.status.state, "value") else str(device.status.state)
        ip_text = device.ip_address or "no-ip"
        return f"{device.name} • {dtype} • {status} • {ip_text}"

    def _open_context_menu(self, pos) -> None:
        menu = QMenu(self)
        action_map = {menu.addAction("Додати пристрій"): "add"}
        create_link_action = menu.addAction("Створити лінк між пристроями")
        undo_action = menu.addAction("Скасувати видалення (Ctrl+Z)")
        has_enough_devices = len(self._site.devices) >= 2
        create_link_action.setEnabled(has_enough_devices)
        link_reason = "Потрібно щонайменше два пристрої." if not has_enough_devices else ""
        create_link_action.setToolTip(link_reason)
        create_link_action.setStatusTip(link_reason)
        undo_action.setEnabled(self._last_deleted_device is not None)
        self._set_action_icon(next(iter(action_map.keys())), "SP_FileDialogNewFolder")
        self._set_action_icon(create_link_action, "SP_ArrowForward")
        self._set_action_icon(undo_action, "SP_ArrowBack")
        chosen = menu.exec(self._view.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == create_link_action:
            self._create_device_link_from_context_menu()
            return
        if chosen == undo_action:
            self._undo_last_device_delete()
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

    def _pick_device_for_link(self, title: str, prompt: str, exclude_id: str | None = None) -> str | None:
        options: list[str] = []
        option_to_id: dict[str, str] = {}
        for device in self._site.devices.values():
            if exclude_id is not None and device.id == exclude_id:
                continue
            dtype = device.device_type.value if hasattr(device.device_type, "value") else str(device.device_type)
            option = f"{device.name} ({dtype}, {device.id})"
            options.append(option)
            option_to_id[option] = device.id
        if not options:
            return None
        selected, ok = QInputDialog.getItem(self, title, prompt, options, 0, False)
        if not ok or not selected:
            return None
        return option_to_id.get(selected)

    def _create_device_link_from_context_menu(self) -> None:
        if len(self._site.devices) < 2:
            QMessageBox.information(self, "Лінк", "Потрібно щонайменше два пристрої.")
            return

        first_device_id = self._pick_device_for_link("Створити лінк", "Оберіть перший пристрій:")
        if first_device_id is None:
            return
        second_device_id = self._pick_device_for_link(
            "Створити лінк",
            "Оберіть другий пристрій:",
            exclude_id=first_device_id,
        )
        if second_device_id is None:
            return

        first_item = self._node_items.get(first_device_id)
        second_item = self._node_items.get(second_device_id)
        if first_item is None or second_item is None:
            self._refresh_scene()
            first_item = self._node_items.get(first_device_id)
            second_item = self._node_items.get(second_device_id)
            if first_item is None or second_item is None:
                QMessageBox.warning(self, "Лінк", "Не вдалося знайти вибрані пристрої.")
                return

        self._pending_link_device_id = None
        self._sync_pending_link_ui()
        self._create_device_link(first_item, second_item)

    def _on_device_menu(self, item: DeviceNodeItem, screen_pos) -> None:
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        header = menu.addAction(self._device_summary(item.device))
        header.setEnabled(False)
        menu.addSeparator()
        start_link = menu.addAction("Створити лінк")
        cancel_link = menu.addAction("Скасувати створення лінка") if self._pending_link_device_id else None
        menu.addSeparator()
        open_web = menu.addAction("Відкрити WebFig")
        open_ssh = menu.addAction("Відкрити SSH")
        ping_device = menu.addAction("Ping пристрою")
        copy_ip = menu.addAction("Копіювати IP")
        copy_ssh = menu.addAction("Копіювати SSH команду")
        menu.addSeparator()
        edit_device = menu.addAction("Редагувати")
        rename_device = menu.addAction("Перейменувати (F2)")
        delete_device = menu.addAction("Видалити пристрій")
        undo_delete = menu.addAction("Скасувати видалення (Ctrl+Z)")
        self._set_action_icon(start_link, "SP_ArrowForward")
        self._set_action_icon(cancel_link, "SP_DialogCancelButton")
        self._set_action_icon(open_web, "SP_DriveNetIcon")
        self._set_action_icon(open_ssh, "SP_ComputerIcon")
        self._set_action_icon(ping_device, "SP_BrowserReload")
        self._set_action_icon(copy_ip, "SP_FileIcon")
        self._set_action_icon(copy_ssh, "SP_FileDialogContentsView")
        self._set_action_icon(edit_device, "SP_FileDialogDetailedView")
        self._set_action_icon(rename_device, "SP_LineEditClearButton")
        self._set_action_icon(delete_device, "SP_TrashIcon")
        self._set_action_icon(undo_delete, "SP_ArrowBack")

        web_host = self._device_web_host(item.device)
        ssh_cmd = self._device_ssh_command(item.device)
        has_ip = self._normalized_ip(item.device) is not None
        has_link_source = self._pending_link_device_id is not None
        can_undo = self._last_deleted_device is not None

        def apply_enabled(action, enabled: bool, reason: str = "") -> None:
            if action is None:
                return
            action.setEnabled(enabled)
            tip = reason if (not enabled and reason) else ""
            action.setToolTip(tip)
            action.setStatusTip(tip)

        apply_enabled(open_web, web_host is not None, "Потрібна коректна IP адреса.")
        apply_enabled(open_ssh, ssh_cmd is not None, "Потрібна коректна IP адреса.")
        apply_enabled(ping_device, has_ip, "Потрібна коректна IP адреса.")
        apply_enabled(copy_ip, has_ip, "Потрібна коректна IP адреса.")
        apply_enabled(copy_ssh, ssh_cmd is not None, "Потрібна коректна IP адреса.")
        apply_enabled(cancel_link, has_link_source, "")
        apply_enabled(undo_delete, can_undo, "Немає останньої операції видалення.")

        chosen = menu.exec(screen_pos)
        changed = False

        if chosen == start_link:
            self._pending_link_device_id = item.device.id
            self._sync_pending_link_ui()
            return
        if chosen == cancel_link:
            self._pending_link_device_id = None
            self._sync_pending_link_ui()
            return
        if chosen == copy_ip and has_ip:
            QApplication.clipboard().setText((item.device.ip_address or "").strip())
            self._show_toast("IP скопійовано.")
            return
        if chosen == copy_ssh and ssh_cmd:
            QApplication.clipboard().setText(ssh_cmd)
            self._show_toast("SSH команду скопійовано.")
            return
        if chosen == ping_device and has_ip:
            self._ping_device(item.device)
            return
        if chosen == undo_delete:
            self._undo_last_device_delete()
            return

        if chosen == open_web:
            self._open_webfig(item.device)
        elif chosen == open_ssh:
            self._open_ssh(item.device)
        elif chosen == edit_device:
            changed = self._edit_device(item)
        elif chosen == rename_device:
            changed = self._rename_device(item)
        elif chosen == delete_device:
            changed = self._delete_device_with_undo(item.device.id)
            if changed:
                self._show_toast("Пристрій видалено. Ctrl+Z для відновлення.")
        if changed:
            self._refresh_scene()

    def _delete_device_link(self, link_id: str) -> None:
        link = self._site.links.get(link_id)
        if link is None:
            return
        if not self._confirm_action("Підтвердження", "Видалити лінк між пристроями?"):
            return
        self._site.links.pop(link_id, None)
        self._refresh_scene()

    def _edit_device(self, item: DeviceNodeItem) -> bool:
        pos = item.scenePos()
        dialog = DeviceFormDialog(self, pos.x(), pos.y(), device=item.device)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        dialog.apply_to_device(item.device)
        return True

    def _rename_device(self, item: DeviceNodeItem) -> bool:
        new_name, ok = QInputDialog.getText(self, "Перейменувати пристрій", "Нова назва:", text=item.device.name)
        if not ok or not new_name.strip():
            return False
        item.device.name = new_name.strip()
        return True

    def _rename_selected_device(self) -> None:
        selected = self._scene.selectedItems()
        item = next((it for it in selected if isinstance(it, DeviceNodeItem)), None)
        if item is None:
            return
        if self._rename_device(item):
            self._refresh_scene()

    def _delete_device_with_undo(self, device_id: str) -> bool:
        device = self._site.devices.get(device_id)
        if device is None:
            return False
        related_links = [
            link
            for link in self._site.links.values()
            if link.device_a_id == device_id or link.device_b_id == device_id
        ]
        self._last_deleted_device = (device, related_links)
        if self._pending_link_device_id == device_id:
            self._pending_link_device_id = None
        self._site.remove_device(device_id)
        self._sync_pending_link_ui()
        return True

    def _undo_last_device_delete(self) -> None:
        if self._last_deleted_device is None:
            return
        device, related_links = self._last_deleted_device
        self._last_deleted_device = None
        self._site.devices[device.id] = device
        for link in related_links:
            if link.device_a_id in self._site.devices and link.device_b_id in self._site.devices:
                self._site.links[link.id] = link
        self._refresh_scene()
        self._show_toast(f"Пристрій '{device.name}' відновлено.")

    def _open_webfig(self, device: Device) -> None:
        host = self._device_web_host(device)
        if host is None:
            QMessageBox.information(self, "WebFig", "У пристрою немає IP адреси.")
            return
        url = QUrl(f"https://{host}/")
        QDesktopServices.openUrl(url)

    def _open_ssh(self, device: Device) -> None:
        ssh_cmd = self._device_ssh_command(device)
        if ssh_cmd is None:
            QMessageBox.information(self, "SSH", "У пристрою немає IP адреси.")
            return
        cmd_parts = ssh_cmd.split()
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["cmd", "/c", "start", *cmd_parts])
            elif sys.platform == "darwin":
                subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{ssh_cmd}"'])
            else:
                subprocess.Popen(["x-terminal-emulator", "-e", *cmd_parts])
        except Exception:
            QMessageBox.information(self, "SSH", "Не вдалося відкрити SSH клієнт.")

    def _ping_device(self, device: Device) -> None:
        ip_value = self._normalized_ip(device)
        if ip_value is None:
            QMessageBox.information(self, "Ping", "У пристрою немає коректної IP адреси.")
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["cmd", "/c", "start", "ping", "-n", "4", ip_value])
            elif sys.platform == "darwin":
                subprocess.Popen(
                    ["osascript", "-e", f'tell application "Terminal" to do script "ping -c 4 {ip_value}"']
                )
            else:
                subprocess.Popen(["x-terminal-emulator", "-e", "ping", "-c", "4", ip_value])
        except Exception:
            QMessageBox.information(self, "Ping", "Не вдалося запустити ping.")

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

    @staticmethod
    def _opposite_side(side: str) -> str:
        return {
            "north": "south",
            "south": "north",
            "east": "west",
            "west": "east",
        }.get(side, "west")

    def _auto_link_sides(self, a: DeviceNodeItem, b: DeviceNodeItem) -> tuple[str, str]:
        dx = b.scenePos().x() - a.scenePos().x()
        dy = b.scenePos().y() - a.scenePos().y()
        if abs(dx) >= abs(dy):
            side_a = "east" if dx >= 0 else "west"
        else:
            side_a = "south" if dy >= 0 else "north"
        side_b = self._opposite_side(side_a)
        return side_a, side_b

    def _has_device_link(self, device_a_id: str, device_b_id: str) -> bool:
        pair = {device_a_id, device_b_id}
        for link in self._site.links.values():
            if {link.device_a_id, link.device_b_id} == pair:
                return True
        return False

    def _create_device_link(
        self,
        a: DeviceNodeItem,
        b: DeviceNodeItem,
        side_a: str | None = None,
        side_b: str | None = None,
    ) -> bool:
        if a.device.id == b.device.id:
            QMessageBox.information(self, "Лінк", "Не можна створити лінк до цього ж пристрою.")
            return False
        if self._has_device_link(a.device.id, b.device.id):
            QMessageBox.information(self, "Лінк", "Лінк між цими пристроями вже існує.")
            return False
        if side_a is None or side_b is None:
            side_a, side_b = self._auto_link_sides(a, b)

        dialog = LinkFormDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        link = DeviceLink(
            id=uuid4().hex[:8],
            device_a_id=a.device.id,
            device_b_id=b.device.id,
            port_a=side_a,
            port_b=side_b,
            link_type=dialog.link_type(),
            cable_type=dialog.cable_type(),
        )
        self._site.links[link.id] = link
        self._refresh_scene()
        return True

class DeviceFormDialog(QDialog):
    def __init__(self, parent=None, pos_x: float = 0.0, pos_y: float = 0.0, device: Device | None = None) -> None:
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
        ip_validator = QRegularExpressionValidator(
            QRegularExpression(r"^(\d{1,3}\.){0,3}\d{0,3}$"), self
        )
        self._ip.setValidator(ip_validator)
        self._port_rows = []
        self._uplink = QComboBox(self)
        self._uplink.addItem("Ні", False)
        self._uplink.addItem("Так", True)
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
        form.addWidget(QLabel("Uplink"))
        form.addWidget(self._uplink)
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
        if device is not None:
            self._fill_from_device(device)

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
        ip_text = self._ip.text().strip()
        if ip_text:
            try:
                ipaddress.ip_address(ip_text)
            except ValueError:
                QMessageBox.warning(self, "IP адреса", "Некоректний формат IP адреси.")
                return
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
            is_uplink=bool(self._uplink.currentData()),
        )

    def apply_to_device(self, device: Device) -> None:
        device.name = self._name.text().strip() or device.name
        device.device_type = self._type.currentData()
        device.ip_address = self._ip.text().strip() or None
        device.notes_text = self._notes.toPlainText().strip() or None
        ports = {}
        for box, value in self._port_rows:
            text = value.text().strip()
            if not text:
                continue
            ports[box.currentData()] = int(text)
        device.ports = ports
        device.position = (self._pos_x, self._pos_y)
        device.is_uplink = bool(self._uplink.currentData())
        device.metadata.pop("manual_status", None)

    def _fill_from_device(self, device: Device) -> None:
        self._name.setText(device.name)
        idx = self._type.findData(device.device_type)
        if idx >= 0:
            self._type.setCurrentIndex(idx)
        self._ip.setText(device.ip_address or "")
        self._notes.setText(device.notes_text or "")
        if device.position:
            self._pos_x, self._pos_y = device.position
            self._pos_label.setText(f"{self._pos_x:.1f}, {self._pos_y:.1f}")
        self._uplink.setCurrentIndex(1 if device.is_uplink else 0)
        for port_type, port_val in (device.ports or {}).items():
            row = QHBoxLayout()
            type_box = QComboBox(self)
            for value, label in [("web", "Web"), ("ssh", "SSH"), ("snmp", "SNMP")]:
                type_box.addItem(label, value)
            idx = type_box.findData(port_type)
            if idx >= 0:
                type_box.setCurrentIndex(idx)
            value_edit = QLineEdit(self)
            value_edit.setValidator(QIntValidator(1, 65535, self))
            value_edit.setText(str(port_val))
            remove_btn = QPushButton("✕", self)
            remove_btn.setFixedWidth(28)

            def remove_row(row=row, type_box=type_box, value_edit=value_edit, remove_btn=remove_btn):
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
