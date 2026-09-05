import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security_resilience import CircuitState, DeadLetter, IdempotencyRecord, ServiceCredential


def _utcnow():
    return datetime.now(timezone.utc)


def serialize_credential(row: ServiceCredential) -> dict:
    return {"credential_id": row.credential_id, "credential_key": row.credential_key, "system_key": row.system_key, "auth_type": row.auth_type, "secret_env_var": row.secret_env_var, "header_name": row.header_name, "prefix": row.prefix, "enabled": row.enabled, "created_at": row.created_at, "updated_at": row.updated_at}


async def upsert_credential(db: AsyncSession, credential_key: str, *, system_key: str, auth_type: str, secret_env_var: str, header_name: str, prefix: str, enabled: bool):
    row = await db.scalar(select(ServiceCredential).where(ServiceCredential.credential_key == credential_key))
    if row is None:
        row = ServiceCredential(credential_key=credential_key)
        db.add(row)
    row.system_key = system_key.upper(); row.auth_type = auth_type; row.secret_env_var = secret_env_var
    row.header_name = header_name; row.prefix = prefix; row.enabled = enabled
    await db.commit(); await db.refresh(row); return row


async def list_credentials(db: AsyncSession):
    return list((await db.scalars(select(ServiceCredential).order_by(ServiceCredential.system_key, ServiceCredential.credential_key))).all())


async def credential_headers(db: AsyncSession, system_key: str) -> dict[str, str]:
    row = await db.scalar(select(ServiceCredential).where(ServiceCredential.system_key == system_key.upper(), ServiceCredential.enabled.is_(True)).order_by(ServiceCredential.updated_at.desc()))
    if row is None:
        return {}
    secret = os.getenv(row.secret_env_var)
    if not secret:
        raise RuntimeError(f"credential environment variable is not configured: {row.secret_env_var}")
    return {row.header_name: f"{row.prefix}{secret}"}


async def begin_idempotent(db: AsyncSession, key: str, action: str):
    row = await db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key))
    if row is not None:
        return row, False
    row = IdempotencyRecord(idempotency_key=key, action=action)
    db.add(row); await db.commit(); await db.refresh(row); return row, True


async def complete_idempotent(db: AsyncSession, row: IdempotencyRecord, result: dict):
    row.status = "completed"; row.result_json = json.dumps(result, separators=(",", ":"), sort_keys=True); row.completed_at = _utcnow()
    await db.commit(); await db.refresh(row); return row


async def get_circuit(db: AsyncSession, system_key: str):
    key = system_key.upper()
    row = await db.scalar(select(CircuitState).where(CircuitState.system_key == key))
    if row is None:
        row = CircuitState(system_key=key); db.add(row); await db.commit(); await db.refresh(row)
    if row.state == "open" and row.opened_at and _utcnow() >= row.opened_at + timedelta(seconds=row.retry_after_seconds):
        row.state = "half_open"; await db.commit(); await db.refresh(row)
    return row


async def assert_circuit_allows(db: AsyncSession, system_key: str):
    row = await get_circuit(db, system_key)
    if row.state == "open":
        raise RuntimeError(f"circuit open for {row.system_key}")
    return row


async def record_circuit_success(db: AsyncSession, system_key: str):
    row = await get_circuit(db, system_key); row.state = "closed"; row.consecutive_failures = 0; row.opened_at = None
    await db.commit(); return row


async def record_circuit_failure(db: AsyncSession, system_key: str):
    row = await get_circuit(db, system_key); row.consecutive_failures += 1
    if row.consecutive_failures >= row.failure_threshold:
        row.state = "open"; row.opened_at = _utcnow()
    await db.commit(); return row


async def dead_letter(db: AsyncSession, *, source_type: str, source_id: str, system_key: str | None, action: str, payload: dict, error: str | None):
    row = DeadLetter(source_type=source_type, source_id=source_id, system_key=system_key.upper() if system_key else None, action=action, payload_json=json.dumps(payload, separators=(",", ":"), sort_keys=True), error=error)
    db.add(row); await db.commit(); await db.refresh(row); return row


def serialize_dead_letter(row: DeadLetter):
    return {"dead_letter_id": row.dead_letter_id, "source_type": row.source_type, "source_id": row.source_id, "system_key": row.system_key, "action": row.action, "payload": json.loads(row.payload_json or "{}"), "error": row.error, "status": row.status, "replay_count": row.replay_count, "created_at": row.created_at, "replayed_at": row.replayed_at}


async def list_dead_letters(db: AsyncSession, status: str | None = None, limit: int = 100):
    stmt = select(DeadLetter).order_by(DeadLetter.created_at.desc()).limit(limit)
    if status: stmt = stmt.where(DeadLetter.status == status)
    return list((await db.scalars(stmt)).all())


async def mark_dead_letter_replayed(db: AsyncSession, dead_letter_id: str):
    row = await db.get(DeadLetter, dead_letter_id)
    if row is None: raise LookupError(dead_letter_id)
    row.status = "replayed"; row.replay_count += 1; row.replayed_at = _utcnow()
    await db.commit(); await db.refresh(row); return row


async def resilience_summary(db: AsyncSession):
    circuits = {"open": 0, "half_open": 0, "closed": 0}
    for state, count in (await db.execute(select(CircuitState.state, func.count()).group_by(CircuitState.state))).all(): circuits[state] = count
    dead = await db.scalar(select(func.count()).select_from(DeadLetter).where(DeadLetter.status == "dead")) or 0
    creds = await db.scalar(select(func.count()).select_from(ServiceCredential).where(ServiceCredential.enabled.is_(True))) or 0
    return {"circuits": circuits, "dead_letters": dead, "active_credentials": creds}
