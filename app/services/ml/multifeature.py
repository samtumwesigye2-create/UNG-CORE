from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log, sqrt
from statistics import mean
from typing import Sequence


@dataclass(frozen=True)
class MatrixPreprocessor:
    method: str
    means: list[float]
    stds: list[float]


@dataclass(frozen=True)
class MultiFeatureModel:
    algorithm: str
    weights: list[float]
    bias: float
    preprocessing: MatrixPreprocessor
    threshold: float | None = None


def _validate_matrix(x: Sequence[Sequence[float]]) -> tuple[list[list[float]], int]:
    if len(x) < 2:
        raise ValueError("at least two samples are required")
    rows = [[float(v) for v in row] for row in x]
    width = len(rows[0]) if rows else 0
    if width < 2:
        raise ValueError("multi-feature models require at least two features")
    if any(len(row) != width for row in rows):
        raise ValueError("all feature rows must have the same width")
    if not all(isfinite(v) for row in rows for v in row):
        raise ValueError("features must contain only finite numbers")
    return rows, width


def fit_matrix_preprocessor(x: Sequence[Sequence[float]], method: str = "standardize") -> MatrixPreprocessor:
    rows, width = _validate_matrix(x)
    if method not in {"none", "standardize"}:
        raise ValueError("multi-feature preprocessing must be 'none' or 'standardize'")
    if method == "none":
        return MatrixPreprocessor(method="none", means=[0.0] * width, stds=[1.0] * width)

    means = [mean(row[j] for row in rows) for j in range(width)]
    stds = []
    for j in range(width):
        variance = mean((row[j] - means[j]) ** 2 for row in rows)
        std = sqrt(variance)
        if std <= 1e-12:
            raise ValueError(f"feature {j} has zero variance")
        stds.append(std)
    return MatrixPreprocessor(method="standardize", means=means, stds=stds)


def transform_matrix(x: Sequence[Sequence[float]], preprocessor: MatrixPreprocessor | dict) -> list[list[float]]:
    rows, width = _validate_matrix(x)
    if isinstance(preprocessor, dict):
        p = MatrixPreprocessor(
            method=str(preprocessor.get("method", "none")),
            means=[float(v) for v in preprocessor.get("means", [])],
            stds=[float(v) for v in preprocessor.get("stds", [])],
        )
    else:
        p = preprocessor
    if len(p.means) != width or len(p.stds) != width:
        raise ValueError("preprocessor width does not match feature width")
    return [
        [(row[j] - p.means[j]) / p.stds[j] for j in range(width)]
        for row in rows
    ]


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = exp(-value)
        return 1.0 / (1.0 + z)
    z = exp(value)
    return z / (1.0 + z)


