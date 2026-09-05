from pathlib import Path


def test_production_registry_bootstrap_is_wired():
    main = Path("app/main.py").read_text()
    source = Path("app/services/registry_bootstrap.py").read_text()
    assert "bootstrap_registry" in main
    assert "app.state.registry_bootstrap" in main
    assert "parse_registry_bootstrap" in source
    assert "validate_registry_bootstrap" in source
    assert "upsert_organization" in source
    assert "upsert_system" in source
    assert "add_dependency" in source


def test_production_readiness_checks_public_url_and_bootstrap():
    source = Path("app/core/hardening.py").read_text()
    assert 'add("public_base_url"' in source
    assert 'add("registry_bootstrap"' in source
    assert "production_require_public_base_url" in source
    assert "registry_bootstrap_json" in source


def test_environment_template_contains_required_production_wiring():
    env = Path(".env.example").read_text()
    for key in (
        "DATABASE_URL=postgresql+asyncpg://",
        "IAM_BASE_URL=https://",
        "DATA_RELAY_BASE_URL=https://",
        "PUBLIC_BASE_URL=https://",
        "REGISTRY_BOOTSTRAP_ENABLED=true",
        "REGISTRY_BOOTSTRAP_STRICT=true",
        "REGISTRY_BOOTSTRAP_JSON=",
    ):
        assert key in env


def test_bootstrap_rejects_unsafe_catalog_shapes():
    source = Path("app/services/registry_bootstrap.py").read_text()
    assert "must use HTTPS in production" in source
    assert "references unknown organization" in source
    assert "cannot depend on itself" in source
    assert "is not in systems catalog" in source
