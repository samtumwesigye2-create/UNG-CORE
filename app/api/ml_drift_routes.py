from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import AuditEventIn, Principal
from app.services.audit import record_audit
from app.services.ml.drift_monitoring import monitor_model_drift
from app.services.ml.model_registry import get_active_model

router = APIRouter(prefix="/v1/ml/drift", tags=["machine-learning-drift"])


class DriftCheckRequest(BaseModel):
    x: list[float] = Field(min_length=2, max_length=100000)
    y: list[float] | None = Field(default=None, max_length=100000)
    mean_shift_threshold: float = Field(default=1.0, gt=0)
    std_ratio_threshold: float = Field(default=2.0, gt=1)
    performance_degradation_threshold: float = Field(default=0.15, gt=0, lt=1)


@router.post("/{model_key}/check")
async def check_model_drift(
    model_key: str,
    body: DriftCheckRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.monitor")),
):
    row = await get_active_model(db, model_key)
    if row is None:
        raise HTTPException(status_code=404, detail="active model not found")
    try:
        result = monitor_model_drift(
            row,
            current_x=body.x,
            current_y=body.y,
            mean_shift_threshold=body.mean_shift_threshold,
            std_ratio_threshold=body.std_ratio_threshold,
            performance_degradation_threshold=body.performance_degradation_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    payload = {
        "model_key": model_key,
        "model_version": row.version,
        "data_drift": result.data_drift,
        "performance_drift": result.performance_drift,
        "drift_detected": result.drift_detected,
        "retraining_recommended": result.retraining_recommended,
    }
    await record_audit(
        db,
        AuditEventIn(
            actor_id=principal.subject,
            action="ml.drift_check",
            resource_type="ml_model",
            resource_id=f"{model_key}:v{row.version}",
            payload=payload,
        ),
    )
    return payload
