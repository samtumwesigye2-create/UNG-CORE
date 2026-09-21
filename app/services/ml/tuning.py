from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import isfinite
from random import Random
from statistics import mean
from typing import Sequence

from app.services.ml.evaluation import binary_classification_metrics, regression_metrics
from app.services.ml.linear_regression import predict_linear, train_linear_regression
from app.services.ml.logistic_regression import predict_logistic, train_logistic_regression
from app.services.ml.preprocessing import fit_preprocessor, transform_values


@dataclass(frozen=True)
class TuningResult:
    algorithm: str
    task: str
    folds: int
    primary_metric: str
    best_params: dict
    best_score: float
    trials: list[dict]


def kfold_indices(size: int, *, folds: int = 5, seed: int = 42) -> list[tuple[list[int], list[int]]]:
    if folds < 2:
        raise ValueError("folds must be at least 2")
    if size < folds:
        raise ValueError("number of samples must be at least the number of folds")
    indices = list(range(size))
    Random(seed).shuffle(indices)
    buckets = [indices[i::folds] for i in range(folds)]
    result = []
    for i in range(folds):
        validation = sorted(buckets[i])
        training = sorted(index for j, bucket in enumerate(buckets) if j != i for index in bucket)
        result.append((training, validation))
    return result


def _validate_grid(values: Sequence, name: str) -> list:
    items = list(values)
    if not items:
        raise ValueError(f"{name} search space cannot be empty")
    return items


def tune_hyperparameters(
    *,
    algorithm: str,
    x: Sequence[float],
    y: Sequence[float | int],
    learning_rates: Sequence[float] = (0.01,),
    epochs_options: Sequence[int] = (1000,),
    thresholds: Sequence[float] = (0.5,),
    preprocessing_options: Sequence[str] = ("standardize",),
    folds: int = 5,
    seed: int = 42,
) -> TuningResult:
    if len(x) != len(y):
        raise ValueError("x and y must contain the same number of values")
    if algorithm not in {"linear_regression", "logistic_regression"}:
        raise ValueError("unsupported algorithm for tuning")

    learning_rates = _validate_grid(learning_rates, "learning_rates")
    epochs_options = _validate_grid(epochs_options, "epochs_options")
    preprocessing_options = _validate_grid(preprocessing_options, "preprocessing_options")
    thresholds = _validate_grid(thresholds, "thresholds")
    splits = kfold_indices(len(x), folds=folds, seed=seed)

    task = "regression" if algorithm == "linear_regression" else "binary_classification"
    primary_metric = "rmse" if task == "regression" else "f1"
    trials: list[dict] = []

    threshold_space = [None] if algorithm == "linear_regression" else thresholds
    for learning_rate, epochs, threshold, preprocessing in product(
        learning_rates, epochs_options, threshold_space, preprocessing_options
    ):
        learning_rate = float(learning_rate)
        epochs = int(epochs)
        if not isfinite(learning_rate) or learning_rate <= 0:
            raise ValueError("learning rates must be finite and greater than zero")
        if epochs < 1 or epochs > 100000:
            raise ValueError("epoch options must be between 1 and 100000")
        if threshold is not None and not 0.0 < float(threshold) < 1.0:
            raise ValueError("threshold options must be between 0 and 1")

        fold_scores: list[float] = []
        fold_metrics: list[dict] = []
        for train_indices, validation_indices in splits:
            raw_train_x = [float(x[i]) for i in train_indices]
            raw_validation_x = [float(x[i]) for i in validation_indices]
            preprocessor = fit_preprocessor(raw_train_x, method=preprocessing)
            train_x = transform_values(raw_train_x, preprocessor)
            validation_x = transform_values(raw_validation_x, preprocessor)

            if algorithm == "linear_regression":
                train_y = [float(y[i]) for i in train_indices]
                validation_y = [float(y[i]) for i in validation_indices]
                trained = train_linear_regression(
                    train_x, train_y, learning_rate=learning_rate, epochs=epochs
                )
                predictions = predict_linear(validation_x, weight=trained.weight, bias=trained.bias)
                metrics = regression_metrics(validation_y, predictions)
                score = metrics["rmse"]
            else:
                train_y = [int(y[i]) for i in train_indices]
                validation_y = [int(y[i]) for i in validation_indices]
                trained = train_logistic_regression(
                    train_x,
                    train_y,
                    learning_rate=learning_rate,
                    epochs=epochs,
                    threshold=float(threshold),
                )
                probabilities, _ = predict_logistic(
                    validation_x,
                    weight=trained.weight,
                    bias=trained.bias,
                    threshold=float(threshold),
                )
                metrics = binary_classification_metrics(
                    validation_y, probabilities, threshold=float(threshold)
                )
                score = metrics["f1"]

            fold_scores.append(score)
            fold_metrics.append(metrics)

        params = {
            "learning_rate": learning_rate,
            "epochs": epochs,
            "preprocessing": preprocessing,
        }
        if threshold is not None:
            params["threshold"] = float(threshold)
        trials.append(
            {
                "params": params,
                "score": mean(fold_scores),
                "fold_scores": fold_scores,
                "fold_metrics": fold_metrics,
            }
        )

    if task == "regression":
        best = min(trials, key=lambda item: item["score"])
    else:
        best = max(trials, key=lambda item: item["score"])

    return TuningResult(
        algorithm=algorithm,
        task=task,
        folds=folds,
        primary_metric=primary_metric,
        best_params=best["params"],
        best_score=best["score"],
        trials=trials,
    )
