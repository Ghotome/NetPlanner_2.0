from __future__ import annotations

from dataclasses import dataclass
from math import log10, sqrt
from typing import Sequence


EARTH_RADIUS_EFFECTIVE_M = 6371000.0 * 1.1
FRESNEL_CLEARANCE_FACTOR = 0.6


@dataclass(frozen=True)
class DiffractionResult:
    blocked: bool
    diffraction_loss_db: float
    max_los_obstruction_m: float
    dominant_v: float


def knife_edge_loss_db(v: float) -> float:
    if v <= -0.78:
        return 0.0
    return 6.9 + (20.0 * log10(sqrt(((v - 0.1) ** 2) + 1.0) + v - 0.1))


def fresnel_radius_m(d1_km: float, d2_km: float, freq_ghz: float) -> float:
    total_km = d1_km + d2_km
    if freq_ghz <= 0 or d1_km <= 0 or d2_km <= 0 or total_km <= 0:
        return 0.0
    return 17.32 * sqrt((d1_km * d2_km) / (freq_ghz * total_km))


def _find_dominant_v(
    distances_m: Sequence[float],
    profile_m: Sequence[float],
    wavelength_m: float,
    start_idx: int,
    end_idx: int,
) -> tuple[int, float]:
    if end_idx - start_idx < 2:
        return -1, -1e9
    dist_total = distances_m[end_idx] - distances_m[start_idx]
    if dist_total <= 0:
        return -1, -1e9
    h_start = profile_m[start_idx]
    h_end = profile_m[end_idx]

    best_idx = -1
    best_v = -1e9
    for i in range(start_idx + 1, end_idx):
        d1_m = distances_m[i] - distances_m[start_idx]
        d2_m = distances_m[end_idx] - distances_m[i]
        if d1_m <= 0 or d2_m <= 0:
            continue
        los_h = h_start + ((h_end - h_start) * (d1_m / dist_total))
        h_excess = profile_m[i] - los_h
        v = h_excess * sqrt((2.0 * (d1_m + d2_m)) / (wavelength_m * d1_m * d2_m))
        if v > best_v:
            best_v = v
            best_idx = i
    return best_idx, best_v


def _deygout_loss_db(
    distances_m: Sequence[float],
    profile_m: Sequence[float],
    wavelength_m: float,
    max_total_loss_db: float | None = None,
) -> tuple[float, float]:
    total_loss = 0.0
    dominant_v = -1e9
    stack: list[tuple[int, int]] = [(0, len(profile_m) - 1)]
    while stack:
        start_idx, end_idx = stack.pop()
        idx, v = _find_dominant_v(distances_m, profile_m, wavelength_m, start_idx, end_idx)
        if idx < 0:
            continue
        dominant_v = max(dominant_v, v)
        if v <= -0.78:
            continue
        total_loss += knife_edge_loss_db(v)
        if max_total_loss_db is not None and total_loss > max_total_loss_db:
            return total_loss, dominant_v
        if idx - start_idx > 1:
            stack.append((start_idx, idx))
        if end_idx - idx > 1:
            stack.append((idx, end_idx))
    return total_loss, dominant_v


def profile_diffraction(
    distances_km: Sequence[float],
    terrain_profile_m: Sequence[float],
    start_total_height_m: float,
    end_total_height_m: float,
    freq_ghz: float | None,
    use_fresnel: bool = True,
    fresnel_factor: float = FRESNEL_CLEARANCE_FACTOR,
    earth_radius_m: float = EARTH_RADIUS_EFFECTIVE_M,
    obstruction_grace_m: float | None = None,
    max_total_loss_db: float | None = None,
) -> DiffractionResult:
    if len(distances_km) != len(terrain_profile_m) or len(distances_km) < 2:
        return DiffractionResult(blocked=True, diffraction_loss_db=0.0, max_los_obstruction_m=0.0, dominant_v=-1e9)

    dist0_km = distances_km[0]
    shifted_dist_km = [max(d - dist0_km, 0.0) for d in distances_km]
    total_km = shifted_dist_km[-1]
    if total_km <= 0:
        return DiffractionResult(blocked=False, diffraction_loss_db=0.0, max_los_obstruction_m=0.0, dominant_v=-1e9)

    freq_valid = freq_ghz is not None and freq_ghz > 0.0
    wavelength_m = (0.3 / freq_ghz) if freq_valid else 0.0

    profile_m = [0.0] * len(shifted_dist_km)
    profile_m[0] = start_total_height_m
    profile_m[-1] = end_total_height_m

    max_obstruction_m = 0.0
    any_obstruction = False
    for i in range(1, len(shifted_dist_km) - 1):
        d1_km = shifted_dist_km[i]
        d2_km = total_km - d1_km
        if d1_km <= 0 or d2_km <= 0:
            continue
        frac = d1_km / total_km
        los_h = start_total_height_m + ((end_total_height_m - start_total_height_m) * frac)
        d1_m = d1_km * 1000.0
        d2_m = d2_km * 1000.0
        bulge_m = (d1_m * d2_m) / (2.0 * earth_radius_m)
        terrain_eff = terrain_profile_m[i] + bulge_m
        geom_excess = terrain_eff - los_h
        if geom_excess > 0.0:
            any_obstruction = True
            if geom_excess > max_obstruction_m:
                max_obstruction_m = geom_excess
            if obstruction_grace_m is not None and geom_excess > obstruction_grace_m:
                return DiffractionResult(
                    blocked=True,
                    diffraction_loss_db=0.0,
                    max_los_obstruction_m=max_obstruction_m,
                    dominant_v=1e9,
                )
        clearance_m = 0.0
        if use_fresnel and freq_valid:
            clearance_m = fresnel_factor * fresnel_radius_m(d1_km, d2_km, freq_ghz)
        profile_m[i] = terrain_eff + clearance_m

    if not any_obstruction:
        return DiffractionResult(blocked=False, diffraction_loss_db=0.0, max_los_obstruction_m=0.0, dominant_v=-1e9)
    if not freq_valid:
        return DiffractionResult(
            blocked=True,
            diffraction_loss_db=0.0,
            max_los_obstruction_m=max_obstruction_m,
            dominant_v=1e9,
        )

    distances_m = [d * 1000.0 for d in shifted_dist_km]
    loss_db, dominant_v = _deygout_loss_db(
        distances_m,
        profile_m,
        wavelength_m,
        max_total_loss_db=max_total_loss_db,
    )
    return DiffractionResult(
        blocked=False,
        diffraction_loss_db=max(0.0, loss_db),
        max_los_obstruction_m=max_obstruction_m,
        dominant_v=dominant_v,
    )
