from __future__ import annotations

from array import array
import math
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Optional, Sequence
from urllib.request import urlopen

from app.runtime_paths import ensure_cache_subdir

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None


class ElevationProvider:
    """Simple DEM provider using Mapzen Terrarium tiles."""

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        zoom: int = 12,
        tile_cache_size: int = 256,
    ) -> None:
        self.zoom = zoom
        self.cache_dir = Path(cache_dir) if cache_dir is not None else ensure_cache_subdir("elevation")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.available = Image is not None
        self._tile_cache: OrderedDict[tuple[int, int, int], Image.Image] = OrderedDict()
        self._tile_cache_size = max(0, tile_cache_size)
        self._tile_lock = threading.Lock()

    def clear_cache(self) -> None:
        with self._tile_lock:
            self._tile_cache.clear()
        if not self.cache_dir.exists():
            return
        for path in self.cache_dir.rglob("*"):
            if path.is_file():
                path.unlink(missing_ok=True)
        for path in sorted(self.cache_dir.glob("**/*"), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    continue
        try:
            self.cache_dir.rmdir()
        except OSError:
            pass

    def get_elevation(self, lat: float, lon: float) -> Optional[float]:
        if Image is None:
            return None
        tile_x, tile_y, px, py = self._tile_and_pixel(lat, lon, self.zoom)
        tile = self._get_tile(self.zoom, tile_x, tile_y)
        if tile is None:
            return None
        try:
            r, g, b = tile.getpixel((px, py))
            return (r * 256 + g + b / 256) - 32768
        except Exception:
            return None

    def get_elevations_grid(
        self,
        lat_values: Sequence[float],
        lon_values: Sequence[float],
        cancel_event: threading.Event | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[array] | None:
        """Return DEM grid for all (lat, lon) pairs with tile-local batching."""
        if Image is None:
            return None
        if not lat_values:
            return []
        if not lon_values:
            return [array("f") for _ in lat_values]

        zoom = self.zoom
        n = 2.0**zoom
        max_tile_index = int(n - 1)
        nan = float("nan")

        lon_pixels: list[tuple[int, int]] = []
        for lon in lon_values:
            x = ((lon + 180.0) / 360.0) * n
            tile_x = int(x)
            px = int((x - tile_x) * 256)
            tile_x = max(0, min(max_tile_index, tile_x))
            px = max(0, min(255, px))
            lon_pixels.append((tile_x, px))

        lat_pixels: list[tuple[int, int]] = []
        for lat in lat_values:
            lat_clamped = max(-89.999999, min(89.999999, lat))
            lat_rad = math.radians(lat_clamped)
            y = (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * n
            tile_y = int(y)
            py = int((y - tile_y) * 256)
            tile_y = max(0, min(max_tile_index, tile_y))
            py = max(0, min(255, py))
            lat_pixels.append((tile_y, py))

        rows: list[array] = []
        call_cache: dict[tuple[int, int, int], Image.Image | None] = {}
        total_rows = len(lat_pixels)
        for row_idx, (tile_y, py) in enumerate(lat_pixels, start=1):
            if cancel_event is not None and cancel_event.is_set():
                return None
            row = array("f")
            for tile_x, px in lon_pixels:
                if cancel_event is not None and cancel_event.is_set():
                    return None
                key = (zoom, tile_x, tile_y)
                tile = call_cache.get(key)
                if tile is None and key not in call_cache:
                    tile = self._get_tile(zoom, tile_x, tile_y)
                    call_cache[key] = tile
                if tile is None:
                    row.append(nan)
                    continue
                try:
                    r, g, b = tile.getpixel((px, py))
                    row.append((r * 256 + g + b / 256) - 32768)
                except Exception:
                    row.append(nan)
            rows.append(row)
            if on_progress is not None:
                on_progress(row_idx, total_rows)
        return rows

    def _get_tile(self, zoom: int, tile_x: int, tile_y: int) -> Optional["Image.Image"]:
        if Image is None:
            return None
        key = (zoom, tile_x, tile_y)
        with self._tile_lock:
            cached = self._tile_cache.get(key)
            if cached is not None:
                self._tile_cache.move_to_end(key)
                return cached

        tile_path = self.cache_dir / str(zoom) / str(tile_x) / f"{tile_y}.png"
        if not tile_path.exists():
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            url = (
                "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
                f"{zoom}/{tile_x}/{tile_y}.png"
            )
            try:
                with urlopen(url, timeout=10) as response:
                    tile_path.write_bytes(response.read())
            except Exception:
                return None
        try:
            with Image.open(tile_path) as img:
                rgb = img.convert("RGB")
                rgb.load()
        except Exception:
            return None

        if self._tile_cache_size > 0:
            with self._tile_lock:
                self._tile_cache[key] = rgb
                if len(self._tile_cache) > self._tile_cache_size:
                    self._tile_cache.popitem(last=False)
        return rgb

    @staticmethod
    def _tile_and_pixel(lat: float, lon: float, zoom: int) -> tuple[int, int, int, int]:
        lat_rad = math.radians(lat)
        n = 2.0**zoom
        xtile = int((lon + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
        x = (lon + 180.0) / 360.0 * n
        y = (1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n
        px = int((x - xtile) * 256)
        py = int((y - ytile) * 256)
        return xtile, ytile, px, py

    def prefetch_tiles(self, bounds: tuple[float, float, float, float], zoom: int) -> None:
        """Prefetch tiles for bounds (min_lat, min_lon, max_lat, max_lon)."""
        if Image is None:
            return
        min_lat, min_lon, max_lat, max_lon = bounds
        x1, y1, _, _ = self._tile_and_pixel(max_lat, min_lon, zoom)
        x2, y2, _, _ = self._tile_and_pixel(min_lat, max_lon, zoom)
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                tile_path = self.cache_dir / str(zoom) / str(x) / f"{y}.png"
                if tile_path.exists():
                    continue
                tile_path.parent.mkdir(parents=True, exist_ok=True)
                url = (
                    "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
                    f"{zoom}/{x}/{y}.png"
                )
                try:
                    with urlopen(url, timeout=10) as response:
                        tile_path.write_bytes(response.read())
                except Exception:
                    continue
