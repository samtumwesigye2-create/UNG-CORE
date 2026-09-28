from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum


class FleetHealth(str, Enum):
    HEALTHY="healthy"
    DEGRADED="degraded"
    OFFLINE="offline"
    MAINTENANCE="maintenance"


@dataclass(frozen=True)
class FleetAsset:
    asset_id: str
    software_version: str
    config_version: str
    calibration_version: str
    connectivity: str
    health: FleetHealth
    battery_percent: float | None = None
    deployment_ring: str = "default"


class FleetManager:
    def __init__(self) -> None:
        self._assets: dict[str,FleetAsset]={}

    def register(self, asset: FleetAsset) -> FleetAsset:
        if asset.asset_id in self._assets:
            raise ValueError("asset already exists")
        self._assets[asset.asset_id]=asset
        return asset

    def update(self, asset_id: str, **changes) -> FleetAsset:
        current=self._assets[asset_id]
        updated=replace(current, **changes)
        self._assets[asset_id]=updated
        return updated

    def by_ring(self, ring: str) -> tuple[FleetAsset,...]:
        return tuple(a for a in self._assets.values() if a.deployment_ring==ring)

    def unhealthy(self) -> tuple[FleetAsset,...]:
        return tuple(a for a in self._assets.values() if a.health is not FleetHealth.HEALTHY)
