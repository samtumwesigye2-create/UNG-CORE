from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time


class ClockQuality(str, Enum):
    GOOD = "good"
    DEGRADED = "degraded"
    UNSYNCED = "unsynced"


@dataclass(frozen=True)
class ClockSample:
    source: str
    source_time_ns: int
    received_monotonic_ns: int
    uncertainty_ns: int = 0


@dataclass(frozen=True)
class ClockStatus:
    source: str
    quality: ClockQuality
    offset_ns: int
    drift_ppm: float
    uncertainty_ns: int
    age_ms: float


class TimeSyncMonitor:
    """Health model for authoritative time sources.

    PTP/GNSS/NTP integration belongs in platform adapters. This class
    normalizes their measurements and exposes health for the rest of UNG.
    """

    def __init__(
        self,
        *,
        max_offset_ns: int = 5_000_000,
        max_drift_ppm: float = 50.0,
        stale_after_ms: float = 2_000.0,
    ) -> None:
        self.max_offset_ns = int(max_offset_ns)
        self.max_drift_ppm = float(max_drift_ppm)
        self.stale_after_ms = float(stale_after_ms)
        self._last_sample: ClockSample | None = None
        self._last_offset_ns: int | None = None
        self._drift_ppm = 0.0

    def update(self, sample: ClockSample, local_wall_time_ns: int | None = None) -> ClockStatus:
        if sample.uncertainty_ns < 0:
            raise ValueError("uncertainty_ns must be non-negative")
        if local_wall_time_ns is None:
            local_wall_time_ns = time.time_ns()

        offset_ns = int(sample.source_time_ns - local_wall_time_ns)

        if self._last_sample is not None and self._last_offset_ns is not None:
            elapsed_ns = sample.received_monotonic_ns - self._last_sample.received_monotonic_ns
            if elapsed_ns > 0:
                self._drift_ppm = ((offset_ns - self._last_offset_ns) / elapsed_ns) * 1_000_000.0

        self._last_sample = sample
        self._last_offset_ns = offset_ns
        return self.status(now_monotonic_ns=sample.received_monotonic_ns)

    def status(self, *, now_monotonic_ns: int | None = None) -> ClockStatus:
        if self._last_sample is None or self._last_offset_ns is None:
            return ClockStatus("none", ClockQuality.UNSYNCED, 0, 0.0, 0, float("inf"))

        if now_monotonic_ns is None:
            now_monotonic_ns = time.monotonic_ns()
        age_ms = max(0.0, (now_monotonic_ns - self._last_sample.received_monotonic_ns) / 1_000_000.0)

        if age_ms > self.stale_after_ms:
            quality = ClockQuality.UNSYNCED
        elif abs(self._last_offset_ns) > self.max_offset_ns or abs(self._drift_ppm) > self.max_drift_ppm:
            quality = ClockQuality.DEGRADED
        else:
            quality = ClockQuality.GOOD

        return ClockStatus(
            source=self._last_sample.source,
            quality=quality,
            offset_ns=self._last_offset_ns,
            drift_ppm=self._drift_ppm,
            uncertainty_ns=self._last_sample.uncertainty_ns,
            age_ms=age_ms,
        )
