from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log
from typing import Literal

from app.services.ml.explainability import PredictionExplanation
from app.services.ml.model_registry import serialize_model

ConfidenceLevel = Literal[0.90, 0.95, 0.99]

_Z_VALUES: dict[float, float] = {
    0.90: 1.6448536269514722,
    0.95: 1.959963984540054,
    0.99: 2.5758293035489004,
}


@dataclass(frozen=True)
class PredictionUncertainty:
    confidence_score: float
    low_confidence: bool
    confidence_level: float | None
    interval_lower: float | None
    interval_upper: float | None
    uncertainty_width: float | None
    probability_margin: float | None
    entropy: float | None
    method: str


def _validate_low_confidence_threshold(value: float) -> float:
    threshold = float(value)
    if not isfinite(threshold) or not 0.5 <= threshold < 1.0:
        raise ValueError("low_confidence_threshold must be between 0.5 and 1.0")
    return threshold


def _regression_uncertainty(
    model: dict,
    explanation: PredictionExplanation,
    *,
    confidence_level: float,
    low_confidence_threshold: float,
) -> PredictionUncertainty:
    if confidence_level not in _Z_VALUES:
        raise ValueError("confidence_level must be one of 0.90, 0.95, or 0.99")

    validation = model.get("metrics", {}).get("validation", {})
    rmse = validation.get("rmse")
    if rmse is None:
        return PredictionUncertainty(
            confidence_score=0.0,
            low_confidence=True,
            confidence_level=confidence_level,
            interval_lower=None,
            interval_upper=None,
            uncertainty_width=None,
            probability_margin=None,
            entropy=None,
            method="validation_rmse_unavailable",
        )

    rmse = float(rmse)
    if not isfinite(rmse) or rmse < 0:
        raise ValueError("validation RMSE must be a finite non-negative number")

    z_value = _Z_VALUES[confidence_level]
    half_width = z_value * rmse
    lower = explanation.output - half_width
    upper = explanation.output + half_width

    scale = max(abs(explanation.output), rmse, 1e-12)
    relative_uncertainty = min(1.0, half_width / scale)
    confidence_score = max(0.0, 1.0 - relative_uncertainty)

    return PredictionUncertainty(
        confidence_score=confidence_score,
        low_confidence=confidence_score < low_confidence_threshold,
        confidence_level=confidence_level,
        interval_lower=lower,
        interval_upper=upper,
        uncertainty_width=upper - lower,
        probability_margin=None,
        entropy=None,
        method="validation_rmse_normal_interval",
    )


def _classification_uncertainty(
    explanation: PredictionExplanation,
    *,
    low_confidence_threshold: float,
) -> PredictionUncertainty:
    probability = float(explanation.output)
    if not isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("classification probability must be between 0 and 1")
    threshold = float(explanation.threshold if explanation.threshold is not None else 0.5)

    confidence_score = max(probability, 1.0 - probability)
    probability_margin = abs(probability - threshold)

    epsilon = 1e-15
    p = min(max(probability, epsilon), 1.0 - epsilon)
    entropy = -(p * log(p) + (1.0 - p) * log(1.0 - p)) / log(2.0)

    return PredictionUncertainty(
        confidence_score=confidence_score,
        low_confidence=confidence_score < low_confidence_threshold,
        confidence_level=None,
        interval_lower=None,
        interval_upper=None,
        uncertainty_width=None,
        probability_margin=probability_margin,
        entropy=entropy,
        method="class_probability_certainty",
    )


def estimate_uncertainty(
    model_row,
    explanation: PredictionExplanation,
    *,
    confidence_level: float = 0.95,
    low_confidence_threshold: float = 0.70,
) -> PredictionUncertainty:
    threshold = _validate_low_confidence_threshold(low_confidence_threshold)
    model = serialize_model(model_row)

    if model["algorithm"] == "linear_regression":
        return _regression_uncertainty(
            model,
            explanation,
            confidence_level=confidence_level,
            low_confidence_threshold=threshold,
        )
    if model["algorithm"] == "logistic_regression":
        return _classification_uncertainty(
            explanation,
            low_confidence_threshold=threshold,
        )
    raise ValueError("uncertainty estimation is supported for linear_regression and logistic_regression")
