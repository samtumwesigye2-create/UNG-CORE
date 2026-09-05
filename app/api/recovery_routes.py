from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.scheduler import enqueue_job
from app.services.security_resilience import list_credentials, list_dead_letters, mark_dead_letter_replayed, resilience_summary, serialize_credential, serialize_dead_letter, upsert_credential

router = APIRouter(prefix="/v1/recovery", tags=["recovery"])


class ServiceAuthRefIn(BaseModel):
    system_key: str = Field(min_length=1, max_length=80)
    auth_type: str = Field(default="bearer", max_length=32)
    secret_env_var: str = Field(min_length=1, max_length=160)
    header_name: str = Field(default="Authorization", max_length=128)
    prefix: str = Field(default="Bearer ", max_length=64)
    enabled: bool = True


@router.put("/service-auth/{credential_key}")
async def set_service_auth(credential_key: str, body: ServiceAuthRefIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.credentials.write"))):
    row = await upsert_credential(db, credential_key, system_key=body.system_key, auth_type=body.auth_type, secret_env_var=body.secret_env_var, header_name=body.header_name, prefix=body.prefix, enabled=body.enabled)
    return serialize_credential(row)


@router.get("/service-auth")
async def service_auth(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.credentials.read"))):
    return [serialize_credential(row) for row in await list_credentials(db)]


@router.get("/dead-letters")
async def dead_letters(status: str | None = None, limit: int = Query(default=100, ge=1, le=500), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.recovery.read"))):
    return [serialize_dead_letter(row) for row in await list_dead_letters(db, status, limit)]


@router.post("/dead-letters/{dead_letter_id}/replay")
async def replay(dead_letter_id: str, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.recovery.execute"))):
    rows = [row for row in await list_dead_letters(db, None, 500) if row.dead_letter_id == dead_letter_id]
    if not rows:
        raise HTTPException(status_code=404, detail="dead letter not found")
    row = rows[0]
    if row.status != "dead":
        raise HTTPException(status_code=409, detail="dead letter is not replayable")
    payload = serialize_dead_letter(row)["payload"]
    job = await enqueue_job(db, action=row.action, actor_id=principal.subject, target_type="recovery", target_id=row.dead_letter_id, system_key=row.system_key, correlation_id=None, approval_request_id=None, payload=payload, scheduled_for=None, max_attempts=3, retry_delay_seconds=30)
    await mark_dead_letter_replayed(db, dead_letter_id)
    return {"dead_letter_id": dead_letter_id, "replay_job_id": job.job_id, "status": "replayed"}


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.recovery.read"))):
    return await resilience_summary(db)
