from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import AuditEventIn, Principal
from app.services.audit import record_audit
from app.services.ml.model_registry import get_active_model, get_model
from app.services.ml.serving_policy import evaluate_serving_policy

router = APIRouter(prefix="/v1/ml/serving", tags=["machine-learning-serving"])


class ModelRef(BaseModel):
    model_key: str
    version: int | None = None
    weight: float = Field(default=1.0, gt=0)


class ServingRequest(BaseModel):
    value: float
    primary: ModelRef
    fallback: list[ModelRef] = Field(default_factory=list, max_length=20)
    canary: ModelRef | None = None
    canary_percentage: float = Field(default=0.0, ge=0, le=1)
    routing_key: str = ""
    shadows: list[ModelRef] = Field(default_factory=list, max_length=20)
    ensemble_threshold: float = Field(default=0.5, gt=0, lt=1)
    confidence_level: float = 0.95
    low_confidence_threshold: float = Field(default=0.70, ge=0.5, lt=1)
    context: dict = Field(default_factory=dict)


async def _resolve(db, ref: ModelRef):
    row = await (get_active_model(db, ref.model_key) if ref.version is None else get_model(db, ref.model_key, ref.version))
    if row is None:
        raise LookupError(f"model not found: {ref.model_key}")
    if row.status == "retired":
        raise ValueError(f"retired model cannot be served: {ref.model_key}:v{row.version}")
    return row


def _single_payload(item):
    if item is None:
        return None
    return {
        "model_key": item.explanation.model_key,
        "model_version": item.explanation.model_version,
        "algorithm": item.explanation.algorithm,
        "output": item.explanation.output,
        "classification": item.explanation.classification,
        "confidence_score": item.uncertainty.confidence_score,
        "low_confidence": item.uncertainty.low_confidence,
    }


@router.post("/predict")
async def serving_predict(
    body: ServingRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.predict")),
):
    try:
        primary = await _resolve(db, body.primary)
        fallback = [await _resolve(db, ref) for ref in body.fallback]
        canary = await _resolve(db, body.canary) if body.canary else None
        shadows = [await _resolve(db, ref) for ref in body.shadows]
        result = evaluate_serving_policy(
            primary_row=primary,
            value=body.value,
            fallback_rows=fallback,
            fallback_weights=[ref.weight for ref in body.fallback] if body.fallback else None,
            ensemble_threshold=body.ensemble_threshold,
            canary_row=canary,
            canary_percentage=body.canary_percentage,
            routing_key=body.routing_key,
            shadow_rows=shadows,
            confidence_level=body.confidence_level,
            low_confidence_threshold=body.low_confidence_threshold,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    selected = _single_payload(result.selected_single)
    if result.selected_ensemble is not None:
        selected = {
            "algorithm": result.selected_ensemble.algorithm,
            "output": result.selected_ensemble.output,
            "classification": result.selected_ensemble.classification,
            "member_count": result.selected_ensemble.member_count,
            "agreement_fraction": result.selected_ensemble.agreement_fraction,
            "output_spread": result.selected_ensemble.output_spread,
        }

    audit = await record_audit(db, AuditEventIn(
        actor_id=principal.subject,
        action="ml.serving_policy_prediction",
        resource_type="ml_serving_policy",
        resource_id=body.primary.model_key,
        payload={
            "route": result.route,
            "selected": selected,
            "primary": _single_payload(result.primary),
            "canary": _single_payload(result.canary),
            "canary_selected": result.canary_selected,
            "fallback_used": result.fallback_used,
            "shadows": [_single_payload(item) for item in result.shadows],
            "context": body.context,
        },
    ))

    return {
        "route": result.route,
        "selected": selected,
        "primary": _single_payload(result.primary),
        "canary": _single_payload(result.canary),
        "canary_selected": result.canary_selected,
        "fallback_used": result.fallback_used,
        "shadows": [_single_payload(item) for item in result.shadows],
        "audit_event_id": audit.event_id,
        "occurred_at": audit.occurred_at,
    }
