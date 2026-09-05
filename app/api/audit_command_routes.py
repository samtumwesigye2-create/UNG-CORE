from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.audit import list_audit_events, serialize_audit
from app.services.command_history import complete_command, list_commands, record_command, serialize_command

router = APIRouter(prefix="/v1/operator-history", tags=["operator-history"])


class CommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=128)
    target_type: str = Field(min_length=1, max_length=80)
    target_id: str | None = None
    system_key: str | None = None
    correlation_id: str | None = None
    request: dict = Field(default_factory=dict)
    before: dict = Field(default_factory=dict)


class CommandCompleteIn(BaseModel):
    status: str
    result_code: int | None = None
    result: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)


@router.post("/commands")
async def create_command(body: CommandIn, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.audit.write"))):
    row = await record_command(db, actor_id=principal.subject, command=body.command, target_type=body.target_type, target_id=body.target_id, system_key=body.system_key, correlation_id=body.correlation_id, request=body.request, before=body.before)
    return serialize_command(row)


@router.post("/commands/{command_id}/complete")
async def finish_command(command_id: str, body: CommandCompleteIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.audit.write"))):
    if body.status not in {"succeeded", "failed", "cancelled"}:
        raise HTTPException(status_code=400, detail="status must be succeeded, failed, or cancelled")
    try:
        row = await complete_command(db, command_id, body.status, body.result_code, body.result, body.after)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="command not found") from exc
    return serialize_command(row)


@router.get("/commands")
async def commands(actor_id: str | None = None, system_key: str | None = None, status: str | None = None, correlation_id: str | None = None, limit: int = Query(default=100, ge=1, le=500), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.audit.read"))):
    return [serialize_command(row) for row in await list_commands(db, actor_id, system_key, status, correlation_id, limit)]


@router.get("/audit")
async def audit_events(actor_id: str | None = None, action: str | None = None, resource_type: str | None = None, resource_id: str | None = None, correlation_id: str | None = None, limit: int = Query(default=100, ge=1, le=500), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.audit.read"))):
    return [serialize_audit(row) for row in await list_audit_events(db, actor_id, action, resource_type, resource_id, correlation_id, limit)]
