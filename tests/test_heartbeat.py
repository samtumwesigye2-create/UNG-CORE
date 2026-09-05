from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from app.services.heartbeat import classify_health


def service(enabled=True):
    return SimpleNamespace(service_key="UNG-IAM", enabled=enabled)


def heartbeat(age_seconds=0, reported_status="healthy"):
    return SimpleNamespace(
        reported_status=reported_status,
        latency_ms=25,
        details_json='{"ok": true}',
        last_seen_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
    )


def test_health_states():
    assert classify_health(service(), heartbeat(10))["state"] == "healthy"
    assert classify_health(service(), heartbeat(100))["state"] == "degraded"
    assert classify_health(service(), heartbeat(200))["state"] == "offline"
    assert classify_health(service(), heartbeat(10, "degraded"))["state"] == "degraded"
    assert classify_health(service(), None)["state"] == "unknown"
    assert classify_health(service(False), heartbeat(10))["state"] == "disabled"
