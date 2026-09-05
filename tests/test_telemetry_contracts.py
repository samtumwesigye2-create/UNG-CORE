def test_fleet_telemetry_contract_shape():
    summary = {
        "total": 4,
        "healthy": 2,
        "degraded": 1,
        "offline": 1,
        "unknown": 0,
        "thresholds": {"degraded_after_seconds": 90, "offline_after_seconds": 180},
    }
    assert summary["total"] == summary["healthy"] + summary["degraded"] + summary["offline"] + summary["unknown"]
    assert summary["thresholds"]["offline_after_seconds"] > summary["thresholds"]["degraded_after_seconds"]


def test_service_sla_contract_shape():
    sla = {
        "service_key": "UNG-NEMSIS",
        "window_minutes": 60,
        "samples": 120,
        "availability_pct": 99.95,
        "average_latency_ms": 84.2,
        "state": "meeting_sla",
    }
    assert sla["service_key"] == "UNG-NEMSIS"
    assert sla["availability_pct"] >= 99.9
    assert sla["state"] == "meeting_sla"
