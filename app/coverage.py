from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

from app.domain import AntennaParams


@dataclass(frozen=True)
class CoverageBreakdown:
    base_km: float
    factors: dict[str, float]
    range_km: float


class CoverageCalculator:
    def __init__(
        self,
        min_range_km: float = 0.2,
        max_range_km: float | None = 100.0,
    ) -> None:
        self.min_range_km = min_range_km
        self.max_range_km = max_range_km

    def estimate_range_km(
        self,
        antenna: AntennaParams,
        site_elevation_m: Optional[float] = None,
        beamwidth_deg: Optional[float] = None,
    ) -> CoverageBreakdown:
        base_km = 0.0
        factors = {
            "height": self._height_factor(antenna.height_m),
            "beamwidth": self._beamwidth_factor(
                beamwidth_deg if beamwidth_deg is not None else antenna.beamwidth_deg
            ),
            "type": self._antenna_type_factor(antenna.antenna_type),
            "elevation": self._elevation_factor(site_elevation_m),
        }
        range_km = 0.0
        budget_km = self.link_budget_range_km(antenna)
        if budget_km is not None:
            range_km = budget_km
            factors["link_budget"] = 1.0
        range_km = max(self.min_range_km, range_km)
        if self.max_range_km is not None:
            range_km = min(self.max_range_km, range_km)
        return CoverageBreakdown(base_km=base_km, factors=factors, range_km=range_km)

    @staticmethod
    def _height_factor(height_m: Optional[float]) -> float:
        if not height_m:
            return 1.0
        clamped = min(max(height_m, 0.0), 80.0)
        return 1.0 + (clamped / 160.0)

    @staticmethod
    def _beamwidth_factor(beamwidth_deg: Optional[float]) -> float:
        if not beamwidth_deg:
            return 1.0
        normalized = max(beamwidth_deg, 10.0)
        factor = (120.0 / normalized) ** 0.12
        return CoverageCalculator._clamp(factor, 0.85, 1.2)

    @staticmethod
    def _antenna_type_factor(antenna_type: Optional[str]) -> float:
        return {
            "Омніполярна": 0.9,
            "Секторна": 1.0,
            "Спрямована": 1.1,
        }.get(antenna_type or "", 1.0)

    @staticmethod
    def _elevation_factor(elevation_m: Optional[float]) -> float:
        if elevation_m is None:
            return 1.0
        clamped = min(max(elevation_m, 0.0), 2000.0)
        return 1.0 + (clamped / 8000.0)

    @staticmethod
    def link_budget_range_km(antenna: AntennaParams) -> Optional[float]:
        freq_ghz = antenna.frequency_ghz
        tx_power = antenna.tx_power_dbm
        rx_sens = CoverageCalculator.rx_sensitivity_dbm(antenna)
        if freq_ghz is None or tx_power is None or rx_sens is None or freq_ghz <= 0:
            return None
        tx_gain = antenna.gain_dbi or 0.0
        rx_gain = antenna.rx_gain_dbi or 0.0
        misc_losses = antenna.misc_losses_db or 0.0
        margin = antenna.link_margin_db or 0.0
        fspl_max = tx_power + tx_gain + rx_gain - misc_losses - (rx_sens + margin)
        if fspl_max <= 0:
            return None
        term = (fspl_max - 92.45 - (20.0 * math.log10(freq_ghz))) / 20.0
        return 10 ** term

    @staticmethod
    def rx_sensitivity_dbm(antenna: AntennaParams) -> Optional[float]:
        bw_mhz = CoverageCalculator._channel_width_mhz(antenna)
        if bw_mhz is not None and bw_mhz > 0:
            nf_db = antenna.noise_figure_db
            required_sinr_db = antenna.required_sinr_db
            if nf_db is not None and required_sinr_db is not None:
                thermal_dbm = -174.0 + (10.0 * math.log10(bw_mhz * 1_000_000.0))
                return thermal_dbm + nf_db + required_sinr_db

        if antenna.rx_sensitivity_dbm is None:
            return None

        if bw_mhz is None or bw_mhz <= 0:
            return antenna.rx_sensitivity_dbm

        ref_mhz = CoverageCalculator._reference_channel_width_mhz(antenna)
        return antenna.rx_sensitivity_dbm + (10.0 * math.log10(bw_mhz / ref_mhz))

    @staticmethod
    def _channel_width_mhz(antenna: AntennaParams) -> Optional[float]:
        bw_mhz = antenna.channel_width_mhz
        if bw_mhz is not None and bw_mhz > 0:
            return bw_mhz
        return CoverageCalculator._reference_channel_width_mhz(antenna)

    @staticmethod
    def _reference_channel_width_mhz(antenna: AntennaParams) -> float:
        freq_ghz = antenna.frequency_ghz or 0.0
        if 0.0 < freq_ghz < 1.0:
            return 0.0125
        return 20.0

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))
