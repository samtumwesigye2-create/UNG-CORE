import json
from urllib.parse import urlparse

from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas.control_plane import DependencyIn, OrganizationIn, SystemIn
from app.services.control_plane import add_dependency, upsert_organization, upsert_system


def parse_registry_bootstrap() -> dict:
    raw = settings.registry_bootstrap_json.strip()
    if not raw:
        return {"organizations": [], "systems": [], "dependencies": []}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("REGISTRY_BOOTSTRAP_JSON must be a JSON object")
    organizations = payload.get("organizations", [])
    systems = payload.get("systems", [])
    dependencies = payload.get("dependencies", [])
    if not all(isinstance(item, list) for item in (organizations, systems, dependencies)):
        raise ValueError("registry bootstrap organizations/systems/dependencies must be arrays")
    return {"organizations": organizations, "systems": systems, "dependencies": dependencies}


def validate_registry_bootstrap(payload: dict) -> list[str]:
    errors: list[str] = []
    organization_keys = {str(item.get("organization_key", "")).upper() for item in payload["organizations"]}
    system_keys = {str(item.get("system_key", "")).upper() for item in payload["systems"]}
    for item in payload["systems"]:
        key = str(item.get("system_key", "")).upper()
        owner = str(item.get("owner_organization_key", "")).upper()
        base_url = item.get("base_url")
        if not key:
            errors.append("system_key is required")
        if owner not in organization_keys:
            errors.append(f"system {key or '<unknown>'} references unknown organization {owner or '<missing>'}")
        if base_url:
            scheme = urlparse(str(base_url)).scheme.lower()
            if settings.environment.lower() == "production" and scheme != "https":
                errors.append(f"system {key} base_url must use HTTPS in production")
    for item in payload["dependencies"]:
        source = str(item.get("system_key", "")).upper()
        target = str(item.get("depends_on_system_key", "")).upper()
        if source not in system_keys:
            errors.append(f"dependency source {source or '<missing>'} is not in systems catalog")
        if target not in system_keys:
            errors.append(f"dependency target {target or '<missing>'} is not in systems catalog")
        if source and source == target:
            errors.append(f"system {source} cannot depend on itself")
    return errors


async def bootstrap_registry() -> dict:
    if not settings.registry_bootstrap_enabled:
        return {"enabled": False, "applied": False, "organizations": 0, "systems": 0, "dependencies": 0}
    payload = parse_registry_bootstrap()
    errors = validate_registry_bootstrap(payload)
    if errors and settings.registry_bootstrap_strict:
        raise RuntimeError("registry bootstrap validation failed: " + "; ".join(errors))
    async with SessionLocal() as db:
        for item in payload["organizations"]:
            await upsert_organization(db, OrganizationIn(**item))
        for item in payload["systems"]:
            await upsert_system(db, SystemIn(**item))
        for item in payload["dependencies"]:
            await add_dependency(db, item["system_key"], DependencyIn(
                depends_on_system_key=item["depends_on_system_key"],
                dependency_type=item.get("dependency_type", "runtime"),
                required=item.get("required", True),
            ))
    return {
        "enabled": True,
        "applied": True,
        "organizations": len(payload["organizations"]),
        "systems": len(payload["systems"]),
        "dependencies": len(payload["dependencies"]),
        "validation_errors": errors,
    }
