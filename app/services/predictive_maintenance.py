from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenanceSignals:
    vibration_rms: float = 0.0
    battery_soh_percent: float = 100.0
    thermal_cycles: int = 0
    fan_rpm_ratio: float = 1.0
    storage_wear_percent: float = 0.0
    sensor_drift_score: float = 0.0
    actuator_error_ratio: float = 0.0


@dataclass(frozen=True)
class MaintenanceAssessment:
    risk_score: float
    recommended_action: str


class PredictiveMaintenance:
    """Transparent weighted health score; ML predictors can plug in later."""

    def assess(self, signals: MaintenanceSignals) -> MaintenanceAssessment:
        battery_penalty=max(0.0, 100.0-signals.battery_soh_percent)/100.0
        fan_penalty=max(0.0, 1.0-signals.fan_rpm_ratio)
        score=(
            min(max(signals.vibration_rms/10.0,0.0),1.0)*0.20 +
            min(battery_penalty,1.0)*0.20 +
            min(max(signals.thermal_cycles/1000.0,0.0),1.0)*0.10 +
            min(fan_penalty,1.0)*0.10 +
            min(max(signals.storage_wear_percent/100.0,0.0),1.0)*0.10 +
            min(max(signals.sensor_drift_score,0.0),1.0)*0.15 +
            min(max(signals.actuator_error_ratio,0.0),1.0)*0.15
        )
        if score >= 0.7:
            action="service_now"
        elif score >= 0.4:
            action="schedule_service"
        else:
            action="monitor"
        return MaintenanceAssessment(round(score,6), action)
