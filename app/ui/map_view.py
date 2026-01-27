from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView


class MapBridge(QObject):
    def __init__(
        self,
        on_show_context_menu: Callable[[float, float, int, int], None],
        on_request_move_node: Callable[[str, float, float, float, float], None],
        on_select_node: Callable[[str], None],
    ) -> None:
        super().__init__()
        self._on_show_context_menu = on_show_context_menu
        self._on_request_move_node = on_request_move_node
        self._on_select_node = on_select_node

    @Slot(float, float, int, int)
    def showContextMenu(self, lat: float, lon: float, x: int, y: int) -> None:
        self._on_show_context_menu(lat, lon, x, y)

    @Slot(str, float, float, float, float)
    def requestMoveNode(
        self, node_id: str, lat: float, lon: float, prev_lat: float, prev_lon: float
    ) -> None:
        self._on_request_move_node(node_id, lat, lon, prev_lat, prev_lon)

    @Slot(str)
    def selectNode(self, node_id: str) -> None:
        self._on_select_node(node_id)


class MapView(QWebEngineView):
    def __init__(
        self,
        on_show_context_menu: Callable[[float, float, int, int], None],
        on_request_move_node: Callable[[str, float, float, float, float], None],
        on_select_node: Callable[[str], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._bridge = MapBridge(on_show_context_menu, on_request_move_node, on_select_node)
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)
        self.page().setWebChannel(self._channel)
        self.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )

        map_path = Path(__file__).resolve().parents[1] / "web" / "map.html"
        self.setUrl(QUrl.fromLocalFile(map_path.as_posix()))
        self.loadFinished.connect(self._on_load_finished)

    def add_marker(self, node_id: str, name: str, kind: str, lat: float, lon: float) -> None:
        js = (
            "addMarker("  # noqa: ISC003
            f"{node_id!r}, {name!r}, {kind!r}, {lat}, {lon}"
            ");"
        )
        self.page().runJavaScript(js)

    def move_marker(self, node_id: str, lat: float, lon: float) -> None:
        self.page().runJavaScript(f"moveMarker({node_id!r}, {lat}, {lon});")

    def focus_marker(self, node_id: str) -> None:
        self.page().runJavaScript(f"focusMarker({node_id!r});")

    def _on_load_finished(self, ok: bool) -> None:
        if ok:
            return
        self.setHtml(
            "<html><body style='font-family:sans-serif;'>"
            "<h3>Map failed to load</h3>"
            "<p>Qt WebEngine could not load the map page.</p>"
            "</body></html>"
        )
