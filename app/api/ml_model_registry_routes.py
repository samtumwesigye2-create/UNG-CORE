from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.ml.model_registry import (
    activate_model,
    get_active_model,
    get_model,
    list_models,
    register_model,
    retire_model,
    rollback_model,
    serialize_model,
)

router = APIRouter(prefix="/v1/ml/models", tags=["machine-learning-model-registry"])


class ModelRegisterRequest(BaseModel):
    model_key: str = Field(min_length=1, max_length=160)
    algorithm: str = Field(min_length=1, max_length=120)
    artifact: dict
    metrics: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_model(
    body: ModelRegisterRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.models.write")),
):
    try:
        row = await register_model(
            db,
            model_key=body.model_key,
            algorithm=body.algorithm,
            artifact=body.artifact,
            metrics=body.metrics,
            metadata=body.metadata,
            created_by=principal.subject,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return serialize_model(row)


@router.get("")
async def models(
    model_key: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.models.read")),
):
    rows = await list_models(db, model_key)
    return {"count": len(rows), "models": [serialize_model(row) for row in rows]}


@router.get("/{model_key}/active")
async def active_model(
    model_key: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.models.read")),
):
    row = await get_active_model(db, model_key)
    if row is None:
        raise HTTPException(status_code=404, detail="active model not found")
    return serialize_model(row)


@router.get("/{model_key}/versions/{version}")
async def model_version(
    model_key: str,
    version: int,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.models.read")),
):
    row = await get_model(db, model_key, version)
    if row is None:
        raise HTTPException(status_code=404, detail="model version not found")
    return serialize_model(row)


@router.post("/{model_key}/versions/{version}/activate")
async def activate(
    model_key: str,
    version: int,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.models.activate")),
):
    try:
        row = await activate_model(db, model_key, version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_model(row)


@router.post("/{model_key}/versions/{version}/retire")
async def retire(
    model_key: str,
    version: int,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.models.write")),
):
    try:
        row = await retire_model(db, model_key, version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_model(row)


@router.post("/{model_key}/rollback")
async def rollback(
    model_key: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.models.activate")),
):
    try:
        row = await rollback_model(db, model_key)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_model(row)
