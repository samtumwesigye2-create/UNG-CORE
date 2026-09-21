from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.contracts import AuditEventIn
from app.services.audit import list_audit_events, record_audit
from app.services.ml.model_registry import activate_model, get_active_model, list_models, serialize_model
from app.services.ml.production_performance import evaluate_production_performance


@dataclass(frozen=True)
class AutoRollbackResult:
    model_key: str
    triggered: bool
    reasons: list[str]
    previous_version: int | None
    active_version: int | None
    rollback_version: int | None


def _payload(row) -> dict:
    if isinstance(row, dict):
        return row.get("payload", {}) or {}
    return json.loads(getattr(row, "payload_json", "{}") or "{}")


async def evaluate_auto_rollback(
    db: AsyncSession,
    *,
    model_key: str,
    actor_id: str,
    minimum_feedback: int = 20,
    maximum_production_degradation: float = 0.20,
    maximum_low_confidence_rate: float = 0.50,
    minimum_prediction_samples: int = 20,
) -> AutoRollbackResult:
    active = await get_active_model(db, model_key)
    if active is None:
        raise LookupError("active model not found")
    audits = await list_audit_events(db, limit=10000)
    reasons: list[str] = []

    production_gate = evaluate_production_performance(
        active,
        audits,
        minimum_feedback=minimum_feedback,
        maximum_degradation_fraction=maximum_production_degradation,
    )
    if production_gate.degraded:
        reasons.append("production_performance_degraded")

    for row in audits:
        action = row.get("action") if isinstance(row, dict) else getattr(row, "action", "")
        if action != "ml.drift_check":
            continue
        payload = _payload(row)
        if payload.get("model_key") == model_key:
            if payload.get("drift_detected") is True:
                reasons.append("drift_detected")
            break

    prediction_events = []
    for row in audits:
        action = row.get("action") if isinstance(row, dict) else getattr(row, "action", "")
        if action != "ml.prediction":
            continue
        payload = _payload(row)
        if payload.get("model_key") == model_key and int(payload.get("model_version", -1)) == active.version:
            prediction_events.append(payload)
    if len(prediction_events) >= minimum_prediction_samples:
        low = sum(
            ((item.get("uncertainty") or {}).get("low_confidence") is True)
            for item in prediction_events
        )
        low_rate = low / len(prediction_events)
        if low_rate > maximum_low_confidence_rate:
            reasons.append("critical_low_confidence_rate")

    if not reasons:
        return AutoRollbackResult(
            model_key=model_key,
            triggered=False,
            reasons=[],
            previous_version=active.version,
            active_version=active.version,
            rollback_version=None,
        )

    versions = await list_models(db, model_key)
    candidates = []
    for row in versions:
        if row.version >= active.version or row.status == "retired":
            continue
        snapshot = serialize_model(row)
        validation = (snapshot.get("metadata") or {}).get("validation") or {}
        if validation.get("passed") is not True:
            continue
        gate = evaluate_production_performance(
            row,
            audits,
            minimum_feedback=minimum_feedback,
            maximum_degradation_fraction=maximum_production_degradation,
        )
        if gate.passed:
            candidates.append(row)

    if not candidates:
        raise ValueError("rollback triggered but no eligible prior model version is available")

    rollback = max(candidates, key=lambda row: row.version)
    previous_version = active.version
    activated = await activate_model(db, model_key, rollback.version)
    await record_audit(
        db,
        AuditEventIn(
            actor_id=actor_id,
            action="ml.auto_rollback",
            resource_type="ml_model",
            resource_id=f"{model_key}:v{rollback.version}",
            payload={
                "model_key": model_key,
                "previous_version": previous_version,
                "rollback_version": rollback.version,
                "reasons": reasons,
            },
        ),
    )
    return AutoRollbackResult(
        model_key=model_key,
        triggered=True,
        reasons=reasons,
        previous_version=previous_version,
        active_version=activated.version,
        rollback_version=rollback.version,
    )
