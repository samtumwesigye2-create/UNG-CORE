from __future__ import annotations

from dataclasses import dataclass

from app.services.api_policy import APIPolicyEngine
from app.services.calibration_registry import CalibrationRegistry
from app.services.device_identity import DeviceIdentityRegistry
from app.services.disaster_recovery import DisasterRecoveryManager
from app.services.event_bus import EventBus
from app.services.fault_supervisor import FaultSupervisor
from app.services.fleet_management import FleetManager
from app.services.geospatial import GeospatialService
from app.services.hmi_state import HMIState
from app.services.mlops_lifecycle import MLOpsLifecycle
from app.services.mission_workflow import MissionWorkflowEngine
from app.services.observability import UnifiedObservability
from app.services.ota_manager import OtaRollbackManager
from app.services.predictive_maintenance import PredictiveMaintenance
from app.services.replay_forensics import ReplayRecorder
from app.services.resource_scheduler import ResourceBudget, ResourceScheduler
from app.services.scenario_orchestrator import ScenarioOrchestrator
from app.services.schema_registry import SchemaRegistry
from app.services.sensor_self_test import SensorSelfTestFramework
from app.services.storage_lifecycle import StorageLifecycleManager
from app.services.time_sync import TimeSyncMonitor


@dataclass
class FoundationRuntime:
    time_sync: TimeSyncMonitor
    observability: UnifiedObservability
    calibration: CalibrationRegistry
    faults: FaultSupervisor
    ota: OtaRollbackManager
    device_identity: DeviceIdentityRegistry
    mlops: MLOpsLifecycle
    sensor_self_test: SensorSelfTestFramework
    resource_scheduler: ResourceScheduler
    schemas: SchemaRegistry
    event_bus: EventBus
    replay: ReplayRecorder
    scenarios: ScenarioOrchestrator
    storage: StorageLifecycleManager
    fleet: FleetManager
    maintenance: PredictiveMaintenance
    workflows: MissionWorkflowEngine
    geospatial: GeospatialService
    hmi: HMIState
    api_policy: APIPolicyEngine
    disaster_recovery: DisasterRecoveryManager

    def health_snapshot(self) -> dict:
        clock = self.time_sync.status()
        fault_snapshot = self.faults.snapshot()
        obs = self.observability.snapshot()
        return {
            "clock": {
                "source": clock.source,
                "quality": clock.quality.value,
                "offset_ns": clock.offset_ns,
                "drift_ppm": clock.drift_ppm,
                "uncertainty_ns": clock.uncertainty_ns,
                "age_ms": clock.age_ms,
            },
            "faults": fault_snapshot,
            "observability": {
                "counters": obs["counters"],
                "gauges": obs["gauges"],
                "latency": obs["latency"],
            },
            "event_bus": {"dropped_events": self.event_bus.dropped_events},
            "map_version": self.geospatial.map_version,
        }


def build_foundation_runtime() -> FoundationRuntime:
    return FoundationRuntime(
        time_sync=TimeSyncMonitor(),
        observability=UnifiedObservability(),
        calibration=CalibrationRegistry(),
        faults=FaultSupervisor(),
        ota=OtaRollbackManager("ung-core", "current"),
        device_identity=DeviceIdentityRegistry(),
        mlops=MLOpsLifecycle(),
        sensor_self_test=SensorSelfTestFramework(),
        resource_scheduler=ResourceScheduler(ResourceBudget(cpu=1.0, gpu=0.0, npu=0.0, fpga=0.0, memory_mb=1024, bandwidth_mbps=100.0)),
        schemas=SchemaRegistry(),
        event_bus=EventBus(),
        replay=ReplayRecorder(),
        scenarios=ScenarioOrchestrator(),
        storage=StorageLifecycleManager(),
        fleet=FleetManager(),
        maintenance=PredictiveMaintenance(),
        workflows=MissionWorkflowEngine(),
        geospatial=GeospatialService(),
        hmi=HMIState(),
        api_policy=APIPolicyEngine(),
        disaster_recovery=DisasterRecoveryManager(),
    )


foundation_runtime = build_foundation_runtime()
