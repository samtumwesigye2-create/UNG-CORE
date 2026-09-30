from app.services.foundation_acceptance import foundation_acceptance_report
from app.services.foundation_adapters import adapter_profile
from app.services.foundation_runtime import build_foundation_runtime
from app.services.fault_supervisor import FaultSeverity


def test_named_cross_system_adapter_profiles_exist():
    expected = {
        "DRACO": "calibration",
        "WAVE": "ota",
        "NEXUS": "schemas",
        "NAVSTAR": "geospatial",
        "CAD": "workflows",
    }
    for name, capability in expected.items():
        assert capability in adapter_profile(name).capabilities


def test_acceptance_report_passes_on_clean_runtime():
    runtime = build_foundation_runtime()
    runtime.geospatial.set_map_version("acceptance-map")
    report = foundation_acceptance_report(runtime)
    assert report["ready"] is True
    assert report["failed_checks"] == 0


def test_restart_round_trip_preserves_degraded_mode():
    runtime = build_foundation_runtime()
    runtime.faults.report("clock", "DRIFT", FaultSeverity.DEGRADED, "clock drift")
    runtime.hmi.set_system_mode(runtime.faults.system_mode())
    report = foundation_acceptance_report(runtime)
    assert report["ready"] is True
