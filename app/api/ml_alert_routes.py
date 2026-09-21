from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.audit import list_audit_events
from app.services.ml.health_alerts import MLAlertThresholds, evaluate_and_raise_ml_alerts
from app.services.ml.model_registry import list_models

router = APIRouter(prefix="/v1/ml/alerts", tags=["machine-learning-alerts"])


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
