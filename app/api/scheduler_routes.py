from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.scheduler import cancel_job, enqueue_job, get_job, list_jobs, mark_job_result, serialize_job

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


class JobIn(BaseModel):
    action: str = Field(min_length=1, max_length=160)
    target_type: str = Field(min_length=1, max_length=80)
    target_id: str | None = None
    system_key: str | None = None
    correlation_id: str | None = None
    approval_request_id: str | None = None
    payload: dict = Field(default_factory=dict)
    scheduled_for: datetime | None = None
    max_attempts: int = Field(default=3, ge=1, le=20)
    retry_delay_seconds: int = Field(default=30, ge=1, le=86400)


class JobResultIn(BaseModel):
    succeeded: bool
    error: str | None = None


@router.post("")
async def create_job(body: JobIn, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.jobs.write"))):
    return serialize_job(await enqueue_job(db, action=body.action, actor_id=principal.subject, target_type=body.target_type, target_id=body.target_id, system_key=body.system_key, correlation_id=body.correlation_id, approval_request_id=body.approval_request_id, payload=body.payload, scheduled_for=body.scheduled_for, max_attempts=body.max_attempts, retry_delay_seconds=body.retry_delay_seconds))


@router.get("")
async def jobs(status: str | None = None, system_key: str | None = None, limit: int = Query(default=100, ge=1, le=500), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.jobs.read"))):
    return [serialize_job(row) for row in await list_jobs(db, status, system_key, limit)]


@router.get("/{job_id}")
async def job(job_id: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.jobs.read"))):
    row = await get_job(db, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return serialize_job(row)


@router.post("/{job_id}/cancel")
async def cancel(job_id: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.jobs.cancel"))):
    try:
        return serialize_job(await cancel_job(db, job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{job_id}/result")
async def result(job_id: str, body: JobResultIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.jobs.execute"))):
    try:
        return serialize_job(await mark_job_result(db, job_id, succeeded=body.succeeded, error=body.error))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
