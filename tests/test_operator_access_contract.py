from pathlib import Path


def test_operator_routes_are_wired():
    main = Path("app/main.py").read_text()
    assert "from app.api.operator_routes import router as operator_router" in main
    assert "app.include_router(operator_router)" in main


def test_operator_access_surface_exists():
    source = Path("app/api/operator_routes.py").read_text()
    for route in ("/me", "/capabilities", "/systems", "/workspace"):
        assert route in source
    assert "launchable" in source
    assert "launch_url" in source
    assert "require_permission(\"ung.core.control.read\")" in source


def test_workspace_is_permission_aware():
    source = Path("app/api/operator_routes.py").read_text()
    for permission in (
        "ung.core.admin",
        "ung.core.approvals.read",
        "ung.core.jobs.read",
        "ung.core.audit.read",
        "ung.core.config.read",
        "ung.core.recovery.write",
    ):
        assert permission in source
