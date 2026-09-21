from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import mean
from typing import Sequence

from app.services.ml.evaluation import binary_classification_metrics, regression_metrics
from app.services.ml.linear_regression import predict_linear
from app.services.ml.logistic_regression import predict_logistic
from app.services.ml.model_registry import serialize_model
from app.services.ml.preprocessing import transform_values


@dataclass(frozen=True)
class DriftResult:
    data_drift: dict
    performance_drift: dict | None
    drift_detected: bool
    retraining_recommended: bool


def summarize_numeric(values: Sequence[float]) -> dict[str, float]:
    if len(values) < 2:
        raise ValueError("at least two values are required")
    data = [float(v) for v in values]
    if not all(isfinite(v) for v in data):
        raise ValueError("values must contain only finite numbers")

    center = mean(data)
    variance = sum((value - center) ** 2 for value in data) / len(data)
    return {
        "count": float(len(data)),
        "mean": center,
        "std": sqrt(variance),
        "min": min(data),
        "max": max(data),
    }


def compare_numeric_distribution(
    reference: dict,
    current: Sequence[float],
    *,
    mean_shift_threshold: float = 1.0,
    std_ratio_threshold: float = 2.0,
) -> dict:
    if mean_shift_threshold <= 0 or std_ratio_threshold <= 1:
        raise ValueError("drift thresholds must be positive and std_ratio_threshold must exceed 1")

    current_stats = summarize_numeric(current)
    try:
        reference_mean = float(reference["mean"])
        reference_std = float(reference["std"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("reference baseline must contain numeric mean and std") from exc

    if not (isfinite(reference_mean) and isfinite(reference_std) and reference_std >= 0):
        raise ValueError("reference baseline mean/std must be finite and std must be non-negative")

    scale = reference_std if reference_std > 1e-12 else 1.0
    normalized_mean_shift = abs(current_stats["mean"] - reference_mean) / scale

    if reference_std <= 1e-12:
        std_ratio = 1.0 if current_stats["std"] <= 1e-12 else float("inf")
    else:
        std_ratio = current_stats["std"] / reference_std

    variance_drift = std_ratio >= std_ratio_threshold or std_ratio <= (1.0 / std_ratio_threshold)
    mean_drift = normalized_mean_shift >= mean_shift_threshold
    return {
        "reference": reference,
        "current": current_stats,
        "normalized_mean_shift": normalized_mean_shift,
        "std_ratio": std_ratio,
        "mean_drift": mean_drift,
        "variance_drift": variance_drift,
        "detected": mean_drift or variance_drift,
        "thresholds": {
            "mean_shift": mean_shift_threshold,
            "std_ratio": std_ratio_threshold,
        },
    }


def evaluate_model_performance(
    model: dict,
    x: Sequence[float],
    y: Sequence[float | int],
    *,
    degradation_threshold: float = 0.15,
) -> dict:
    if len(x) != len(y):
        raise ValueError("x and y must contain the same number of values")
    if not 0 < degradation_threshold < 1:
        raise ValueError("degradation_threshold must be between 0 and 1")

    algorithm = model.get("algorithm")
    artifact = model.get("artifact", {})
    validation_metrics = model.get("metrics", {}).get("validation", {})
    try:
        weight = float(artifact["weight"])
        bias = float(artifact["bias"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("model artifact must contain numeric weight and bias") from exc

    transformed_x = transform_values(x, artifact.get("preprocessing"))

    if algorithm == "linear_regression":
        predictions = predict_linear(transformed_x, weight=weight, bias=bias)
        current_metrics = regression_metrics(y, predictions)
        reference_metric = validation_metrics.get("rmse")
        current_metric = current_metrics["rmse"]
        if reference_metric is None:
            degradation = None
            degraded = False
        else:
            reference_metric = float(reference_metric)
            denominator = max(abs(reference_metric), 1e-12)
            degradation = (current_metric - reference_metric) / denominator
            degraded = degradation >= degradation_threshold
        primary_metric = "rmse"
    elif algorithm == "logistic_regression":
        threshold = float(artifact.get("threshold", 0.5))
        probabilities, _ = predict_logistic(transformed_x, weight=weight, bias=bias, threshold=threshold)
        current_metrics = binary_classification_metrics(y, probabilities, threshold=threshold)
        reference_metric = validation_metrics.get("f1")
        current_metric = current_metrics["f1"]
        if reference_metric is None:
            degradation = None
            degraded = False
        else:
            reference_metric = float(reference_metric)
            denominator = max(abs(reference_metric), 1e-12)
            degradation = (reference_metric - current_metric) / denominator
            degraded = degradation >= degradation_threshold
        primary_metric = "f1"
    else:
        raise ValueError("performance drift is supported for linear_regression and logistic_regression")

    return {
        "primary_metric": primary_metric,
        "reference_value": reference_metric,
        "current_value": current_metric,
        "degradation_fraction": degradation,
        "threshold": degradation_threshold,
        "degraded": degraded,
        "metrics": current_metrics,
    }


def monitor_model_drift(
    model_row,
    *,
    current_x: Sequence[float],
    current_y: Sequence[float | int] | None = None,
    mean_shift_threshold: float = 1.0,
    std_ratio_threshold: float = 2.0,
    performance_degradation_threshold: float = 0.15,
) -> DriftResult:
    model = serialize_model(model_row)
    baseline = model.get("metadata", {}).get("training_baseline", {}).get("x")
    if not isinstance(baseline, dict):
        raise ValueError("model does not contain a training data baseline")

    data_drift = compare_numeric_distribution(
        baseline,
        current_x,
        mean_shift_threshold=mean_shift_threshold,
        std_ratio_threshold=std_ratio_threshold,
    )
    performance_drift = None
    if current_y is not None:
        performance_drift = evaluate_model_performance(
            model,
            current_x,
            current_y,
            degradation_threshold=performance_degradation_threshold,
        )

    performance_detected = bool(performance_drift and performance_drift["degraded"])
    detected = data_drift["detected"] or performance_detected
    return DriftResult(
        data_drift=data_drift,
        performance_drift=performance_drift,
        drift_detected=detected,
        retraining_recommended=detected,
    )
