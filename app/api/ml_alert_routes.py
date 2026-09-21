from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.audit import list_audit_events
from app.services.ml.health_alerts import MLAlertThresholds, evaluate_and_raise_ml_alerts
from app.services.ml.model_registry import list_models
from app.services.scheduler import enqueue_job, serialize_job

router = APIRouter(prefix="/v1/ml/alerts", tags=["machine-learning-alerts"])


class MLAlertScheduleRequest(BaseModel):
    interval_seconds: int = Field(default=300, ge=60, le=86400)
    scheduled_for: datetime | None = None
    event_limit: int = Field(default=1000, ge=1, le=5000)
    minimum_average_confidence: float = Field(default=0.70, ge=0, le=1)
    maximum_low_confidence_rate: float = Field(default=0.25, ge=0, le=1)
    maximum_fallback_rate: float = Field(default=0.25, ge=0, le=1)
    maximum_shadow_difference: float = Field(default=0.20, ge=0)
    maximum_canary_difference: float = Field(default=0.20, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=20)
    retry_delay_seconds: int = Field(default=30, ge=1, le=86400)


class MLAlertThresholdRequest(BaseModel):
    minimum_average_confidence: float = Field(default=0.70, ge=0, le=1)
    maximum_low_confidence_rate: float = Field(default=0.25, ge=0, le=1)
    maximum_fallback_rate: float = Field(default=0.25, ge=0, le=1)
    maximum_shadow_difference: float = Field(default=0.20, ge=0)
    maximum_canary_difference: float = Field(default=0.20, ge=0)


@router.post("/evaluate")
async def evaluate_ml_alerts(
    body: MLAlertThresholdRequest,
    event_limit: int = Query(default=1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.monitor")),
):
    models = await list_models(db)
    events = await list_audit_events(db, limit=event_limit)
    thresholds = MLAlertThresholds(**body.model_dump())
    return await evaluate_and_raise_ml_alerts(
        db,
        model_rows=models,
        audit_rows=events,
        thresholds=thresholds,
    )


@router.post("/schedule")
async def schedule_ml_alerts(
    body: MLAlertScheduleRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.monitor")),
):
    payload = {
        "_repeat_interval_seconds": body.interval_seconds,
        "event_limit": body.event_limit,
        "minimum_average_confidence": body.minimum_average_confidence,
        "maximum_low_confidence_rate": body.maximum_low_confidence_rate,
        "maximum_fallback_rate": body.maximum_fallback_rate,
        "maximum_shadow_difference": body.maximum_shadow_difference,
        "maximum_canary_difference": body.maximum_canary_difference,
    }
    row = await enqueue_job(
        db,
        action="ml.health.evaluate",
        actor_id=principal.subject,
        target_type="ml_health",
        target_id="global",
        system_key="ML",
        correlation_id=None,
        approval_request_id=None,
        payload=payload,
        scheduled_for=body.scheduled_for,
        max_attempts=body.max_attempts,
        retry_delay_seconds=body.retry_delay_seconds,
    )
    return serialize_job(row)
