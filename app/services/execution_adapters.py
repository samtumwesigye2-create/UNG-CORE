import json

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_registry import RegisteredService
from app.services.event_delivery import publish_event
from app.services.security_resilience import (
    assert_circuit_allows,
    begin_idempotent,
    complete_idempotent,
    credential_headers,
    dead_letter,
    record_circuit_failure,
    record_circuit_success,
)


async def execute_adapter(db: AsyncSession, *, action: str, system_key: str | None, payload: dict, correlation_id: str | None, job_id: str) -> dict:
    idempotency_key = str(payload.get("idempotency_key") or f"job:{job_id}:{action}")
    idem, created = await begin_idempotent(db, idempotency_key, action)
    if not created:
        if idem.status == "completed":
            return {"adapter": action, "idempotent_replay": True, "result": json.loads(idem.result_json or "{}")}
        raise RuntimeError(f"idempotent action already in progress: {idempotency_key}")

    try:
        if action == "event.publish":
            target = system_key or payload.get("target_system")
            if not target:
                raise ValueError("target system is required for event.publish")
            await assert_circuit_allows(db, target)
            event_type = payload.get("event_type") or "ung.core.job.completed"
            data = payload.get("data") or payload
            delivery = await publish_event(db, event_type=event_type, target_system=target, payload=data, correlation_id=correlation_id, job_id=job_id)
            result = {"adapter": "event.publish", "delivery_id": delivery.delivery_id, "delivery_status": delivery.status}
            await record_circuit_success(db, target)
            await complete_idempotent(db, idem, result)
            return result

        if action == "http.request":
            if not system_key:
                raise ValueError("system_key is required for http.request")
            await assert_circuit_allows(db, system_key)
            service = await db.scalar(select(RegisteredService).where(RegisteredService.service_key == system_key.upper(), RegisteredService.enabled.is_(True)))
            if service is None:
                raise LookupError(f"registered target system not found: {system_key}")
            method = str(payload.get("method", "POST")).upper()
            path = str(payload.get("path", "/")).strip()
            if not path.startswith("/"):
                path = "/" + path
            url = service.base_url.rstrip("/") + path
            headers = {"X-UNG-Job-ID": job_id, "Idempotency-Key": idempotency_key}
            headers.update(await credential_headers(db, system_key))
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
            result = {"adapter": "http.request", "status_code": response.status_code, "response": body}
            await record_circuit_success(db, system_key)
            await complete_idempotent(db, idem, result)
            return result

        raise ValueError(f"unsupported execution action: {action}")
    except Exception as exc:
        if system_key:
            await record_circuit_failure(db, system_key)
        await dead_letter(db, source_type="job", source_id=job_id, system_key=system_key, action=action, payload=payload, error=str(exc))
        raise
