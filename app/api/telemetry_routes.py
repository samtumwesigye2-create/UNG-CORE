from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.telemetry import fleet_health_summary, list_telemetry, serialize_telemetry, service_sla_summary

router = APIRouter(prefix="/v1/telemetry", tags=["telemetry"])


@router.get("/fleet")
async def fleet(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.telemetry.read"))):
    return await fleet_health_summary(db)


@router.get("/services/{service_key}/history")
async def history(service_key: str, limit: int = Query(default=200, ge=1, le=1000), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.telemetry.read"))):
    return [serialize_telemetry(row) for row in await list_telemetry(db, service_key, limit)]


@router.get("/services/{service_key}/sla")
async def sla(service_key: str, window_minutes: int = Query(default=60, ge=5, le=43200), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.telemetry.read"))):
    return await service_sla_summary(db, service_key, window_minutes)
