from __future__ import annotations

from pathlib import Path
from typing import Callable
import json

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView


class MapBridge(QObject):
    def __init__(
        self,
        on_show_context_menu: Callable[[float, float, int, int], None],
        on_show_site_menu: Callable[[str, int, int], None],
        on_show_link_menu: Callable[[str, int, int], None],
        on_report_height: Callable[[float, float, int, int], None],
        on_map_click: Callable[[float, float], None],
        on_request_move_node: Callable[[str, float, float, float, float], None],
        on_request_site_link: Callable[[str, str], None],
        on_request_delete_link: Callable[[str], None],
        on_select_link: Callable[[str], None],
        on_prefetch_elevation: Callable[[float, float, float, float, int], None],
        on_request_rename_site: Callable[[str], None],
        on_select_node: Callable[[str], None],
        on_open_site: Callable[[str], None],
        on_set_height_mode: Callable[[bool], None],
        on_set_azimuth_mode: Callable[[bool], None],
        on_set_ruler_mode: Callable[[bool], None],
        on_set_los_mode: Callable[[bool], None],
        on_open_eirp: Callable[[], None],
        on_open_horizon: Callable[[], None],
        on_open_power: Callable[[], None],
        on_open_frequency: Callable[[], None],
    ) -> None:
        super().__init__()
        self._on_show_context_menu = on_show_context_menu
        self._on_show_site_menu = on_show_site_menu
        self._on_show_link_menu = on_show_link_menu
        self._on_report_height = on_report_height
        self._on_map_click = on_map_click
        self._on_request_move_node = on_request_move_node
        self._on_request_site_link = on_request_site_link
        self._on_request_delete_link = on_request_delete_link
        self._on_select_link = on_select_link
        self._on_prefetch_elevation = on_prefetch_elevation
        self._on_request_rename_site = on_request_rename_site
        self._on_select_node = on_select_node
        self._on_open_site = on_open_site
        self._on_set_height_mode = on_set_height_mode
        self._on_set_azimuth_mode = on_set_azimuth_mode
        self._on_set_ruler_mode = on_set_ruler_mode
        self._on_set_los_mode = on_set_los_mode
        self._on_open_eirp = on_open_eirp
        self._on_open_horizon = on_open_horizon
        self._on_open_power = on_open_power
        self._on_open_frequency = on_open_frequency

    @Slot(float, float, int, int)
    def showContextMenu(self, lat: float, lon: float, x: int, y: int) -> None:
        self._on_show_context_menu(lat, lon, x, y)

    @Slot(str, int, int)
    def showSiteMenu(self, site_id: str, x: int, y: int) -> None:
        self._on_show_site_menu(site_id, x, y)

    @Slot(str, int, int)
    def showLinkMenu(self, link_id: str, x: int, y: int) -> None:
        self._on_show_link_menu(link_id, x, y)

    @Slot(float, float, int, int)
    def reportHeight(self, lat: float, lon: float, x: int, y: int) -> None:
        self._on_report_height(lat, lon, x, y)

    @Slot(float, float)
    def mapClick(self, lat: float, lon: float) -> None:
        self._on_map_click(lat, lon)

    @Slot(str, float, float, float, float)
    def requestMoveNode(
        self, node_id: str, lat: float, lon: float, prev_lat: float, prev_lon: float
    ) -> None:
        self._on_request_move_node(node_id, lat, lon, prev_lat, prev_lon)

    @Slot(str)
    def selectNode(self, node_id: str) -> None:
        self._on_select_node(node_id)

    @Slot(str)
    def selectLink(self, link_id: str) -> None:
        self._on_select_link(link_id)

    @Slot(str)
    def requestRenameSite(self, site_id: str) -> None:
        self._on_request_rename_site(site_id)

    @Slot(str)
    def openSite(self, site_id: str) -> None:
        self._on_open_site(site_id)

    @Slot(bool)
    def setHeightMode(self, enabled: bool) -> None:
        self._on_set_height_mode(enabled)

    @Slot(bool)
    def setAzimuthMode(self, enabled: bool) -> None:
        self._on_set_azimuth_mode(enabled)

    @Slot(bool)
    def setRulerMode(self, enabled: bool) -> None:
        self._on_set_ruler_mode(enabled)

    @Slot(bool)
    def setLosMode(self, enabled: bool) -> None:
        self._on_set_los_mode(enabled)

    @Slot()
    def openEirpCalculator(self) -> None:
        self._on_open_eirp()

    @Slot()
    def openHorizonCalculator(self) -> None:
        self._on_open_horizon()

    @Slot()
    def openPowerCalculator(self) -> None:
        self._on_open_power()

    @Slot()
    def openFrequencyCalculator(self) -> None:
        self._on_open_frequency()

    @Slot(float, float, float, float, int)
    def prefetchElevation(
        self, south: float, west: float, north: float, east: float, zoom: int
    ) -> None:
        self._on_prefetch_elevation(south, west, north, east, zoom)

    @Slot(str, str)
    def requestSiteLink(self, site_a_id: str, site_b_id: str) -> None:
        self._on_request_site_link(site_a_id, site_b_id)

    @Slot(str)
    def requestDeleteLink(self, link_id: str) -> None:
        self._on_request_delete_link(link_id)


