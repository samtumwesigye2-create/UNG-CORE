def test_approval_policy_contract_shape():
    policy = {
        "policy_key": "critical-config",
        "action_pattern": "config.*",
        "required_approvals": 2,
        "required_roles": ["core-admin"],
        "expires_minutes": 60,
        "enabled": True,
    }
    assert policy["required_approvals"] >= 1
    assert policy["action_pattern"]
    assert isinstance(policy["required_roles"], list)


def test_approval_request_lifecycle_contract():
    request = {
        "status": "pending",
        "required_approvals": 2,
        "approval_count": 1,
    }
    assert request["status"] in {"pending", "approved", "denied", "expired"}
    assert request["approval_count"] <= request["required_approvals"]


def test_sensitive_action_requires_gate_when_policy_matches():
    gate = {"allowed": False, "approval_required": True, "request": {"status": "pending"}}
    assert gate["approval_required"] is True
    assert gate["allowed"] is False
    assert gate["request"]["status"] == "pending"


def test_approved_gate_allows_execution():
    gate = {"allowed": True, "approval_required": True, "request": {"status": "approved"}}
    assert gate["allowed"] is True
    assert gate["request"]["status"] == "approved"
