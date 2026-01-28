from __future__ import annotations

import math
from pathlib import Path
from typing import Optional
from urllib.request import urlopen

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None


class ElevationProvider:
    """Simple DEM provider using Mapzen Terrarium tiles."""

    def __init__(self, cache_dir: Path | str | None = None, zoom: int = 12) -> None:
        self.zoom = zoom
        self.cache_dir = Path(cache_dir or Path(__file__).resolve().parents[1] / "cache" / "elevation")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.available = Image is not None

    def get_elevation(self, lat: float, lon: float) -> Optional[float]:
        if Image is None:
            return None
        tile_x, tile_y, px, py = self._tile_and_pixel(lat, lon, self.zoom)
        tile_path = self.cache_dir / str(self.zoom) / str(tile_x) / f"{tile_y}.png"
        if not tile_path.exists():
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            url = (
                "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
                f"{self.zoom}/{tile_x}/{tile_y}.png"
            )
            try:
                with urlopen(url, timeout=10) as response:
                    tile_path.write_bytes(response.read())
            except Exception:
                return None
        try:
            with Image.open(tile_path) as img:
                img = img.convert("RGB")
                r, g, b = img.getpixel((px, py))
                return (r * 256 + g + b / 256) - 32768
        except Exception:
            return None

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
