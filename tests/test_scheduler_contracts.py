from datetime import datetime, timezone


def test_job_contract_shape():
    job = {
        "action": "config.rollback",
        "target_type": "configuration",
        "target_id": "global:feature_flag:3",
        "system_key": "UNG-NEMSIS",
        "correlation_id": "corr-001",
        "approval_request_id": "approval-001",
        "payload": {"scope": "global"},
        "scheduled_for": datetime.now(timezone.utc).isoformat(),
        "max_attempts": 3,
        "retry_delay_seconds": 30,
    }
    assert job["max_attempts"] >= 1
    assert job["system_key"] == "UNG-NEMSIS"
    assert job["approval_request_id"]


def test_job_states_include_retry_and_cancel():
    states = {"queued", "scheduled", "running", "retry_wait", "succeeded", "failed", "cancelled"}
    assert {"retry_wait", "cancelled", "succeeded", "failed"}.issubset(states)
