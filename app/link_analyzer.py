from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import List

from app.elevation import ElevationProvider
from app.domain import Site


@dataclass
class LinkProfile:
    distances_km: List[float]
    elevations_m: List[float]
    los_ok: bool
    clearance_needed_m: float
    status: str


class LinkAnalyzer:
    def __init__(self, elevation: ElevationProvider) -> None:
        self._elevation = elevation

    def analyze(self, site_a: Site, site_b: Site, samples: int = 30) -> LinkProfile:
        lat1, lon1 = site_a.location.lat, site_a.location.lon
        lat2, lon2 = site_b.location.lat, site_b.location.lon

        distances = []
        elevations = []
        total_km = self._distance_km(lat1, lon1, lat2, lon2)

        for i in range(samples + 1):
            t = i / samples
            lat = lat1 + (lat2 - lat1) * t
            lon = lon1 + (lon2 - lon1) * t
            elev = self._elevation.get_elevation(lat, lon)
            elevations.append(elev if elev is not None else 0.0)
            distances.append(total_km * t)

        start = elevations[0] + (site_a.antenna.height_m or 0.0)
        end = elevations[-1] + (site_b.antenna.height_m or 0.0)
        blocked = False
        max_obstruction = 0.0
        for i in range(1, len(elevations) - 1):
            expected = start + (end - start) * (distances[i] / total_km if total_km else 0)
            obstruction = elevations[i] - expected
            if obstruction > 0:
                blocked = True
                max_obstruction = max(max_obstruction, obstruction)

        los_ok = not blocked
        clearance_needed = max_obstruction if blocked else 0.0
        if los_ok:
            status = "LOS OK"
        elif clearance_needed < 5:
            status = "Margin low"
        else:
            status = "Blocked"

        return LinkProfile(
            distances_km=distances,
            elevations_m=elevations,
            los_ok=los_ok,
            clearance_needed_m=clearance_needed,
            status=status,
        )

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        return r * c
