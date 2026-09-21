from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.audit import list_audit_events
from app.services.ml.calibration import (
    feedback_pairs,
    fit_platt_calibration,
    store_calibration,
)
from app.services.ml.model_registry import get_model, serialize_model

router = APIRouter(prefix="/v1/ml/calibration", tags=["machine-learning-calibration"])


class CalibrationFitRequest(BaseModel):
    learning_rate: float = Field(default=0.05, gt=0)
    epochs: int = Field(default=1000, ge=1, le=100000)
    minimum_samples: int = Field(default=20, ge=5, le=100000)


@router.post("/{model_key}/versions/{version}/fit")
async def fit_calibration(
    model_key: str,
    version: int,
    body: CalibrationFitRequest,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.models.write")),
):
    row = await get_model(db, model_key, version)
    if row is None:
        raise HTTPException(status_code=404, detail="model version not found")
    if row.algorithm != "logistic_regression":
        raise HTTPException(status_code=422, detail="probability calibration supports logistic_regression")
    feedback = await list_audit_events(db, action="ml.prediction_feedback", limit=10000)
    probabilities, labels = feedback_pairs(
        feedback,
        model_key=model_key,
        model_version=version,
    )
    if len(probabilities) < body.minimum_samples:
        raise HTTPException(
            status_code=409,
            detail=f"at least {body.minimum_samples} ground-truth samples are required",
        )
    try:
        calibration = fit_platt_calibration(
            probabilities,
            labels,
            learning_rate=body.learning_rate,
            epochs=body.epochs,
        )
        row = await store_calibration(db, row, calibration)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "model": serialize_model(row),
        "calibration": calibration,
    }


@router.get("/{model_key}/versions/{version}")
async def get_calibration(
    model_key: str,
    version: int,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.monitor")),
):
    row = await get_model(db, model_key, version)
    if row is None:
        raise HTTPException(status_code=404, detail="model version not found")
    model = serialize_model(row)
    return {
        "model_key": model_key,
        "model_version": version,
        "calibration": (model.get("metadata") or {}).get("probability_calibration"),
    }
