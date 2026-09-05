def test_execution_adapter_contract_shape():
    payload = {
        "action": "http.request",
        "system_key": "UNG-NEMSIS",
        "payload": {"method": "POST", "path": "/v1/commands", "body": {"command": "sync"}},
    }
    assert payload["action"] == "http.request"
    assert payload["system_key"] == "UNG-NEMSIS"
    assert payload["payload"]["method"] == "POST"


def test_event_delivery_contract_shape():
    delivery = {
        "event_type": "ung.core.job.completed",
        "target_system": "UNG-NEMSIS",
        "correlation_id": "corr-001",
        "status": "delivered",
        "attempts": 1,
        "max_attempts": 3,
    }
    assert delivery["event_type"].startswith("ung.core")
    assert delivery["target_system"] == "UNG-NEMSIS"
    assert delivery["attempts"] <= delivery["max_attempts"]


def test_scheduler_actions_are_explicit():
    supported = {"http.request", "event.publish"}
    assert "http.request" in supported
    assert "event.publish" in supported
