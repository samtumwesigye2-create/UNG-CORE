from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

from app.services.ml.ensemble import EnsemblePrediction, predict_ensemble
from app.services.ml.explainability import PredictionExplanation, explain_prediction
from app.services.ml.uncertainty import PredictionUncertainty, estimate_uncertainty


@dataclass(frozen=True)
class SinglePrediction:
    explanation: PredictionExplanation
    uncertainty: PredictionUncertainty


@dataclass(frozen=True)
class ServingPolicyResult:
    route: str
    selected_single: SinglePrediction | None
    selected_ensemble: EnsemblePrediction | None
    primary: SinglePrediction
    canary: SinglePrediction | None
    shadows: list[SinglePrediction]
    canary_selected: bool
    fallback_used: bool


def _bucket(routing_key: str) -> float:
    digest = hashlib.sha256(routing_key.encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big")
    return value / float(2**64 - 1)


def evaluate_serving_policy(
    *,
    primary_row,
    value: float,
    fallback_rows: Sequence = (),
    fallback_weights: Sequence[float] | None = None,
    ensemble_threshold: float = 0.5,
    canary_row=None,
    canary_percentage: float = 0.0,
    routing_key: str = "",
    shadow_rows: Sequence = (),
    confidence_level: float = 0.95,
    low_confidence_threshold: float = 0.70,
) -> ServingPolicyResult:
    if not 0.0 <= canary_percentage <= 1.0:
        raise ValueError("canary_percentage must be between 0 and 1")
    primary_explanation = explain_prediction(primary_row, value)
    primary_uncertainty = estimate_uncertainty(
        primary_row,
        primary_explanation,
        confidence_level=confidence_level,
        low_confidence_threshold=low_confidence_threshold,
    )
    primary = SinglePrediction(primary_explanation, primary_uncertainty)

    canary = None
    canary_selected = False
    if canary_row is not None:
        canary_explanation = explain_prediction(canary_row, value)
        if canary_explanation.algorithm != primary_explanation.algorithm:
            raise ValueError("canary model must use the same algorithm as primary")
        canary = SinglePrediction(
            canary_explanation,
            estimate_uncertainty(
                canary_row,
                canary_explanation,
                confidence_level=confidence_level,
                low_confidence_threshold=low_confidence_threshold,
            ),
        )
        canary_selected = bool(
            canary_percentage > 0
            and routing_key
            and _bucket(routing_key) < canary_percentage
        )

    selected_single = canary if canary_selected else primary
    selected_ensemble = None
    fallback_used = False
    route = "canary" if canary_selected else "primary"

    if selected_single.uncertainty.low_confidence and fallback_rows:
        selected_ensemble = predict_ensemble(
            fallback_rows,
            value,
            weights=fallback_weights,
            threshold=ensemble_threshold,
        )
        if selected_ensemble.algorithm != primary_explanation.algorithm:
            raise ValueError("fallback ensemble must use the same algorithm as primary")
        selected_single = None
        fallback_used = True
        route = "fallback_ensemble"

    shadows: list[SinglePrediction] = []
    for row in shadow_rows:
        explanation = explain_prediction(row, value)
        if explanation.algorithm != primary_explanation.algorithm:
            raise ValueError("shadow models must use the same algorithm as primary")
        shadows.append(
            SinglePrediction(
                explanation,
                estimate_uncertainty(
                    row,
                    explanation,
                    confidence_level=confidence_level,
                    low_confidence_threshold=low_confidence_threshold,
                ),
            )
        )

    return ServingPolicyResult(
        route=route,
        selected_single=selected_single,
        selected_ensemble=selected_ensemble,
        primary=primary,
        canary=canary,
        shadows=shadows,
        canary_selected=canary_selected,
        fallback_used=fallback_used,
    )
