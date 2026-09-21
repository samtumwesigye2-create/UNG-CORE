from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import pstdev
from typing import Sequence

from app.services.ml.explainability import PredictionExplanation, explain_prediction


@dataclass(frozen=True)
class EnsembleMemberPrediction:
    model_key: str
    model_version: int
    algorithm: str
    weight: float
    output: float
    classification: int | None
    threshold: float | None
    explanation: str


@dataclass(frozen=True)
class EnsemblePrediction:
    algorithm: str
    input_value: float
    output: float
    classification: int | None
    threshold: float | None
    member_count: int
    members: list[EnsembleMemberPrediction]
    output_spread: float
    agreement_fraction: float | None
    method: str


def predict_ensemble(
    model_rows: Sequence,
    value: float,
    *,
    weights: Sequence[float] | None = None,
    threshold: float = 0.5,
) -> EnsemblePrediction:
    if len(model_rows) < 2:
        raise ValueError("an ensemble requires at least two models")

    x = float(value)
    if not isfinite(x):
        raise ValueError("input value must be finite")

    explanations: list[PredictionExplanation] = [
        explain_prediction(row, x) for row in model_rows
    ]
    algorithms = {item.algorithm for item in explanations}
    if len(algorithms) != 1:
        raise ValueError("ensemble members must use the same algorithm")
    algorithm = next(iter(algorithms))

    if weights is None:
        normalized_weights = [1.0 / len(explanations)] * len(explanations)
    else:
        if len(weights) != len(explanations):
            raise ValueError("weights must match the number of ensemble members")
        raw = [float(weight) for weight in weights]
        if not all(isfinite(weight) and weight > 0 for weight in raw):
            raise ValueError("ensemble weights must be finite positive numbers")
        total = sum(raw)
        normalized_weights = [weight / total for weight in raw]

    if not 0.0 < threshold < 1.0:
        raise ValueError("ensemble threshold must be between 0 and 1")

    output = sum(
        weight * explanation.output
        for weight, explanation in zip(normalized_weights, explanations)
    )
    spread = pstdev([explanation.output for explanation in explanations])

    if algorithm == "linear_regression":
        classification = None
        ensemble_threshold = None
        agreement_fraction = None
        method = "weighted_mean"
    elif algorithm == "logistic_regression":
        ensemble_threshold = threshold
        classification = 1 if output >= threshold else 0
        member_classes = [
            1 if explanation.output >= threshold else 0
            for explanation in explanations
        ]
        agreement_fraction = (
            sum(member == classification for member in member_classes)
            / len(member_classes)
        )
        method = "weighted_probability_consensus"
    else:
        raise ValueError("ensemble prediction supports linear_regression and logistic_regression")

    members = [
        EnsembleMemberPrediction(
            model_key=explanation.model_key,
            model_version=explanation.model_version,
            algorithm=explanation.algorithm,
            weight=weight,
            output=explanation.output,
            classification=explanation.classification,
            threshold=explanation.threshold,
            explanation=explanation.explanation,
        )
        for weight, explanation in zip(normalized_weights, explanations)
    ]

    return EnsemblePrediction(
        algorithm=algorithm,
        input_value=x,
        output=output,
        classification=classification,
        threshold=ensemble_threshold,
        member_count=len(members),
        members=members,
        output_spread=spread,
        agreement_fraction=agreement_fraction,
        method=method,
    )
