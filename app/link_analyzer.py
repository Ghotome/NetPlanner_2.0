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

        antenna_a = next((a for a in site_a.antennas if a.applied), None) if site_a.antennas else None
        if antenna_a is None and site_a.antennas:
            antenna_a = site_a.antennas[0]
        antenna_b = next((a for a in site_b.antennas if a.applied), None) if site_b.antennas else None
        if antenna_b is None and site_b.antennas:
            antenna_b = site_b.antennas[0]
        start = elevations[0] + (antenna_a.height_m or 0.0 if antenna_a else 0.0)
        end = elevations[-1] + (antenna_b.height_m or 0.0 if antenna_b else 0.0)
        freq_ghz = None
        if antenna_a and antenna_a.frequency_ghz:
            freq_ghz = antenna_a.frequency_ghz
        elif antenna_b and antenna_b.frequency_ghz:
            freq_ghz = antenna_b.frequency_ghz
        freq_valid = freq_ghz is not None and freq_ghz > 0
        fresnel_factor = 0.6
        earth_radius_m = 6371000.0 * 1.1
        blocked = False
        max_obstruction = 0.0
        for i in range(1, len(elevations) - 1):
            frac = distances[i] / total_km if total_km else 0
            expected = start + (end - start) * frac
            d1_m = distances[i] * 1000.0
            d2_m = (total_km - distances[i]) * 1000.0
            bulge_m = (d1_m * d2_m) / (2.0 * earth_radius_m) if total_km else 0.0
            clearance = 0.0
            if freq_valid and total_km:
                r1 = 17.32 * ((distances[i] * (total_km - distances[i])) / (freq_ghz * total_km)) ** 0.5
                clearance = fresnel_factor * r1
            obstruction = (elevations[i] + bulge_m) - (expected - clearance)
            if obstruction > 0:
                blocked = True
                max_obstruction = max(max_obstruction, obstruction)

        los_ok = not blocked
        clearance_needed = max_obstruction if blocked else 0.0
        if los_ok:
            status = "LOS OK"
        elif clearance_needed < 12:
            status = "Possible"
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