def train_multifeature(
    x: Sequence[Sequence[float]],
    y: Sequence[float | int],
    *,
    algorithm: str,
    learning_rate: float = 0.01,
    epochs: int = 1000,
    threshold: float = 0.5,
    preprocessing: str = "standardize",
) -> tuple[MultiFeatureModel, dict]:
    rows, width = _validate_matrix(x)
    if len(rows) != len(y):
        raise ValueError("x and y must contain the same number of samples")
    if not isfinite(learning_rate) or learning_rate <= 0:
        raise ValueError("learning_rate must be positive and finite")
    if epochs < 1 or epochs > 100000:
        raise ValueError("epochs must be between 1 and 100000")
    p = fit_matrix_preprocessor(rows, preprocessing)
    tx = transform_matrix(rows, p)
    weights = [0.0] * width
    bias = 0.0
    n = float(len(rows))

    if algorithm == "multivariate_linear_regression":
        targets = [float(v) for v in y]
        if not all(isfinite(v) for v in targets):
            raise ValueError("targets must be finite")
        for _ in range(epochs):
            dw = [0.0] * width
            db = 0.0
            for row, target in zip(tx, targets):
                pred = sum(w * v for w, v in zip(weights, row)) + bias
                error = pred - target
                for j in range(width):
                    dw[j] += 2.0 * error * row[j] / n
                db += 2.0 * error / n
            weights = [w - learning_rate * g for w, g in zip(weights, dw)]
            bias -= learning_rate * db
        predictions = [sum(w * v for w, v in zip(weights, row)) + bias for row in tx]
        mse = mean((pred - target) ** 2 for pred, target in zip(predictions, targets))
        mean_y = mean(targets)
        total = sum((target - mean_y) ** 2 for target in targets)
        residual = sum((target - pred) ** 2 for target, pred in zip(targets, predictions))
        metrics = {"mse": mse, "rmse": sqrt(mse), "r2": None if total == 0 else 1.0 - residual / total}
        return MultiFeatureModel(algorithm, weights, bias, p, None), metrics

    if algorithm == "multivariate_logistic_regression":
        labels = [int(v) for v in y]
        if any(v not in (0, 1) for v in labels) or len(set(labels)) < 2:
            raise ValueError("logistic labels must contain both classes 0 and 1")
        if not 0.0 < threshold < 1.0:
            raise ValueError("threshold must be between 0 and 1")
        for _ in range(epochs):
            dw = [0.0] * width
            db = 0.0
            for row, target in zip(tx, labels):
                probability = _sigmoid(sum(w * v for w, v in zip(weights, row)) + bias)
                error = probability - target
                for j in range(width):
                    dw[j] += error * row[j] / n
                db += error / n
            weights = [w - learning_rate * g for w, g in zip(weights, dw)]
            bias -= learning_rate * db
        probabilities = [_sigmoid(sum(w * v for w, v in zip(weights, row)) + bias) for row in tx]
        predictions = [1 if p >= threshold else 0 for p in probabilities]
        eps = 1e-15
        loss = -mean(
            label * log(max(probability, eps)) + (1 - label) * log(max(1.0 - probability, eps))
            for probability, label in zip(probabilities, labels)
        )
        accuracy = mean(pred == label for pred, label in zip(predictions, labels))
        return MultiFeatureModel(algorithm, weights, bias, p, threshold), {"log_loss": loss, "accuracy": accuracy}

    raise ValueError("unsupported multi-feature algorithm")


def predict_multifeature(model: MultiFeatureModel | dict, x: Sequence[Sequence[float]]) -> dict:
    if isinstance(model, dict):
        pre = model.get("preprocessing") or {}
        model = MultiFeatureModel(
            algorithm=str(model["algorithm"]),
            weights=[float(v) for v in model["weights"]],
            bias=float(model["bias"]),
            preprocessing=MatrixPreprocessor(
                method=str(pre.get("method", "none")),
                means=[float(v) for v in pre.get("means", [])],
                stds=[float(v) for v in pre.get("stds", [])],
            ),
            threshold=float(model["threshold"]) if model.get("threshold") is not None else None,
        )
    tx = transform_matrix(x, model.preprocessing)
    if len(model.weights) != len(tx[0]):
        raise ValueError("model weight count does not match feature count")
    scores = [sum(w * v for w, v in zip(model.weights, row)) + model.bias for row in tx]
    if model.algorithm == "multivariate_linear_regression":
        return {"outputs": scores, "classifications": None}
    if model.algorithm == "multivariate_logistic_regression":
        threshold = model.threshold if model.threshold is not None else 0.5
        probabilities = [_sigmoid(score) for score in scores]
        return {
            "outputs": probabilities,
            "classifications": [1 if p >= threshold else 0 for p in probabilities],
        }
    raise ValueError("unsupported multi-feature algorithm")


def serialize_multifeature_model(model: MultiFeatureModel) -> dict:
    return {
        "algorithm": model.algorithm,
        "weights": model.weights,
        "bias": model.bias,
        "threshold": model.threshold,
        "preprocessing": {
            "method": model.preprocessing.method,
            "means": model.preprocessing.means,
            "stds": model.preprocessing.stds,
        },
        "feature_count": len(model.weights),
    }
