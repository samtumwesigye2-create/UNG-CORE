from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import mean
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.services.ml.model_registry import activate_model, serialize_model


@dataclass(frozen=True)
class ProductionPerformanceGate:
    model_key: str
    model_version: int
    algorithm: str
    feedback_count: int
    minimum_feedback: int
    validation_metric: str
    validation_value: float | None
    production_value: float | None
    degradation_fraction: float | None
    maximum_degradation_fraction: float
    sufficient_feedback: bool
    degraded: bool
    passed: bool
    status: str


def _payload(row: AuditEvent | dict) -> dict:
    if isinstance(row, dict):
        value = row.get("payload", {})
        return value if isinstance(value, dict) else {}
    return json.loads(row.payload_json or "{}")


def _action(row: AuditEvent | dict) -> str:
    return str(row.get("action", "")) if isinstance(row, dict) else str(row.action)


def _feedback_for_version(
    rows: Sequence[AuditEvent | dict],
    *,
    model_key: str,
    model_version: int,
) -> list[dict]:
    matched: list[dict] = []
    for row in rows:
        if _action(row) != "ml.prediction_feedback":
            continue
        payload = _payload(row)
        if (
            str(payload.get("model_key", "")) == model_key
            and int(payload.get("model_version", -1)) == model_version
        ):
            matched.append(payload)
    return matched


def evaluate_production_performance(
    model_row,
    feedback_rows: Sequence[AuditEvent | dict],
    *,
    minimum_feedback: int = 20,
    maximum_degradation_fraction: float = 0.20,
) -> ProductionPerformanceGate:
    if minimum_feedback < 1:
        raise ValueError("minimum_feedback must be at least 1")
    if not isfinite(maximum_degradation_fraction) or maximum_degradation_fraction < 0:
        raise ValueError("maximum_degradation_fraction must be a finite non-negative number")

    model = model_row if isinstance(model_row, dict) else serialize_model(model_row)
    model_key = str(model["model_key"])
    model_version = int(model["version"])
    algorithm = str(model["algorithm"])
    feedback = _feedback_for_version(
        feedback_rows,
        model_key=model_key,
        model_version=model_version,
    )
    feedback_count = len(feedback)
    validation = (model.get("metrics") or {}).get("validation", {})

    if algorithm == "linear_regression":
        validation_metric = "rmse"
        raw_validation = validation.get("rmse")
        squared_errors = []
        for item in feedback:
            value = (item.get("metrics") or {}).get("squared_error")
            if isinstance(value, (int, float)) and isfinite(float(value)) and float(value) >= 0:
                squared_errors.append(float(value))
        production_value = sqrt(mean(squared_errors)) if squared_errors else None
    elif algorithm == "logistic_regression":
        validation_metric = "accuracy"
        raw_validation = validation.get("accuracy")
        correct_values = []
        for item in feedback:
            value = (item.get("metrics") or {}).get("correct")
            if isinstance(value, bool):
                correct_values.append(value)
        production_value = (
            sum(correct_values) / len(correct_values) if correct_values else None
        )
    else:
        raise ValueError("production performance gates support linear_regression and logistic_regression")

    validation_value = None
    if raw_validation is not None:
        validation_value = float(raw_validation)
        if not isfinite(validation_value):
            raise ValueError("validation metric must be finite")

    sufficient_feedback = feedback_count >= minimum_feedback
    if not sufficient_feedback:
        return ProductionPerformanceGate(
            model_key=model_key,
            model_version=model_version,
            algorithm=algorithm,
            feedback_count=feedback_count,
            minimum_feedback=minimum_feedback,
            validation_metric=validation_metric,
            validation_value=validation_value,
            production_value=production_value,
            degradation_fraction=None,
            maximum_degradation_fraction=maximum_degradation_fraction,
            sufficient_feedback=False,
            degraded=False,
            passed=True,
            status="insufficient_feedback",
        )

    if validation_value is None or production_value is None:
        return ProductionPerformanceGate(
            model_key=model_key,
            model_version=model_version,
            algorithm=algorithm,
            feedback_count=feedback_count,
            minimum_feedback=minimum_feedback,
            validation_metric=validation_metric,
            validation_value=validation_value,
            production_value=production_value,
            degradation_fraction=None,
            maximum_degradation_fraction=maximum_degradation_fraction,
            sufficient_feedback=True,
            degraded=False,
            passed=True,
            status="metric_unavailable",
        )

    denominator = max(abs(validation_value), 1e-12)
    if algorithm == "linear_regression":
        degradation = (production_value - validation_value) / denominator
    else:
        degradation = (validation_value - production_value) / denominator

    degraded = degradation > maximum_degradation_fraction
    return ProductionPerformanceGate(
        model_key=model_key,
        model_version=model_version,
        algorithm=algorithm,
        feedback_count=feedback_count,
        minimum_feedback=minimum_feedback,
        validation_metric=validation_metric,
        validation_value=validation_value,
        production_value=production_value,
        degradation_fraction=degradation,
        maximum_degradation_fraction=maximum_degradation_fraction,
        sufficient_feedback=True,
        degraded=degraded,
        passed=not degraded,
        status="degraded" if degraded else "healthy",
    )


async def load_feedback_events(db: AsyncSession, *, limit: int = 10000) -> list[AuditEvent]:
    if hasattr(db, "ml_models") and not hasattr(db, "execute"):
        return []
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.action == "ml.prediction_feedback")
        .order_by(AuditEvent.occurred_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def production_gate_for_model(
    db: AsyncSession,
    model_row,
    *,
    minimum_feedback: int = 20,
    maximum_degradation_fraction: float = 0.20,
) -> ProductionPerformanceGate:
    feedback = await load_feedback_events(db)
    return evaluate_production_performance(
        model_row,
        feedback,
        minimum_feedback=minimum_feedback,
        maximum_degradation_fraction=maximum_degradation_fraction,
    )


async def activate_model_with_production_gate(
    db: AsyncSession,
    model_key: str,
    version: int,
    *,
    minimum_feedback: int = 20,
    maximum_degradation_fraction: float = 0.20,
) -> tuple[object, ProductionPerformanceGate]:
    from app.services.ml.model_registry import get_model

    row = await get_model(db, model_key, version)
    if row is None:
        raise LookupError("model version not found")
    gate = await production_gate_for_model(
        db,
        row,
        minimum_feedback=minimum_feedback,
        maximum_degradation_fraction=maximum_degradation_fraction,
    )
    if not gate.passed:
        raise ValueError(
            f"production performance gate failed: {gate.validation_metric} degraded "
            f"by {gate.degradation_fraction:.3f}, exceeding {gate.maximum_degradation_fraction:.3f}"
        )
    return await activate_model(db, model_key, version), gate


def serialize_production_gate(gate: ProductionPerformanceGate) -> dict:
    return {
        "model_key": gate.model_key,
        "model_version": gate.model_version,
        "algorithm": gate.algorithm,
        "feedback_count": gate.feedback_count,
        "minimum_feedback": gate.minimum_feedback,
        "validation_metric": gate.validation_metric,
        "validation_value": gate.validation_value,
        "production_value": gate.production_value,
        "degradation_fraction": gate.degradation_fraction,
        "maximum_degradation_fraction": gate.maximum_degradation_fraction,
        "sufficient_feedback": gate.sufficient_feedback,
        "degraded": gate.degraded,
        "passed": gate.passed,
        "status": gate.status,
    }
