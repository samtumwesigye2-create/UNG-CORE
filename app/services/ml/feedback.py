from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import mean
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.schemas.contracts import AuditEventIn
from app.services.audit import record_audit


@dataclass(frozen=True)
class PredictionFeedback:
    prediction_event_id: str
    feedback_event_id: str
    model_key: str
    model_version: int
    algorithm: str
    predicted_value: float
    predicted_classification: int | None
    observed_value: float
    absolute_error: float | None
    squared_error: float | None
    correct: bool | None
    brier_score: float | None
    occurred_at: object


def _payload(row: AuditEvent) -> dict:
    return json.loads(row.payload_json or "{}")


async def get_prediction_event(db: AsyncSession, event_id: str) -> AuditEvent | None:
    stmt = select(AuditEvent).where(
        AuditEvent.event_id == event_id,
        AuditEvent.action.in_(["ml.prediction", "ml.multifeature_prediction"]),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _existing_feedback(db: AsyncSession, prediction_event_id: str) -> AuditEvent | None:
    stmt = select(AuditEvent).where(
        AuditEvent.action == "ml.prediction_feedback",
        AuditEvent.resource_type == "ml_prediction",
        AuditEvent.resource_id == prediction_event_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def record_prediction_feedback(
    db: AsyncSession,
    *,
    prediction_event_id: str,
    observed_value: float,
    actor_id: str,
    notes: str | None = None,
    context: dict | None = None,
) -> PredictionFeedback:
    prediction = await get_prediction_event(db, prediction_event_id)
    if prediction is None:
        raise LookupError("prediction audit event not found")
    if await _existing_feedback(db, prediction_event_id) is not None:
        raise ValueError("ground truth has already been recorded for this prediction")

    prediction_payload = _payload(prediction)
    algorithm = str(prediction_payload.get("algorithm", ""))
    model_key = str(prediction_payload.get("model_key", ""))
    model_version = int(prediction_payload.get("model_version"))
    output = prediction_payload.get("output") or {}
    predicted_value = float(output.get("value"))
    if not isfinite(predicted_value):
        raise ValueError("prediction output must be finite")

    observed = float(observed_value)
    if not isfinite(observed):
        raise ValueError("observed value must be finite")

    predicted_classification = output.get("classification")
    absolute_error = None
    squared_error = None
    correct = None
    brier_score = None

    if algorithm in {"linear_regression", "multivariate_linear_regression"}:
        error = predicted_value - observed
        absolute_error = abs(error)
        squared_error = error * error
    elif algorithm in {"logistic_regression", "multivariate_logistic_regression"}:
        if observed not in (0.0, 1.0):
            raise ValueError("logistic regression ground truth must be 0 or 1")
        actual_class = int(observed)
        if predicted_classification is None:
            threshold = float(output.get("threshold", 0.5))
            predicted_classification = 1 if predicted_value >= threshold else 0
        predicted_classification = int(predicted_classification)
        correct = predicted_classification == actual_class
        brier_score = (predicted_value - actual_class) ** 2
    else:
        raise ValueError("ground-truth feedback supports linear and logistic regression models")

    feedback = await record_audit(
        db,
        AuditEventIn(
            actor_id=actor_id,
            action="ml.prediction_feedback",
            resource_type="ml_prediction",
            resource_id=prediction_event_id,
            payload={
                "prediction_event_id": prediction_event_id,
                "model_key": model_key,
                "model_version": model_version,
                "algorithm": algorithm,
                "predicted": {
                    "value": predicted_value,
                    "classification": predicted_classification,
                    "threshold": output.get("threshold"),
                },
                "observed": {"value": observed},
                "metrics": {
                    "absolute_error": absolute_error,
                    "squared_error": squared_error,
                    "correct": correct,
                    "brier_score": brier_score,
                },
                "notes": notes,
                "context": dict(context or {}),
            },
        ),
    )

    return PredictionFeedback(
        prediction_event_id=prediction_event_id,
        feedback_event_id=feedback.event_id,
        model_key=model_key,
        model_version=model_version,
        algorithm=algorithm,
        predicted_value=predicted_value,
        predicted_classification=predicted_classification,
        observed_value=observed,
        absolute_error=absolute_error,
        squared_error=squared_error,
        correct=correct,
        brier_score=brier_score,
        occurred_at=feedback.occurred_at,
    )


def summarize_feedback_events(rows: Sequence[AuditEvent | dict]) -> dict:
    regression_abs: list[float] = []
    regression_sq: list[float] = []
    classification_correct: list[bool] = []
    brier_scores: list[float] = []
    per_model: dict[str, dict] = {}

    for row in rows:
        action = row.get("action") if isinstance(row, dict) else row.action
        if action != "ml.prediction_feedback":
            continue
        payload = row.get("payload", {}) if isinstance(row, dict) else json.loads(row.payload_json or "{}")
        model_key = str(payload.get("model_key", "unknown"))
        algorithm = str(payload.get("algorithm", ""))
        metrics = payload.get("metrics") or {}
        bucket = per_model.setdefault(
            model_key,
            {
                "algorithm": algorithm,
                "feedback_count": 0,
                "_abs": [],
                "_sq": [],
                "_correct": [],
                "_brier": [],
            },
        )
        bucket["feedback_count"] += 1

        if algorithm in {"linear_regression", "multivariate_linear_regression"}:
            ae = metrics.get("absolute_error")
            se = metrics.get("squared_error")
            if isinstance(ae, (int, float)) and isinstance(se, (int, float)):
                regression_abs.append(float(ae))
                regression_sq.append(float(se))
                bucket["_abs"].append(float(ae))
                bucket["_sq"].append(float(se))
        elif algorithm in {"logistic_regression", "multivariate_logistic_regression"}:
            correct = metrics.get("correct")
            brier = metrics.get("brier_score")
            if isinstance(correct, bool):
                classification_correct.append(correct)
                bucket["_correct"].append(correct)
            if isinstance(brier, (int, float)):
                brier_scores.append(float(brier))
                bucket["_brier"].append(float(brier))

    summarized_models = {}
    for key, bucket in per_model.items():
        summarized_models[key] = {
            "algorithm": bucket["algorithm"],
            "feedback_count": bucket["feedback_count"],
            "mae": mean(bucket["_abs"]) if bucket["_abs"] else None,
            "rmse": sqrt(mean(bucket["_sq"])) if bucket["_sq"] else None,
            "accuracy": (
                sum(bucket["_correct"]) / len(bucket["_correct"])
                if bucket["_correct"] else None
            ),
            "brier_score": mean(bucket["_brier"]) if bucket["_brier"] else None,
        }

    return {
        "feedback_count": sum(item["feedback_count"] for item in summarized_models.values()),
        "regression": {
            "count": len(regression_abs),
            "mae": mean(regression_abs) if regression_abs else None,
            "rmse": sqrt(mean(regression_sq)) if regression_sq else None,
        },
        "classification": {
            "count": len(classification_correct),
            "accuracy": (
                sum(classification_correct) / len(classification_correct)
                if classification_correct else None
            ),
            "brier_score": mean(brier_scores) if brier_scores else None,
        },
        "by_model": summarized_models,
    }
