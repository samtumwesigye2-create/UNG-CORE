from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class CheckState(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class SensorCheck:
    name: str
    state: CheckState
    detail: str = ""


@dataclass(frozen=True)
class SensorHealth:
    sensor_id: str
    checks: tuple[SensorCheck, ...]

    @property
    def state(self) -> CheckState:
        states={check.state for check in self.checks}
        if CheckState.FAIL in states:
            return CheckState.FAIL
        if CheckState.WARN in states:
            return CheckState.WARN
        return CheckState.PASS


class SensorSelfTestFramework:
    def __init__(self) -> None:
        self._checks: dict[str, list[tuple[str, Callable[[], SensorCheck]]]] = {}

    def register_check(self, sensor_id: str, name: str, check: Callable[[], SensorCheck]) -> None:
        self._checks.setdefault(sensor_id, []).append((name, check))

    def run(self, sensor_id: str) -> SensorHealth:
        results: list[SensorCheck]=[]
        for name, check in self._checks.get(sensor_id, []):
            try:
                result=check()
                if result.name != name:
                    result=SensorCheck(name, result.state, result.detail)
            except Exception as exc:
                result=SensorCheck(name, CheckState.FAIL, f"{type(exc).__name__}: {exc}")
            results.append(result)
        return SensorHealth(sensor_id=sensor_id, checks=tuple(results))