class MapView(QWebEngineView):
    def __init__(
        self,
        on_show_context_menu: Callable[[float, float, int, int], None],
        on_show_site_menu: Callable[[str, int, int], None],
        on_show_link_menu: Callable[[str, int, int], None],
        on_report_height: Callable[[float, float, int, int], None],
        on_map_click: Callable[[float, float], None],
        on_request_move_node: Callable[[str, float, float, float, float], None],
        on_request_site_link: Callable[[str, str], None],
        on_request_delete_link: Callable[[str], None],
        on_select_link: Callable[[str], None],
        on_prefetch_elevation: Callable[[float, float, float, float, int], None],
        on_request_rename_site: Callable[[str], None],
        on_select_node: Callable[[str], None],
        on_open_site: Callable[[str], None],
        on_set_height_mode: Callable[[bool], None],
        on_set_azimuth_mode: Callable[[bool], None],
        on_set_ruler_mode: Callable[[bool], None],
        on_set_los_mode: Callable[[bool], None],
        on_open_eirp: Callable[[], None],
        on_open_horizon: Callable[[], None],
        on_open_power: Callable[[], None],
        on_open_frequency: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._bridge = MapBridge(
            on_show_context_menu,
            on_show_site_menu,
            on_show_link_menu,
            on_report_height,
            on_map_click,
            on_request_move_node,
            on_request_site_link,
            on_request_delete_link,
            on_select_link,
            on_prefetch_elevation,
            on_request_rename_site,
            on_select_node,
            on_open_site,
            on_set_height_mode,
            on_set_azimuth_mode,
            on_set_ruler_mode,
            on_set_los_mode,
            on_open_eirp,
            on_open_horizon,
            on_open_power,
            on_open_frequency,
        )
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)
        self.page().setWebChannel(self._channel)
        self.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        profile = self.page().profile()
        profile.setHttpCacheMaximumSize(256 * 1024 * 1024)
        try:
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        except Exception:
            pass

        map_path = Path(__file__).resolve().parents[1] / "web" / "map.html"
        self.setUrl(QUrl.fromLocalFile(map_path.as_posix()))
        self.loadFinished.connect(self._on_load_finished)

    def request_viewport(self, callback) -> None:
        self.page().runJavaScript(
            "(() => { const b = map.getBounds(); return [b.getSouth(), b.getWest(), b.getNorth(), b.getEast(), map.getZoom()]; })();",
            callback,
        )

    def clear_web_cache(self) -> None:
        try:
            self.page().profile().clearHttpCache()
        except Exception:
            pass

    def add_marker(self, node_id: str, name: str, kind: str, lat: float, lon: float) -> None:
        js = (
            "addMarker("  # noqa: ISC003
            f"{node_id!r}, {name!r}, {kind!r}, {lat}, {lon}"
            ");"
        )
        self.page().runJavaScript(js)

    def set_marker_status(self, node_id: str, status: str) -> None:
        self.page().runJavaScript(f"setMarkerStatus({node_id!r}, {status!r});")

    def update_marker_label(self, node_id: str, name: str, kind: str) -> None:
        self.page().runJavaScript(f"updateMarkerLabel({node_id!r}, {name!r}, {kind!r});")

    def remove_marker(self, node_id: str) -> None:
        self.page().runJavaScript(f"removeMarker({node_id!r});")

    def add_coverage(
        self,
        site_id: str,
        lat: float,
        lon: float,
        azimuth: float,
        beamwidth: float,
        range_km: float,
        color: str,
    ) -> None:
        self.page().runJavaScript(
            f"addCoverage({site_id!r}, {lat}, {lon}, {azimuth}, {beamwidth}, {range_km}, {color!r});"
        )

    def update_coverage(
        self,
        site_id: str,
        lat: float,
        lon: float,
        azimuth: float,
        beamwidth: float,
        range_km: float,
        color: str,
        tooltip: str,
    ) -> None:
        self.page().runJavaScript(
            f"updateCoverage({site_id!r}, {lat}, {lon}, {azimuth}, {beamwidth}, {range_km}, {color!r}, {tooltip!r});"
        )

    def update_coverage_points(self, site_id: str, points: list, color: str, tooltip: str) -> None:
        self.page().runJavaScript(
            f"updateCoveragePoints({site_id!r}, {points!r}, {color!r}, {tooltip!r});"
        )

    def update_coverage_raster_tile(self, site_id: str, data_url: str, bounds: list) -> None:
        self.page().runJavaScript(
            f"updateCoverageRasterTile({site_id!r}, {data_url!r}, {bounds!r});"
        )

    def update_coverage_bands(self, site_id: str, bands: list, tooltip: str) -> None:
        bands_json = json.dumps(bands, ensure_ascii=False)
        tooltip_json = json.dumps(tooltip, ensure_ascii=False)
        self.page().runJavaScript(
            f"updateCoverageBands({site_id!r}, {bands_json}, {tooltip_json});"
        )

    def remove_coverage(self, site_id: str) -> None:
        self.page().runJavaScript(f"removeCoverage({site_id!r});")

    def set_coverage_visible(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setCoverageVisible({str(enabled).lower()});")

    def clear_all(self) -> None:
        self.page().runJavaScript("clearAll();")

    def add_link(
        self,
        link_id: str,
        label: str,
        kind: str,
        info: str,
        distance_km: float | None,
        lat_a: float,
        lon_a: float,
        lat_b: float,
        lon_b: float,
    ) -> None:
        distance_js = "null" if distance_km is None else str(distance_km)
        js = (
            "addLink("
            f"{link_id!r}, {label!r}, {kind!r}, {info!r}, {distance_js}, {lat_a}, {lon_a}, {lat_b}, {lon_b}"
            ");"
        )
        self.page().runJavaScript(js)

    def update_link(self, link_id: str, lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> None:
        self.page().runJavaScript(f"updateLink({link_id!r}, {lat_a}, {lon_a}, {lat_b}, {lon_b});")

    def remove_link(self, link_id: str) -> None:
        self.page().runJavaScript(f"removeLink({link_id!r});")

    def set_link_mode(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setLinkMode({str(enabled).lower()});")

    def set_height_mode(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setHeightMode({str(enabled).lower()});")

    def set_los_mode(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setLosMode({str(enabled).lower()});")

    def set_azimuth_mode(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setAzimuthMode({str(enabled).lower()});")

    def set_ruler_mode(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setRulerMode({str(enabled).lower()});")

    def add_horizon_point(self, lat: float, lon: float) -> None:
        self.page().runJavaScript(f"addHorizonPoint({lat}, {lon});")

    def clear_horizon_points(self) -> None:
        self.page().runJavaScript("clearHorizonPoints();")

    def update_link_meta(
        self, link_id: str, label: str, kind: str, info: str, distance_km: float | None
    ) -> None:
        distance_js = "null" if distance_km is None else str(distance_km)
        self.page().runJavaScript(
            f"updateLinkMeta({link_id!r}, {label!r}, {kind!r}, {info!r}, {distance_js});"
        )

    def set_elevation_layer(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setElevationVisible({str(enabled).lower()});")

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
