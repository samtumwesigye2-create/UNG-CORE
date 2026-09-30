from app.services.fault_supervisor import FaultSeverity
from app.services.foundation_checkpoint import hydrate_runtime, serialize_runtime
from app.services.foundation_runtime import build_foundation_runtime


def test_checkpoint_round_trip_restores_faults_map_hmi_and_metrics():
    source = build_foundation_runtime()
    source.geospatial.set_map_version("map-v7")
    source.faults.report("camera", "NO_FRAMES", FaultSeverity.DEGRADED, "stale stream")
    source.hmi.set_system_mode(source.faults.system_mode())
    source.observability.gauge("gpu_temp_c", 72.5)
    source.observability.increment("frames", 42)
    source.ota.current_version = "2.4.0"

    payload = serialize_runtime(source)
    target = build_foundation_runtime()
    assert hydrate_runtime(target, payload)

    assert target.geospatial.map_version == "map-v7"
    assert target.faults.system_mode() == "degraded"
    assert target.hmi.view()["system_mode"] == "degraded"
    assert target.observability.snapshot()["gauges"]["gpu_temp_c"] == 72.5
    assert target.observability.snapshot()["counters"]["frames"] == 42
    assert target.ota.current_version == "2.4.0"


def test_hydrate_empty_payload_is_noop():
    runtime = build_foundation_runtime()
    assert hydrate_runtime(runtime, None) is False
