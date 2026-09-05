from urllib.parse import urlparse

from app.core.config import settings


def production_readiness() -> dict:
    checks: list[dict] = []

    def add(key: str, ok: bool, detail: str):
        checks.append({"key": key, "ok": ok, "detail": detail})

    production = settings.environment.lower() == "production"
    database_ok = not production or not settings.production_require_postgres or settings.database_url.startswith(("postgresql+", "postgres+"))
    add("database", database_ok, "PostgreSQL required in production" if not database_ok else "database configuration accepted")

    dependency_urls = {"iam": settings.iam_base_url, "data_relay": settings.data_relay_base_url}
    for name, value in dependency_urls.items():
        scheme = urlparse(value).scheme.lower()
        ok = not production or not settings.production_require_https_dependencies or scheme == "https"
        add(f"dependency.{name}.https", ok, f"{name} must use HTTPS in production" if not ok else f"{name} transport accepted")

    public_scheme = urlparse(settings.public_base_url).scheme.lower() if settings.public_base_url else ""
    public_ok = not production or not settings.production_require_public_base_url or public_scheme == "https"
    add("public_base_url", public_ok, "PUBLIC_BASE_URL must be configured with HTTPS in production" if not public_ok else "public base URL accepted")

    bootstrap_ok = not production or not settings.registry_bootstrap_enabled or bool(settings.registry_bootstrap_json.strip())
    add("registry_bootstrap", bootstrap_ok, "REGISTRY_BOOTSTRAP_JSON is required when production bootstrap is enabled" if not bootstrap_ok else "registry bootstrap configuration accepted")

    add("request_body_limit", settings.request_body_limit_bytes > 0, "request body limit must be positive")
    add("request_timeout", settings.request_timeout_seconds > 0, "request timeout must be positive")
    add("scheduler_interval", (not settings.scheduler_enabled) or settings.scheduler_interval_seconds >= 1, "scheduler interval must be at least one second")

    failed = [item for item in checks if not item["ok"]]
    return {"ready": not failed, "environment": settings.environment, "checks": checks, "failed_checks": len(failed)}
