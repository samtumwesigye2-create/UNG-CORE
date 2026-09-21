from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.ml.model_registry import get_active_model, get_model
from app.services.ml.prediction_audit import predict_and_record

router = APIRouter(prefix="/v1/ml/predictions", tags=["machine-learning-predictions"])


class PredictionRequest(BaseModel):
    value: float
    context: dict = Field(default_factory=dict)


def _response(result):
    explanation = result.explanation
    return {
        "model_key": explanation.model_key,
        "model_version": explanation.model_version,
        "algorithm": explanation.algorithm,
        "input_value": explanation.input_value,
        "output": explanation.output,
        "classification": explanation.classification,
        "threshold": explanation.threshold,
        "explanation": explanation.explanation,
        "explanation_ref": result.explanation_ref,
        "explanation_sha256": result.explanation_sha256,
        "audit_event_id": result.audit_event_id,
        "occurred_at": result.occurred_at,
    }


@router.post("/{model_key}/active")
async def predict_active(
    model_key: str,
    body: PredictionRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.predict")),
):
    row = await get_active_model(db, model_key)
    if row is None:
        raise HTTPException(status_code=404, detail="active model not found")
    try:
        result = await predict_and_record(
            db,
            model_row=row,
            input_value=body.value,
            actor_id=principal.subject,
            request_context=body.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response(result)


@router.post("/{model_key}/versions/{version}")
async def predict_version(
    model_key: str,
    version: int,
    body: PredictionRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.predict")),
):
    row = await get_model(db, model_key, version)
    if row is None:
        raise HTTPException(status_code=404, detail="model version not found")
    try:
        result = await predict_and_record(
            db,
            model_row=row,
            input_value=body.value,
            actor_id=principal.subject,
            request_context=body.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response(result)
