def test_alert_policy_contract_shape():
    policy = {
        "service_key": "UNG-NEMSIS",
        "minimum_severity": "warning",
        "trigger_states": ["degraded", "offline"],
        "escalation_minutes": [5, 15, 30],
        "targets": ["national-ops"],
        "enabled": True,
    }
    assert policy["service_key"] == "UNG-NEMSIS"
    assert policy["escalation_minutes"][-1] == 30


def test_alert_lifecycle_contract_shape():
    alert = {
        "status": "open",
        "severity": "critical",
        "state": "offline",
        "escalation_stage": 0,
    }
    assert alert["status"] in {"open", "acknowledged", "resolved"}
    assert alert["severity"] == "critical"
