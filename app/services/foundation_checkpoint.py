from __future__ import annotations

import asyncio
from contextlib import suppress

from app.db.session import SessionLocal
from app.services.fault_supervisor import FaultSeverity
from app.services.foundation_persistence import load_state, save_state
from app.services.foundation_runtime import FoundationRuntime, foundation_runtime

CHECKPOINT_NAMESPACE = "foundation-runtime"
CHECKPOINT_KEY = "core"


def serialize_runtime(runtime: FoundationRuntime) -> dict:
    faults = runtime.faults.snapshot()["faults"]
    return {
        "map_version": runtime.geospatial.map_version,
        "hmi": runtime.hmi.view(),
        "faults": faults,
        "ota": {
            "platform_id": runtime.ota.platform_id,
            "current_version": runtime.ota.current_version,
            "state": runtime.ota.state.value,
            "previous_version": runtime.ota.previous_version,
            "staged_version": runtime.ota.staged_manifest.version if runtime.ota.staged_manifest else None,
        },
        "observability": runtime.observability.snapshot(),
    }


def hydrate_runtime(runtime: FoundationRuntime, payload: dict | None) -> bool:
    if not payload:
        return False

    map_version = payload.get("map_version")
    if map_version and map_version != "unset":
        runtime.geospatial.set_map_version(map_version)

    for item in payload.get("faults", []):
        severity_name = str(item.get("severity", "info")).upper()
        severity = getattr(FaultSeverity, severity_name, FaultSeverity.INFO)
        runtime.faults.report(
            str(item.get("component", "unknown")),
            str(item.get("code", "UNKNOWN")),
            severity,
            str(item.get("message", "")),
        )

    mode = runtime.faults.system_mode()
    runtime.hmi.set_system_mode(mode)

    ota = payload.get("ota") or {}
    if ota.get("current_version"):
        runtime.ota.current_version = str(ota["current_version"])
    if ota.get("previous_version") is not None:
        runtime.ota.previous_version = str(ota["previous_version"])

    observability = payload.get("observability") or {}
    for name, value in (observability.get("gauges") or {}).items():
        runtime.observability.gauge(str(name), float(value))
    for name, value in (observability.get("counters") or {}).items():
        runtime.observability.increment(str(name), int(value))

    return True


async def checkpoint_runtime(runtime: FoundationRuntime = foundation_runtime, *, updated_by: str = "system") -> None:
    async with SessionLocal() as db:
        await save_state(db, CHECKPOINT_NAMESPACE, CHECKPOINT_KEY, serialize_runtime(runtime), updated_by)


async def hydrate_runtime_from_db(runtime: FoundationRuntime = foundation_runtime) -> bool:
    async with SessionLocal() as db:
        payload = await load_state(db, CHECKPOINT_NAMESPACE, CHECKPOINT_KEY)
    return hydrate_runtime(runtime, payload)


async def checkpoint_loop(interval_seconds: int, runtime: FoundationRuntime = foundation_runtime) -> None:
    delay = max(5, int(interval_seconds))
    while True:
        await asyncio.sleep(delay)
        with suppress(Exception):
            await checkpoint_runtime(runtime)
