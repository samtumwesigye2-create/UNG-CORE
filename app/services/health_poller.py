import asyncio
import time
from contextlib import suppress

import httpx

from app.db.session import SessionLocal
from app.schemas.heartbeat import HeartbeatIn
from app.services.heartbeat import record_heartbeat
from app.services.registry import list_services


async def poll_service(client: httpx.AsyncClient, service) -> None:
    url = f"{service.base_url.rstrip('/')}{service.health_path}"
    started = time.perf_counter()
    status = "offline"
    details: dict = {"probe": "active", "url": url}
    try:
        response = await client.get(url)
        latency_ms = int((time.perf_counter() - started) * 1000)
        details["http_status"] = response.status_code
        if 200 <= response.status_code < 300:
            status = "healthy"
            with suppress(Exception):
                payload = response.json()
                details["response"] = payload
                if isinstance(payload, dict) and str(payload.get("status", "")).lower() in {"degraded", "warning"}:
                    status = "degraded"
        elif response.status_code < 500:
            status = "degraded"
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        details["error"] = type(exc).__name__

    async with SessionLocal() as db:
        await record_heartbeat(db, service.service_key, HeartbeatIn(status=status, latency_ms=latency_ms, details=details))


async def poll_once() -> None:
    async with SessionLocal() as db:
        services = await list_services(db, enabled_only=True)
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        await asyncio.gather(*(poll_service(client, service) for service in services), return_exceptions=True)


async def health_poll_loop(interval_seconds: int) -> None:
    while True:
        await poll_once()
        await asyncio.sleep(interval_seconds)
