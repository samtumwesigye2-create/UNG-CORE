from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class ScenarioAction(str, Enum):
    SENSOR_DROPOUT="sensor_dropout"
    NETWORK_DEGRADATION="network_degradation"
    CLOCK_DRIFT="clock_drift"
    THERMAL_STRESS="thermal_stress"
    CPU_PRESSURE="cpu_pressure"
    MALFORMED_PACKET="malformed_packet"
    CALIBRATION_FAULT="calibration_fault"


@dataclass(frozen=True)
class ScenarioStep:
    at_ms: int
    action: ScenarioAction
    parameters: dict[str, Any]


class ScenarioOrchestrator:
    """Deterministic SITL/HITL scenario plan executor."""

    def __init__(self) -> None:
        self._handlers: dict[ScenarioAction, Callable[[dict[str,Any]], None]] = {}

    def register_handler(self, action: ScenarioAction, handler: Callable[[dict[str,Any]], None]) -> None:
        self._handlers[action]=handler

    def validate(self, steps: list[ScenarioStep]) -> None:
        if any(step.at_ms < 0 for step in steps):
            raise ValueError("scenario times must be non-negative")
        if [s.at_ms for s in steps] != sorted(s.at_ms for s in steps):
            raise ValueError("scenario steps must be time ordered")

    def execute(self, steps: list[ScenarioStep]) -> list[tuple[ScenarioStep,str]]:
        self.validate(steps)
        results=[]
        for step in steps:
            handler=self._handlers.get(step.action)
            if handler is None:
                results.append((step,"unhandled"))
                continue
            handler(dict(step.parameters))
            results.append((step,"executed"))
        return results
