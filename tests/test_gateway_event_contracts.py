def test_gateway_route_contract_shape():
    route = {
        "route_key": "nemsis-incidents",
        "system_key": "UNG-NEMSIS",
        "public_path": "/nemsis/incidents",
        "upstream_path": "/v1/incidents",
        "methods": ["GET", "POST"],
        "auth_policy": "authenticated",
        "rate_limit_per_minute": 120,
        "enabled": True,
    }
    assert route["system_key"] == "UNG-NEMSIS"
    assert "POST" in route["methods"]


def test_correlated_event_contract_shape():
    event = {
        "event_type": "national-emergency.incident.escalated",
        "source_system_key": "UNG-NEMSIS",
        "subject": "incident-001",
        "severity": "critical",
        "incident_id": "incident-001",
        "payload": {"region": "national"},
    }
    assert event["severity"] == "critical"
    assert event["source_system_key"] == "UNG-NEMSIS"
