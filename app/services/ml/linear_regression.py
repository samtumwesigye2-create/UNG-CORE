from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class LinearRegressionResult:
    weight: float
    bias: float
    epochs: int
    learning_rate: float
    mse: float
    r2: float | None
    predictions: list[float]


def _validate(xs: Sequence[float], ys: Sequence[float], learning_rate: float, epochs: int) -> None:
    if len(xs) != len(ys):
        raise ValueError("x and y must contain the same number of values")
    if len(xs) < 2:
        raise ValueError("at least two training points are required")
    if not all(isfinite(float(v)) for v in (*xs, *ys)):
        raise ValueError("training data must contain only finite numbers")
    if not isfinite(learning_rate) or learning_rate <= 0:
        raise ValueError("learning_rate must be a finite number greater than zero")
    if epochs < 1 or epochs > 100_000:
        raise ValueError("epochs must be between 1 and 100000")


def train_linear_regression(
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    learning_rate: float = 0.01,
    epochs: int = 1000,
) -> LinearRegressionResult:
    """Train y = weight*x + bias with batch gradient descent."""
    _validate(xs, ys, learning_rate, epochs)

    x = [float(v) for v in xs]
    y = [float(v) for v in ys]
    n = float(len(x))
    weight = 0.0
    bias = 0.0

    for _ in range(epochs):
        dw = 0.0
        db = 0.0
        for xi, yi in zip(x, y):
            error = (weight * xi + bias) - yi
            dw += 2.0 * error * xi / n
            db += 2.0 * error / n
        weight -= learning_rate * dw
        bias -= learning_rate * db

        if not (isfinite(weight) and isfinite(bias)):
            raise ValueError("training diverged; reduce learning_rate or normalize the input data")

    predictions = [weight * xi + bias for xi in x]
    mse = sum((pred - yi) ** 2 for pred, yi in zip(predictions, y)) / n
    mean_y = sum(y) / n
    total_variance = sum((yi - mean_y) ** 2 for yi in y)
    residual_variance = sum((yi - pred) ** 2 for yi, pred in zip(y, predictions))
    r2 = None if total_variance == 0 else 1.0 - (residual_variance / total_variance)

    return LinearRegressionResult(
        weight=weight,
        bias=bias,
        epochs=epochs,
        learning_rate=learning_rate,
        mse=mse,
        r2=r2,
        predictions=predictions,
    )


def predict_linear(xs: Sequence[float], *, weight: float, bias: float) -> list[float]:
    if not (isfinite(weight) and isfinite(bias)):
        raise ValueError("weight and bias must be finite")
    if not all(isfinite(float(v)) for v in xs):
        raise ValueError("prediction data must contain only finite numbers")
    return [weight * float(x) + bias for x in xs]
