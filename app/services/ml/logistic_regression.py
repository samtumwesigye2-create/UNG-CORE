from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log
from typing import Sequence


_EPSILON = 1e-15


@dataclass(frozen=True)
class LogisticRegressionResult:
    weight: float
    bias: float
    epochs: int
    learning_rate: float
    log_loss: float
    accuracy: float
    probabilities: list[float]
    predictions: list[int]


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = exp(-value)
        return 1.0 / (1.0 + z)
    z = exp(value)
    return z / (1.0 + z)


def _validate(xs: Sequence[float], ys: Sequence[int], learning_rate: float, epochs: int) -> None:
    if len(xs) != len(ys):
        raise ValueError("x and y must contain the same number of values")
    if len(xs) < 2:
        raise ValueError("at least two training points are required")
    if not all(isfinite(float(v)) for v in xs):
        raise ValueError("training data must contain only finite numbers")
    if any(v not in (0, 1) for v in ys):
        raise ValueError("logistic regression labels must be 0 or 1")
    if len(set(ys)) < 2:
        raise ValueError("training labels must contain both classes 0 and 1")
    if not isfinite(learning_rate) or learning_rate <= 0:
        raise ValueError("learning_rate must be a finite number greater than zero")
    if epochs < 1 or epochs > 100_000:
        raise ValueError("epochs must be between 1 and 100000")


def train_logistic_regression(
    xs: Sequence[float],
    ys: Sequence[int],
    *,
    learning_rate: float = 0.01,
    epochs: int = 1000,
    threshold: float = 0.5,
) -> LogisticRegressionResult:
    """Train a binary logistic-regression classifier with batch gradient descent."""
    _validate(xs, ys, learning_rate, epochs)
    if not isfinite(threshold) or not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be between 0 and 1")

    x = [float(v) for v in xs]
    y = [int(v) for v in ys]
    n = float(len(x))
    weight = 0.0
    bias = 0.0

    for _ in range(epochs):
        dw = 0.0
        db = 0.0
        for xi, yi in zip(x, y):
            probability = _sigmoid(weight * xi + bias)
            error = probability - yi
            dw += error * xi / n
            db += error / n
        weight -= learning_rate * dw
        bias -= learning_rate * db
        if not (isfinite(weight) and isfinite(bias)):
            raise ValueError("training diverged; reduce learning_rate or normalize the input data")

    probabilities = [_sigmoid(weight * xi + bias) for xi in x]
    predictions = [1 if p >= threshold else 0 for p in probabilities]
    loss = -sum(
        yi * log(max(p, _EPSILON)) + (1 - yi) * log(max(1.0 - p, _EPSILON))
        for yi, p in zip(y, probabilities)
    ) / n
    accuracy = sum(pred == yi for pred, yi in zip(predictions, y)) / n

    return LogisticRegressionResult(
        weight=weight,
        bias=bias,
        epochs=epochs,
        learning_rate=learning_rate,
        log_loss=loss,
        accuracy=accuracy,
        probabilities=probabilities,
        predictions=predictions,
    )


def predict_logistic(
    xs: Sequence[float],
    *,
    weight: float,
    bias: float,
    threshold: float = 0.5,
) -> tuple[list[float], list[int]]:
    if not (isfinite(weight) and isfinite(bias)):
        raise ValueError("weight and bias must be finite")
    if not isfinite(threshold) or not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be between 0 and 1")
    if not all(isfinite(float(v)) for v in xs):
        raise ValueError("prediction data must contain only finite numbers")

    probabilities = [_sigmoid(weight * float(x) + bias) for x in xs]
    predictions = [1 if p >= threshold else 0 for p in probabilities]
    return probabilities, predictions
