from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite
from typing import Sequence

from app.services.ml.model_registry import serialize_model
from app.services.ml.preprocessing import transform_value
from app.services.ml.calibration import apply_platt_calibration


@dataclass(frozen=True)
class PredictionExplanation:
    model_key: str
    model_version: int
    algorithm: str
    input_value: float
    output: float
    classification: int | None
    threshold: float | None
    contributions: dict[str, float]
    parameters: dict[str, object]
    explanation: str


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = exp(-value)
        return 1.0 / (1.0 + z)
    z = exp(value)
    return z / (1.0 + z)


def explain_prediction(model_row, value: float) -> PredictionExplanation:
    x = float(value)
    if not isfinite(x):
        raise ValueError("input value must be finite")

    model = serialize_model(model_row)
    artifact = model.get("artifact", {})
    try:
        weight = float(artifact["weight"])
        bias = float(artifact["bias"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("model artifact must contain numeric weight and bias") from exc

    if not (isfinite(weight) and isfinite(bias)):
        raise ValueError("model parameters must be finite")

    transformed_x = transform_value(x, artifact.get("preprocessing"))
    weighted_input = weight * transformed_x
    linear_score = weighted_input + bias

    if model["algorithm"] == "linear_regression":
        output = linear_score
        classification = None
        threshold = None
        explanation = (
            f"The prediction is {output:.6g}. The input contributes {weighted_input:.6g} "
            f"through weight {weight:.6g}, and the bias contributes {bias:.6g}."
        )
    elif model["algorithm"] == "logistic_regression":
        threshold = float(artifact.get("threshold", 0.5))
        if not 0.0 < threshold < 1.0:
            raise ValueError("logistic model threshold must be between 0 and 1")
        raw_probability = _sigmoid(linear_score)
        calibration = (model.get("metadata") or {}).get("probability_calibration")
        output = apply_platt_calibration(raw_probability, calibration)
        classification = 1 if output >= threshold else 0
        direction = "above" if classification == 1 else "below"
        explanation = (
            f"The model produced probability {output:.6g}, which is {direction} the "
            f"decision threshold {threshold:.6g}, so the class is {classification}. "
            f"The input contributes {weighted_input:.6g} to the logit and the bias contributes {bias:.6g}."
        )
    else:
        raise ValueError("explainability is supported for linear_regression and logistic_regression")

    return PredictionExplanation(
        model_key=model["model_key"],
        model_version=model["version"],
        algorithm=model["algorithm"],
        input_value=x,
        output=output,
        classification=classification,
        threshold=threshold,
        contributions={
            "weighted_input": weighted_input,
            "bias": bias,
            "linear_score": linear_score,
            "transformed_input": transformed_x,
        },
        parameters={
            "weight": weight,
            "bias": bias,
            "preprocessing": artifact.get("preprocessing", {"method": "none"}),
            "probability_calibration": (model.get("metadata") or {}).get("probability_calibration"),
        },
        explanation=explanation,
    )


def explain_batch(model_row, values: Sequence[float]) -> list[PredictionExplanation]:
    if not values:
        raise ValueError("at least one value is required")
    return [explain_prediction(model_row, value) for value in values]
