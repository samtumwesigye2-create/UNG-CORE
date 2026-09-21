from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import AuditEventIn, Principal
from app.services.audit import record_audit
from app.services.ml.ensemble import predict_ensemble
from app.services.ml.model_registry import get_active_model, get_model

router = APIRouter(prefix="/v1/ml/ensembles", tags=["machine-learning-ensembles"])


class EnsembleMemberIn(BaseModel):
    model_key: str = Field(min_length=1, max_length=160)
    version: int | None = Field(default=None, ge=1)
    weight: float = Field(default=1.0, gt=0)


class EnsemblePredictionRequest(BaseModel):
    value: float
    members: list[EnsembleMemberIn] = Field(min_length=2, max_length=20)
    threshold: float = Field(default=0.5, gt=0, lt=1)
    context: dict = Field(default_factory=dict)


async def _resolve_member(db: AsyncSession, member: EnsembleMemberIn):
    if member.version is None:
        row = await get_active_model(db, member.model_key)
        if row is None:
            raise LookupError(f"active model not found: {member.model_key}")
        return row
    row = await get_model(db, member.model_key, member.version)
    if row is None:
        raise LookupError(f"model version not found: {member.model_key}:v{member.version}")
    if row.status == "retired":
        raise ValueError(f"retired model cannot join ensemble: {member.model_key}:v{member.version}")
    return row


@router.post("/predict")
async def ensemble_predict(
    body: EnsemblePredictionRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.ml.predict")),
):
    try:
        rows = [await _resolve_member(db, member) for member in body.members]
        identities = [(row.model_key, row.version) for row in rows]
        if len(set(identities)) != len(identities):
            raise ValueError("ensemble members must be distinct model versions")

        result = predict_ensemble(
            rows,
            body.value,
            weights=[member.weight for member in body.members],
            threshold=body.threshold,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    audit = await record_audit(
        db,
        AuditEventIn(
            actor_id=principal.subject,
            action="ml.ensemble_prediction",
            resource_type="ml_ensemble",
            resource_id="+".join(
                f"{member.model_key}:v{member.model_version}" for member in result.members
            ),
            payload={
                "algorithm": result.algorithm,
                "input": {"value": result.input_value},
                "output": {
                    "value": result.output,
                    "classification": result.classification,
                    "threshold": result.threshold,
                },
                "method": result.method,
                "member_count": result.member_count,
                "output_spread": result.output_spread,
                "agreement_fraction": result.agreement_fraction,
                "members": [
                    {
                        "model_key": member.model_key,
                        "model_version": member.model_version,
                        "algorithm": member.algorithm,
                        "weight": member.weight,
                        "output": member.output,
                        "classification": member.classification,
                        "threshold": member.threshold,
                    }
                    for member in result.members
                ],
                "context": body.context,
            },
        ),
    )

    return {
        "algorithm": result.algorithm,
        "input_value": result.input_value,
        "output": result.output,
        "classification": result.classification,
        "threshold": result.threshold,
        "member_count": result.member_count,
        "method": result.method,
        "output_spread": result.output_spread,
        "agreement_fraction": result.agreement_fraction,
        "members": [
            {
                "model_key": member.model_key,
                "model_version": member.model_version,
                "algorithm": member.algorithm,
                "weight": member.weight,
                "output": member.output,
                "classification": member.classification,
                "threshold": member.threshold,
                "explanation": member.explanation,
            }
            for member in result.members
        ],
        "audit_event_id": audit.event_id,
        "occurred_at": audit.occurred_at,
    }
