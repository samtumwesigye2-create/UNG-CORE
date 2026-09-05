from app.core.hardening import production_readiness


def test_release_readiness_contract_is_complete():
    result = production_readiness()
    keys = {item["key"] for item in result["checks"]}
    assert {"database", "dependency.iam.https", "dependency.data_relay.https", "request_body_limit", "request_timeout", "scheduler_interval"} <= keys


def test_release_readiness_reports_boolean_gate():
    result = production_readiness()
    assert isinstance(result["ready"], bool)
    assert result["failed_checks"] == len([item for item in result["checks"] if not item["ok"]])
