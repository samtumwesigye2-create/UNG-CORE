from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.event_delivery import list_deliveries, publish_event, retry_delivery, serialize_delivery

router = APIRouter(prefix="/v1/event-delivery", tags=["event-delivery"])


class PublishEventIn(BaseModel):
    event_type: str = Field(min_length=1, max_length=160)
    target_system: str = Field(min_length=1, max_length=80)
    payload: dict = Field(default_factory=dict)
    correlation_id: str | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)


@router.post("/publish")
async def publish(body: PublishEventIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.events.publish"))):
    try:
        row = await publish_event(db, event_type=body.event_type, target_system=body.target_system, payload=body.payload, correlation_id=body.correlation_id, max_attempts=body.max_attempts)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_delivery(row)


@router.get("/deliveries")
async def deliveries(status: str | None = None, target_system: str | None = None, limit: int = Query(default=100, ge=1, le=500), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.events.read"))):
    return [serialize_delivery(row) for row in await list_deliveries(db, status, target_system, limit)]


@router.post("/deliveries/{delivery_id}/retry")
async def retry(delivery_id: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.events.retry"))):
    try:
        row = await retry_delivery(db, delivery_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="delivery not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_delivery(row)
