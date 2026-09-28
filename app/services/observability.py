from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from statistics import mean
import time
from typing import Any


@dataclass(frozen=True)
class TraceEvent:
    timestamp_ns: int
    component: str
    event: str
    attributes: dict[str, Any]


class UnifiedObservability:
    """Dependency-light metrics/tracing core with export-friendly snapshots."""

    def __init__(self, latency_window: int = 512, trace_window: int = 1024) -> None:
        if latency_window <= 0 or trace_window <= 0:
            raise ValueError("windows must be positive")
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._latencies: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=latency_window))
        self._traces: deque[TraceEvent] = deque(maxlen=trace_window)

    def increment(self, name: str, amount: int = 1) -> None:
        self._counters[name] += int(amount)

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = float(value)

    def observe_latency_ms(self, name: str, value_ms: float) -> None:
        if value_ms < 0:
            raise ValueError("latency cannot be negative")
        self._latencies[name].append(float(value_ms))

    def trace(self, component: str, event: str, **attributes: Any) -> None:
        self._traces.append(
            TraceEvent(
                timestamp_ns=time.time_ns(),
                component=component,
                event=event,
                attributes=dict(attributes),
            )
        )

    def snapshot(self) -> dict[str, Any]:
        latency = {}
        for name, values in self._latencies.items():
            sample = list(values)
            if not sample:
                continue
            ordered = sorted(sample)

            def percentile(p: float) -> float:
                idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))
                return ordered[idx]

            latency[name] = {
                "count": len(sample),
                "mean_ms": mean(sample),
                "max_ms": max(sample),
                "p95_ms": percentile(0.95),
                "p99_ms": percentile(0.99),
            }

        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "latency": latency,
            "recent_traces": [
                {
                    "timestamp_ns": event.timestamp_ns,
                    "component": event.component,
                    "event": event.event,
                    "attributes": event.attributes,
                }
                for event in self._traces
            ],
        }
