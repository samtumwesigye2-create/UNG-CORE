from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.audit import list_audit_events
from app.services.ml.feedback import record_prediction_feedback, summarize_feedback_events

router = APIRouter(prefix="/v1/ml/feedback", tags=["machine-learning-feedback"])


class PredictionFeedbackRequest(BaseModel):
    observed_value: float
    notes: str | None = Field(default=None, max_length=2000)
    context: dict = Field(default_factory=dict)


@router.post("/{prediction_event_id}")
async def submit_prediction_feedback(
    prediction_event_id: str,
    body: PredictionFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.monitor")),
):
    try:
        result = await record_prediction_feedback(
            db,
            prediction_event_id=prediction_event_id,
            observed_value=body.observed_value,
            actor_id=principal.subject,
            notes=body.notes,
            context=body.context,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409 if "already" in str(exc) else 422, detail=str(exc)) from exc

    return {
        "prediction_event_id": result.prediction_event_id,
        "feedback_event_id": result.feedback_event_id,
        "model_key": result.model_key,
        "model_version": result.model_version,
        "algorithm": result.algorithm,
        "predicted_value": result.predicted_value,
        "predicted_classification": result.predicted_classification,
        "observed_value": result.observed_value,
        "absolute_error": result.absolute_error,
        "squared_error": result.squared_error,
        "correct": result.correct,
        "brier_score": result.brier_score,
        "occurred_at": result.occurred_at,
    }


@router.get("/summary")
async def feedback_summary(
    limit: int = Query(default=5000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.monitor")),
):
    rows = await list_audit_events(db, action="ml.prediction_feedback", limit=limit)
    return summarize_feedback_events(rows)
