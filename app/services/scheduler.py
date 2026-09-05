import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.scheduled_job import ScheduledJob
from app.services.execution_adapters import execute_adapter


def _utcnow():
    return datetime.now(timezone.utc)


def serialize_job(row: ScheduledJob) -> dict:
    return {
        "job_id": row.job_id,
        "action": row.action,
        "actor_id": row.actor_id,
        "system_key": row.system_key,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "correlation_id": row.correlation_id,
        "approval_request_id": row.approval_request_id,
        "payload": json.loads(row.payload_json or "{}"),
        "status": row.status,
        "attempts": row.attempts,
        "max_attempts": row.max_attempts,
        "retry_delay_seconds": row.retry_delay_seconds,
        "scheduled_for": row.scheduled_for,
        "next_attempt_at": row.next_attempt_at,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "last_error": row.last_error,
    }


async def enqueue_job(db: AsyncSession, *, action: str, actor_id: str, target_type: str, target_id: str | None, system_key: str | None, correlation_id: str | None, approval_request_id: str | None, payload: dict, scheduled_for: datetime | None, max_attempts: int, retry_delay_seconds: int) -> ScheduledJob:
    when = scheduled_for or _utcnow()
    row = ScheduledJob(
        job_id=str(uuid.uuid4()), action=action, actor_id=actor_id, target_type=target_type,
        target_id=target_id, system_key=system_key.upper() if system_key else None,
        correlation_id=correlation_id, approval_request_id=approval_request_id,
        payload_json=json.dumps(payload, separators=(",", ":"), sort_keys=True),
        status="scheduled" if when > _utcnow() else "queued", max_attempts=max_attempts,
        retry_delay_seconds=retry_delay_seconds, scheduled_for=when, next_attempt_at=when,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_jobs(db: AsyncSession, status: str | None = None, system_key: str | None = None, limit: int = 100):
    stmt = select(ScheduledJob).order_by(ScheduledJob.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(ScheduledJob.status == status)
    if system_key:
        stmt = stmt.where(ScheduledJob.system_key == system_key.upper())
    return list((await db.scalars(stmt)).all())


async def get_job(db: AsyncSession, job_id: str):
    return await db.get(ScheduledJob, job_id)


async def cancel_job(db: AsyncSession, job_id: str):
    row = await db.get(ScheduledJob, job_id)
    if row is None:
        raise LookupError(job_id)
    if row.status in {"succeeded", "failed", "cancelled"}:
        raise ValueError("job is already terminal")
    row.status = "cancelled"
    row.completed_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return row


async def mark_job_result(db: AsyncSession, job_id: str, *, succeeded: bool, error: str | None = None):
    row = await db.get(ScheduledJob, job_id)
    if row is None:
        raise LookupError(job_id)
    row.attempts += 1
    if succeeded:
        row.status = "succeeded"
        row.completed_at = _utcnow()
        row.last_error = None
    elif row.attempts >= row.max_attempts:
        row.status = "failed"
        row.completed_at = _utcnow()
        row.last_error = error
    else:
        row.status = "retry_wait"
        row.last_error = error
        row.next_attempt_at = _utcnow() + timedelta(seconds=row.retry_delay_seconds)
    await db.commit()
    await db.refresh(row)
    return row


async def claim_due_jobs(db: AsyncSession, limit: int = 20):
    now = _utcnow()
    stmt = select(ScheduledJob).where(
        ScheduledJob.status.in_(["queued", "scheduled", "retry_wait"]),
        ScheduledJob.next_attempt_at <= now,
    ).order_by(ScheduledJob.next_attempt_at.asc()).limit(limit)
    rows = list((await db.scalars(stmt)).all())
    for row in rows:
        row.status = "running"
        row.started_at = now
    if rows:
        await db.commit()
    return rows


async def execute_claimed_job(db: AsyncSession, row: ScheduledJob):
    payload = json.loads(row.payload_json or "{}")
    try:
        await execute_adapter(
            db,
            action=row.action,
            system_key=row.system_key,
            payload=payload,
            correlation_id=row.correlation_id,
            job_id=row.job_id,
        )
    except Exception as exc:
        return await mark_job_result(db, row.job_id, succeeded=False, error=str(exc))
    return await mark_job_result(db, row.job_id, succeeded=True)


async def scheduler_loop(interval_seconds: int = 5):
    while True:
        try:
            async with SessionLocal() as db:
                for row in await claim_due_jobs(db):
                    await execute_claimed_job(db, row)
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)


async def job_summary(db: AsyncSession):
    result = {"queued": 0, "scheduled": 0, "running": 0, "retry_wait": 0, "succeeded": 0, "failed": 0, "cancelled": 0, "total": 0}
    rows = (await db.execute(select(ScheduledJob.status, func.count()).group_by(ScheduledJob.status))).all()
    for status, count in rows:
        result[status] = count
        result["total"] += count
    return result
