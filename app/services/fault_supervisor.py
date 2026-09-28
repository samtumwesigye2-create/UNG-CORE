from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import time


class FaultSeverity(IntEnum):
    INFO = 10
    DEGRADED = 20
    CRITICAL = 30


@dataclass(frozen=True)
class Fault:
    component: str
    code: str
    severity: FaultSeverity
    detected_monotonic_ns: int
    message: str


class FaultSupervisor:
    """Centralized fault state and degraded-mode policy evaluator."""

    def __init__(self) -> None:
        self._faults: dict[tuple[str, str], Fault] = {}
        self._dependencies: dict[str, set[str]] = {}

    def set_dependencies(self, component: str, dependencies: set[str]) -> None:
        if component in dependencies:
            raise ValueError("component cannot depend on itself")
        self._dependencies[component] = set(dependencies)

    def report(self, component: str, code: str, severity: FaultSeverity, message: str = "") -> Fault:
        fault = Fault(
            component=component,
            code=code,
            severity=FaultSeverity(severity),
            detected_monotonic_ns=time.monotonic_ns(),
            message=message,
        )
        self._faults[(component, code)] = fault
        return fault

    def clear(self, component: str, code: str) -> bool:
        return self._faults.pop((component, code), None) is not None

    def component_state(self, component: str) -> str:
        own = [f.severity for f in self._faults.values() if f.component == component]
        deps = self._dependencies.get(component, set())
        dep_faults = [f.severity for f in self._faults.values() if f.component in deps]
        highest = max(own + dep_faults, default=FaultSeverity.INFO)
        if highest >= FaultSeverity.CRITICAL:
            return "unavailable"
        if highest >= FaultSeverity.DEGRADED:
            return "degraded"
        return "healthy"

    def system_mode(self) -> str:
        severities = [fault.severity for fault in self._faults.values()]
        if any(level >= FaultSeverity.CRITICAL for level in severities):
            return "safe_degraded"
        if any(level >= FaultSeverity.DEGRADED for level in severities):
            return "degraded"
        return "nominal"

    def snapshot(self) -> dict:
        return {
            "mode": self.system_mode(),
            "faults": [
                {
                    "component": f.component,
                    "code": f.code,
                    "severity": f.severity.name.lower(),
                    "message": f.message,
                    "detected_monotonic_ns": f.detected_monotonic_ns,
                }
                for f in sorted(self._faults.values(), key=lambda x: (x.component, x.code))
            ],
        }
