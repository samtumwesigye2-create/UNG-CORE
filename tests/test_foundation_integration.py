from app.services.fault_supervisor import FaultSeverity
from app.services.foundation_runtime import build_foundation_runtime
from app.services.time_sync import ClockSample


def test_runtime_health_snapshot_has_foundation_sections():
    runtime = build_foundation_runtime()
    snapshot = runtime.health_snapshot()
    assert {"clock", "faults", "observability", "event_bus", "map_version"} <= set(snapshot)


def test_faults_drive_system_mode():
    runtime = build_foundation_runtime()
    runtime.faults.report("sensor", "NO_DATA", FaultSeverity.CRITICAL)
    runtime.hmi.set_system_mode(runtime.faults.system_mode())
    assert runtime.health_snapshot()["faults"]["mode"] == "safe_degraded"
    assert runtime.hmi.view()["system_mode"] == "safe_degraded"


def test_time_sync_and_observability_can_be_combined():
    runtime = build_foundation_runtime()
    status = runtime.time_sync.update(ClockSample(source="ptp", source_time_ns=1_000_000, received_monotonic_ns=10_000_000, uncertainty_ns=100), local_wall_time_ns=1_000_000)
    runtime.observability.gauge("clock_offset_ns", status.offset_ns)
    assert runtime.health_snapshot()["observability"]["gauges"]["clock_offset_ns"] == 0.0
