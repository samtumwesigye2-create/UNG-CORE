from pathlib import Path


def test_operator_dashboard_is_permission_aware():
    source = Path("app/api/operator_routes.py").read_text()
    assert '@router.get("/dashboard")' in source
    for permission in (
        "ung.core.incidents.read",
        "ung.core.approvals.read",
        "ung.core.jobs.read",
        "ung.core.audit.read",
        "ung.core.recovery.write",
    ):
        assert permission in source
    for summary in (
        "fleet_health_summary",
        "alert_summary",
        "incident_summary",
        "approval_summary",
        "job_summary",
        "audit_summary",
        "command_summary",
        "delivery_summary",
        "resilience_summary",
        "production_readiness",
    ):
        assert summary in source


def test_control_center_uses_operator_workspace_and_dashboard():
    source = Path("app/api/control_center_routes.py").read_text()
    assert "/v1/operator/workspace" in source
    assert "/v1/operator/dashboard" in source
    assert "/v1/control-center/topology" in source
    assert "setInterval(loadAll,30000)" in source


def test_control_center_has_launcher_search_and_operations_sections():
    source = Path("app/api/control_center_routes.py").read_text()
    for marker in (
        "Systems & Launchpad",
        "systemSearch",
        "Open system",
        "Operations",
        "Governance & Delivery",
        "Production Readiness",
        "Recovery & Resilience",
        "Ecosystem Topology",
    ):
        assert marker in source
    assert "noopener noreferrer" in source
    assert "data-cap='approvals'" in source
    assert "data-cap='audit'" in source
    assert "data-cap='recovery'" in source


def test_control_center_handles_auth_and_role_boundaries():
    source = Path("app/api/control_center_routes.py").read_text()
    assert "AUTH_REQUIRED" in source
    assert "FORBIDDEN" in source
    assert "applyNavigation" in source
    assert "Recovery controls are not available for this role." in source
