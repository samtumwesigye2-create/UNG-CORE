from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum


class AlarmPriority(IntEnum):
    INFO=10
    ADVISORY=20
    WARNING=30
    CRITICAL=40


@dataclass(frozen=True)
class Alarm:
    alarm_id: str
    component: str
    message: str
    priority: AlarmPriority
    acknowledged: bool = False


class HMIState:
    """Operator-facing state model with prioritized alarms and explicit degraded mode."""

    def __init__(self) -> None:
        self._alarms: dict[str,Alarm]={}
        self._system_mode="nominal"
        self._operator_role="viewer"

    def set_system_mode(self, mode: str) -> None:
        if mode not in {"nominal","degraded","safe_degraded","maintenance"}:
            raise ValueError("unsupported system mode")
        self._system_mode=mode

    def set_operator_role(self, role: str) -> None:
        self._operator_role=role

    def raise_alarm(self, alarm: Alarm) -> Alarm:
        self._alarms[alarm.alarm_id]=alarm
        return alarm

    def acknowledge(self, alarm_id: str) -> Alarm:
        from dataclasses import replace
        current=self._alarms[alarm_id]
        updated=replace(current,acknowledged=True)
        self._alarms[alarm_id]=updated
        return updated

    def view(self) -> dict:
        alarms=sorted(self._alarms.values(), key=lambda a:(-int(a.priority),a.alarm_id))
        return {
            "system_mode":self._system_mode,
            "operator_role":self._operator_role,
            "alarms":[
                {
                    "alarm_id":a.alarm_id,
                    "component":a.component,
                    "message":a.message,
                    "priority":a.priority.name.lower(),
                    "acknowledged":a.acknowledged,
                } for a in alarms
            ],
        }
