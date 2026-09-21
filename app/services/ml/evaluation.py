from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log
from random import Random
from typing import Literal, Sequence

Task = Literal["regression", "binary_classification"]
Operator = Literal["gte", "gt", "lte", "lt"]


@dataclass(frozen=True)
class EvaluationResult:
    task: Task
    metrics: dict[str, float]
    baseline_metrics: dict[str, float] | None
    baseline_improvement: dict[str, float] | None
    gates: list[dict]
    passed: bool


def train_test_split_indices(
    size: int,
    *,
    test_fraction: float = 0.2,
    seed: int = 42,
) -> tuple[list[int], list[int]]:
    if size < 3:
        raise ValueError("at least three samples are required")
    if not isfinite(test_fraction) or not 0.0 < test_fraction < 1.0:
        raise ValueError("test_fraction must be between 0 and 1")

    indices = list(range(size))
    Random(seed).shuffle(indices)
    test_size = max(1, min(size - 1, round(size * test_fraction)))
    test_indices = sorted(indices[:test_size])
    train_indices = sorted(indices[test_size:])
    return train_indices, test_indices


def _validate_same_length(actual: Sequence, predicted: Sequence) -> None:
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must have the same number of values")
    if not actual:
        raise ValueError("at least one evaluation sample is required")


def regression_metrics(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, float]:
    _validate_same_length(actual, predicted)
    y = [float(v) for v in actual]
    p = [float(v) for v in predicted]
    if not all(isfinite(v) for v in (*y, *p)):
        raise ValueError("regression values must contain only finite numbers")

    n = len(y)
    errors = [pred - target for target, pred in zip(y, p)]
    mse = sum(error * error for error in errors) / n
    mae = sum(abs(error) for error in errors) / n
    rmse = mse ** 0.5
    mean_y = sum(y) / n
    total = sum((value - mean_y) ** 2 for value in y)
    residual = sum((target - pred) ** 2 for target, pred in zip(y, p))
    r2 = 0.0 if total == 0 else 1.0 - residual / total
    return {"mae": mae, "mse": mse, "rmse": rmse, "r2": r2}


def binary_classification_metrics(
    actual: Sequence[int],
    probabilities: Sequence[float],
    *,
    threshold: float = 0.5,
) -> dict[str, float]:
    _validate_same_length(actual, probabilities)
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be between 0 and 1")
    y = [int(v) for v in actual]
    probs = [float(v) for v in probabilities]
    if any(v not in (0, 1) for v in y):
        raise ValueError("binary classification labels must be 0 or 1")
    if not all(isfinite(v) and 0.0 <= v <= 1.0 for v in probs):
        raise ValueError("probabilities must be finite values between 0 and 1")

    predictions = [1 if value >= threshold else 0 for value in probs]
    tp = sum(1 for target, pred in zip(y, predictions) if target == 1 and pred == 1)
    tn = sum(1 for target, pred in zip(y, predictions) if target == 0 and pred == 0)
    fp = sum(1 for target, pred in zip(y, predictions) if target == 0 and pred == 1)
    fn = sum(1 for target, pred in zip(y, predictions) if target == 1 and pred == 0)
    accuracy = (tp + tn) / len(y)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    epsilon = 1e-15
    log_loss = -sum(
        target * log(max(prob, epsilon)) + (1 - target) * log(max(1.0 - prob, epsilon))
        for target, prob in zip(y, probs)
    ) / len(y)
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "log_loss": log_loss,
    }


def _compare(actual: float, operator: Operator, target: float) -> bool:
    if operator == "gte":
        return actual >= target
    if operator == "gt":
        return actual > target
    if operator == "lte":
        return actual <= target
    if operator == "lt":
        return actual < target
    raise ValueError("gate operator must be one of: gte, gt, lte, lt")


def _metric_direction(task: Task, metric: str) -> int:
    if task == "regression":
        return 1 if metric == "r2" else -1
    return -1 if metric == "log_loss" else 1


def evaluate_predictions(
    *,
    task: Task,
    actual: Sequence,
    predicted: Sequence,
    baseline_predicted: Sequence | None = None,
    threshold: float = 0.5,
    gates: Sequence[dict] = (),
) -> EvaluationResult:
    if task == "regression":
        metrics = regression_metrics(actual, predicted)
        baseline_metrics = (
            regression_metrics(actual, baseline_predicted) if baseline_predicted is not None else None
        )
    elif task == "binary_classification":
        metrics = binary_classification_metrics(actual, predicted, threshold=threshold)
        baseline_metrics = (
            binary_classification_metrics(actual, baseline_predicted, threshold=threshold)
            if baseline_predicted is not None
            else None
        )
    else:
        raise ValueError("task must be 'regression' or 'binary_classification'")

    baseline_improvement = None
    if baseline_metrics is not None:
        baseline_improvement = {}
        for metric, value in metrics.items():
            if metric not in baseline_metrics:
                continue
            direction = _metric_direction(task, metric)
            baseline_improvement[metric] = direction * (value - baseline_metrics[metric])

    gate_results: list[dict] = []
    for gate in gates:
        metric = str(gate.get("metric", "")).strip()
        operator = str(gate.get("operator", "")).strip()
        target = gate.get("value")
        if metric not in metrics:
            raise ValueError(f"unknown metric in gate: {metric}")
        if operator not in {"gte", "gt", "lte", "lt"}:
            raise ValueError("gate operator must be one of: gte, gt, lte, lt")
        try:
            target_value = float(target)
        except (TypeError, ValueError) as exc:
            raise ValueError("gate value must be numeric") from exc
        if not isfinite(target_value):
            raise ValueError("gate value must be finite")
        actual_value = metrics[metric]
        passed = _compare(actual_value, operator, target_value)
        gate_results.append(
            {
                "metric": metric,
                "operator": operator,
                "value": target_value,
                "actual": actual_value,
                "passed": passed,
            }
        )

    if baseline_metrics is not None:
        primary = "rmse" if task == "regression" else "f1"
        baseline_passed = baseline_improvement is not None and baseline_improvement.get(primary, 0.0) >= 0.0
        gate_results.append(
            {
                "metric": f"baseline_{primary}",
                "operator": "gte",
                "value": 0.0,
                "actual": baseline_improvement.get(primary, 0.0) if baseline_improvement else 0.0,
                "passed": baseline_passed,
            }
        )

    return EvaluationResult(
        task=task,
        metrics=metrics,
        baseline_metrics=baseline_metrics,
        baseline_improvement=baseline_improvement,
        gates=gate_results,
        passed=all(item["passed"] for item in gate_results) if gate_results else True,
    )
