from __future__ import annotations
from dataclasses import dataclass
from math import hypot
from typing import Iterable


@dataclass(frozen=True)
class MapPoint:
    x_m: float
    y_m: float
    z_m: float = 0.0
    frame: str = "ENU"


@dataclass(frozen=True)
class Geofence:
    fence_id: str
    polygon_xy_m: tuple[tuple[float,float],...]


class GeospatialService:
    """Metric-map utilities; CRS/geodetic adapters remain external."""

    def __init__(self) -> None:
        self._fences: dict[str,Geofence]={}
        self._map_version="unset"

    def set_map_version(self, version: str) -> None:
        if not version:
            raise ValueError("map version is required")
        self._map_version=version

    @property
    def map_version(self) -> str:
        return self._map_version

    def add_geofence(self, fence: Geofence) -> None:
        if len(fence.polygon_xy_m) < 3:
            raise ValueError("geofence polygon needs at least three points")
        self._fences[fence.fence_id]=fence

    @staticmethod
    def point_in_polygon(point: MapPoint, polygon: tuple[tuple[float,float],...]) -> bool:
        x,y=point.x_m,point.y_m
        inside=False
        j=len(polygon)-1
        for i in range(len(polygon)):
            xi,yi=polygon[i]
            xj,yj=polygon[j]
            intersects=((yi>y)!=(yj>y)) and (x < (xj-xi)*(y-yi)/((yj-yi) or 1e-12)+xi)
            if intersects:
                inside=not inside
            j=i
        return inside

    def fences_containing(self, point: MapPoint) -> tuple[str,...]:
        return tuple(
            fence_id for fence_id,fence in self._fences.items()
            if self.point_in_polygon(point,fence.polygon_xy_m)
        )

    @staticmethod
    def route_length_m(points: Iterable[MapPoint]) -> float:
        seq=list(points)
        return sum(hypot(b.x_m-a.x_m,b.y_m-a.y_m) for a,b in zip(seq,seq[1:]))
