import json
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import get_db
from app.schemas.contracts import AuditEventIn, AuditEventOut
from app.services.audit import record_audit

router = APIRouter()

@router.get("/health")
async def health():
    return {"status":"ok","service":settings.app_name,"version":settings.service_version}

@router.get("/ready")
async def ready():
    return {"status":"ready","environment":settings.environment}

@router.post("/v1/audit/events", response_model=AuditEventOut)
async def create_audit_event(body: AuditEventIn, db: AsyncSession = Depends(get_db)):
    row = await record_audit(db, body)
    return AuditEventOut(event_id=row.event_id, actor_id=row.actor_id, action=row.action,
        resource_type=row.resource_type, resource_id=row.resource_id,
        payload=json.loads(row.payload_json), occurred_at=row.occurred_at)
