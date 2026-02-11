from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import List

from app.elevation import ElevationProvider
from app.domain import Site
from app.rf_propagation import profile_diffraction


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
        diffraction = profile_diffraction(
            distances,
            elevations,
            start_total_height_m=start,
            end_total_height_m=end,
            freq_ghz=freq_ghz,
            use_fresnel=True,
            obstruction_grace_m=20.0,
        )
        clearance_needed = max(0.0, diffraction.max_los_obstruction_m)
        los_ok = not diffraction.blocked and diffraction.diffraction_loss_db <= 0.2
        if los_ok:
            status = "LOS OK"
        elif not diffraction.blocked and diffraction.diffraction_loss_db <= 8.0:
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
