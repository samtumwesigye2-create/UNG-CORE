import json

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_registry import RegisteredService
from app.services.event_delivery import publish_event


async def execute_adapter(db: AsyncSession, *, action: str, system_key: str | None, payload: dict, correlation_id: str | None, job_id: str) -> dict:
    if action == "event.publish":
        target = system_key or payload.get("target_system")
        if not target:
            raise ValueError("target system is required for event.publish")
        event_type = payload.get("event_type") or "ung.core.job.completed"
        data = payload.get("data") or payload
        delivery = await publish_event(db, event_type=event_type, target_system=target, payload=data, correlation_id=correlation_id, job_id=job_id)
        return {"adapter": "event.publish", "delivery_id": delivery.delivery_id, "delivery_status": delivery.status}

    if action == "http.request":
        if not system_key:
            raise ValueError("system_key is required for http.request")
        service = await db.scalar(select(RegisteredService).where(RegisteredService.service_key == system_key.upper(), RegisteredService.enabled.is_(True)))
        if service is None:
            raise LookupError(f"registered target system not found: {system_key}")
        method = str(payload.get("method", "POST")).upper()
        path = str(payload.get("path", "/")).strip()
        if not path.startswith("/"):
            path = "/" + path
        url = service.base_url.rstrip("/") + path
        headers = {"X-UNG-Job-ID": job_id}
        if correlation_id:
            headers["X-UNG-Correlation-ID"] = correlation_id
        async with httpx.AsyncClient(timeout=float(payload.get("timeout_seconds", 15))) as client:
            response = await client.request(method, url, json=payload.get("body"), params=payload.get("query"), headers=headers)
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"target returned HTTP {response.status_code}")
        try:
            body = response.json()
        except Exception:
            body = {"text": response.text[:2000]}
        return {"adapter": "http.request", "status_code": response.status_code, "response": body}

    raise ValueError(f"unsupported execution action: {action}")
