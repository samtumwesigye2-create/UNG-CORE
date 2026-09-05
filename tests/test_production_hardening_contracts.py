from app.core.hardening import production_readiness


def test_readiness_contract_shape():
    result = production_readiness()
    assert set(result) == {"ready", "environment", "checks", "failed_checks"}
    assert isinstance(result["checks"], list)
    assert all(set(item) == {"key", "ok", "detail"} for item in result["checks"])


def test_readiness_contains_runtime_guards():
    keys = {item["key"] for item in production_readiness()["checks"]}
    assert "database" in keys
    assert "dependency.iam.https" in keys
    assert "dependency.data_relay.https" in keys
    assert "request_body_limit" in keys
    assert "request_timeout" in keys
    assert "scheduler_interval" in keys
