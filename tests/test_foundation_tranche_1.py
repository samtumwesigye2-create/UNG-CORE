import hashlib

from app.services.calibration_registry import CalibrationRegistry
from app.services.fault_supervisor import FaultSeverity, FaultSupervisor
from app.services.observability import UnifiedObservability
from app.services.ota_manager import OtaRollbackManager, UpdateManifest, UpdateState
from app.services.time_sync import ClockQuality, ClockSample, TimeSyncMonitor


def test_time_sync_health_degrades_on_large_offset():
    monitor = TimeSyncMonitor(max_offset_ns=1_000)
    sample = ClockSample("ptp", source_time_ns=10_000, received_monotonic_ns=1_000_000)
    status = monitor.update(sample, local_wall_time_ns=0)
    assert status.quality == ClockQuality.DEGRADED


def test_observability_snapshot_has_latency_percentiles():
    obs = UnifiedObservability()
    for value in (1.0, 2.0, 3.0, 10.0):
        obs.observe_latency_ms("sensor_to_track", value)
    obs.increment("frames")
    obs.gauge("gpu_temp_c", 71.2)
    snap = obs.snapshot()
    assert snap["counters"]["frames"] == 1
    assert snap["latency"]["sensor_to_track"]["max_ms"] == 10.0


def test_calibration_registry_is_versioned_and_activatable():
    registry = CalibrationRegistry()
    one = registry.register("imu-1", "imu_bias", {"x": 0.1})
    two = registry.register("imu-1", "imu_bias", {"x": 0.2})
    assert (one.version, two.version) == (1, 2)
    registry.activate("imu-1", "imu_bias", 2)
    assert registry.active("imu-1", "imu_bias").payload["x"] == 0.2


def test_fault_supervisor_propagates_dependency_state():
    supervisor = FaultSupervisor()
    supervisor.set_dependencies("fusion", {"time_sync"})
    supervisor.report("time_sync", "CLOCK_DRIFT", FaultSeverity.DEGRADED)
    assert supervisor.component_state("fusion") == "degraded"
    assert supervisor.system_mode() == "degraded"


def test_ota_rolls_back_on_failed_boot_health():
    artifact = b"release-2"
    manifest = UpdateManifest(
        version="2.0.0",
        artifact_sha256=hashlib.sha256(artifact).hexdigest(),
        compatible_platforms=("edge-a",),
    )
    manager = OtaRollbackManager("edge-a", "1.0.0")
    assert manager.stage(manifest, artifact, signature_verified=True) == UpdateState.STAGED
    manager.mark_reboot_pending()
    manager.begin_boot_verification()
    assert manager.complete_boot_verification(healthy=False) == UpdateState.ROLLED_BACK
    assert manager.current_version == "1.0.0"
