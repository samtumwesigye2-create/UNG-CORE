from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.contracts import AuditEventIn
from app.services.audit import record_audit
from app.services.ml.explainability import PredictionExplanation, explain_prediction
from app.services.ml.uncertainty import PredictionUncertainty, estimate_uncertainty


@dataclass(frozen=True)
class AuditedPrediction:
    explanation: PredictionExplanation
    uncertainty: PredictionUncertainty
    explanation_ref: str
    explanation_sha256: str
    audit_event_id: str
    occurred_at: object


def explanation_fingerprint(explanation: PredictionExplanation) -> str:
    payload = {
        "model_key": explanation.model_key,
        "model_version": explanation.model_version,
        "algorithm": explanation.algorithm,
        "input_value": explanation.input_value,
        "output": explanation.output,
        "classification": explanation.classification,
        "threshold": explanation.threshold,
        "contributions": explanation.contributions,
        "parameters": explanation.parameters,
        "explanation": explanation.explanation,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def predict_and_record(
    db: AsyncSession,
    *,
    model_row,
    input_value: float,
    actor_id: str,
    request_context: dict | None = None,
    confidence_level: float = 0.95,
    low_confidence_threshold: float = 0.70,
) -> AuditedPrediction:
    explanation = explain_prediction(model_row, input_value)
    uncertainty = estimate_uncertainty(
        model_row,
        explanation,
        confidence_level=confidence_level,
        low_confidence_threshold=low_confidence_threshold,
    )
    explanation_ref = str(uuid.uuid4())
    explanation_sha256 = explanation_fingerprint(explanation)

    audit = await record_audit(
        db,
        AuditEventIn(
            actor_id=actor_id,
            action="ml.prediction",
            resource_type="ml_model",
            resource_id=f"{explanation.model_key}:v{explanation.model_version}",
            payload={
                "model_key": explanation.model_key,
                "model_version": explanation.model_version,
                "algorithm": explanation.algorithm,
                "input": {"value": explanation.input_value},
                "output": {
                    "value": explanation.output,
                    "classification": explanation.classification,
                    "threshold": explanation.threshold,
                },
                "explanation_ref": explanation_ref,
                "explanation_sha256": explanation_sha256,
                "contributions": explanation.contributions,
                "parameters": explanation.parameters,
                "uncertainty": {
                    "confidence_score": uncertainty.confidence_score,
                    "low_confidence": uncertainty.low_confidence,
                    "confidence_level": uncertainty.confidence_level,
                    "interval_lower": uncertainty.interval_lower,
                    "interval_upper": uncertainty.interval_upper,
                    "uncertainty_width": uncertainty.uncertainty_width,
                    "probability_margin": uncertainty.probability_margin,
                    "entropy": uncertainty.entropy,
                    "method": uncertainty.method,
                },
                "context": dict(request_context or {}),
            },
        ),
    )

    return AuditedPrediction(
        explanation=explanation,
        uncertainty=uncertainty,
        explanation_ref=explanation_ref,
        explanation_sha256=explanation_sha256,
        audit_event_id=audit.event_id,
        occurred_at=audit.occurred_at,
    )
