from __future__ import annotations

from app.core.hardening import production_readiness
from app.services.api_policy import RequestContext
from app.services.foundation_adapters import adapter_profile
from app.services.foundation_checkpoint import hydrate_runtime, serialize_runtime
from app.services.foundation_runtime import FoundationRuntime, build_foundation_runtime
from app.services.ota_manager import OtaRollbackManager, UpdateManifest, UpdateState


def foundation_acceptance_report(runtime: FoundationRuntime) -> dict:
    checks: list[dict] = []

    def add(key: str, ok: bool, detail: str) -> None:
        checks.append({"key": key, "ok": bool(ok), "detail": detail})

    snapshot = runtime.health_snapshot()
    add("runtime.status", "faults" in snapshot and "observability" in snapshot, "foundation health snapshot is available")

    cloned = build_foundation_runtime()
    payload = serialize_runtime(runtime)
    restored = hydrate_runtime(cloned, payload)
    add("restart.hydration", restored, "restart-safe state can be serialized and hydrated")

    probe = build_foundation_runtime()
    probe.observability.increment("acceptance_probe")
    add("observability.counter", probe.observability.snapshot()["counters"].get("acceptance_probe", 0) >= 1, "observability counter path is operational")

    probe.api_policy.allow_roles("/acceptance", {"admin"})
    decision = probe.api_policy.evaluate(RequestContext("acceptance-service", "admin", "/acceptance", 1, "acceptance-trace"), now=1.0)
    add("api_policy.authorization", decision.allowed, "service identity/RBAC policy accepted an authorized request")

    profile = adapter_profile("NEXUS")
    add("adapter.contract", "schemas" in profile.capabilities and bool(profile.read_endpoints), "cross-system adapter contract is available")

    ota = OtaRollbackManager("acceptance", "1.0.0")
    artifact = b"acceptance-release"
    manifest = UpdateManifest("2.0.0", ota.sha256(artifact), ("acceptance",))
    staged = ota.stage(manifest, artifact, signature_verified=True) is UpdateState.STAGED
    if staged:
        ota.mark_reboot_pending(); ota.begin_boot_verification(); ota.complete_boot_verification(healthy=False)
    add("ota.rollback", staged and ota.state is UpdateState.ROLLED_BACK and ota.current_version == "1.0.0", "failed boot health rolls back to previous version")

    prod = production_readiness()
    add("production.readiness_contract", isinstance(prod.get("ready"), bool), "production readiness gate returns a boolean decision")

    failed = [item for item in checks if not item["ok"]]
    return {"ready": not failed, "checks": checks, "failed_checks": len(failed)}
