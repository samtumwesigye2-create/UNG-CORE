from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.ml.explainability import explain_batch, explain_prediction
from app.services.ml.model_registry import get_active_model, get_model

router = APIRouter(prefix="/v1/ml/explain", tags=["machine-learning-explainability"])


class ExplainRequest(BaseModel):
    value: float


class ExplainBatchRequest(BaseModel):
    values: list[float] = Field(min_length=1, max_length=10000)


def _serialize(result):
    return {
        "model_key": result.model_key,
        "model_version": result.model_version,
        "algorithm": result.algorithm,
        "input_value": result.input_value,
        "output": result.output,
        "classification": result.classification,
        "threshold": result.threshold,
        "contributions": result.contributions,
        "parameters": result.parameters,
        "explanation": result.explanation,
    }


@router.post("/{model_key}/active")
async def explain_active(
    model_key: str,
    body: ExplainRequest,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.explain")),
):
    row = await get_active_model(db, model_key)
    if row is None:
        raise HTTPException(status_code=404, detail="active model not found")
    try:
        return _serialize(explain_prediction(row, body.value))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{model_key}/versions/{version}")
async def explain_version(
    model_key: str,
    version: int,
    body: ExplainRequest,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.explain")),
):
    row = await get_model(db, model_key, version)
    if row is None:
        raise HTTPException(status_code=404, detail="model version not found")
    try:
        return _serialize(explain_prediction(row, body.value))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{model_key}/active/batch")
async def explain_active_batch(
    model_key: str,
    body: ExplainBatchRequest,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.explain")),
):
    row = await get_active_model(db, model_key)
    if row is None:
        raise HTTPException(status_code=404, detail="active model not found")
    try:
        results = explain_batch(row, body.values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"count": len(results), "explanations": [_serialize(item) for item in results]}
