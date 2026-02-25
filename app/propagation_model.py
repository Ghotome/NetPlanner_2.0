from __future__ import annotations

from dataclasses import dataclass
import json
from math import sqrt
from typing import Any


@dataclass
class PropagationModelConfig:
    model_version: str = "v1"
    k_factor: float = 1.1
    fresnel_factor: float = 0.6
    obstruction_grace_m: float = 20.0
    horizon_extension_km: float = 10.0
    green_threshold_db: float = 5.0
    yellow_threshold_db: float = 0.0
    red_threshold_db: float = -5.0

    def __post_init__(self) -> None:
        self.k_factor = max(0.5, min(2.0, float(self.k_factor)))
        self.fresnel_factor = max(0.0, min(1.0, float(self.fresnel_factor)))
        self.obstruction_grace_m = max(0.0, float(self.obstruction_grace_m))
        self.horizon_extension_km = max(0.0, float(self.horizon_extension_km))

        self.green_threshold_db = float(self.green_threshold_db)
        self.yellow_threshold_db = float(self.yellow_threshold_db)
        self.red_threshold_db = float(self.red_threshold_db)
        if self.green_threshold_db < self.yellow_threshold_db:
            self.green_threshold_db = self.yellow_threshold_db
        if self.yellow_threshold_db < self.red_threshold_db:
            self.yellow_threshold_db = self.red_threshold_db

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any] | None) -> "PropagationModelConfig":
        if not isinstance(metadata, dict):
            return cls()
        raw = metadata.get("propagation_model")
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return cls()
            if isinstance(data, dict):
                return cls.from_dict(data)
        if isinstance(raw, dict):
            return cls.from_dict(raw)
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PropagationModelConfig":
        return cls(
            model_version=str(data.get("model_version", "v1")),
            k_factor=float(data.get("k_factor", 1.1)),
            fresnel_factor=float(data.get("fresnel_factor", 0.6)),
            obstruction_grace_m=float(data.get("obstruction_grace_m", 20.0)),
            horizon_extension_km=float(data.get("horizon_extension_km", 10.0)),
            green_threshold_db=float(data.get("green_threshold_db", 5.0)),
            yellow_threshold_db=float(data.get("yellow_threshold_db", 0.0)),
            red_threshold_db=float(data.get("red_threshold_db", -5.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "k_factor": self.k_factor,
            "fresnel_factor": self.fresnel_factor,
            "obstruction_grace_m": self.obstruction_grace_m,
            "horizon_extension_km": self.horizon_extension_km,
            "green_threshold_db": self.green_threshold_db,
            "yellow_threshold_db": self.yellow_threshold_db,
            "red_threshold_db": self.red_threshold_db,
        }

    def to_metadata_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    def effective_earth_radius_m(self, base_earth_radius_m: float = 6_371_000.0) -> float:
        return base_earth_radius_m * self.k_factor

    def radio_horizon_km(self, total_height_m: float) -> float:
        return 3.57 * sqrt(self.k_factor) * sqrt(max(total_height_m, 0.0))

    def radio_horizon_limit_km(self, tx_total_m: float, rx_total_m: float) -> float:
        return (
            self.radio_horizon_km(tx_total_m)
            + self.radio_horizon_km(rx_total_m)
            + self.horizon_extension_km
        )

    def short_label(self) -> str:
        return (
            f"k_factor={self.k_factor:.2f} | Frensel={self.fresnel_factor:.2f} | "
            f"obstruction_grace={self.obstruction_grace_m:.1f} m"
        )
