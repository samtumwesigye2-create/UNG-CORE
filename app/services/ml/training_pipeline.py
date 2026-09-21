from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ml.evaluation import evaluate_predictions, train_test_split_indices
from app.services.ml.linear_regression import predict_linear, train_linear_regression
from app.services.ml.logistic_regression import predict_logistic, train_logistic_regression
from app.services.ml.model_registry import (
    activate_model,
    get_active_model,
    record_validation,
    register_model,
    serialize_model,
)


SUPPORTED_ALGORITHMS = {"linear_regression", "logistic_regression"}


@dataclass(frozen=True)
class TrainingPipelineResult:
    algorithm: str
    task: str
    train_size: int
    test_size: int
    model: dict
    evaluation: dict
    promoted: bool
    previous_active_version: int | None


def _subset(values: Sequence, indices: Sequence[int]) -> list:
    return [values[index] for index in indices]


def _baseline_predictions(active, algorithm: str, test_x: list[float], threshold: float):
    if active is None or active.algorithm != algorithm:
        return None
    artifact = serialize_model(active)["artifact"]
    try:
        weight = float(artifact["weight"])
        bias = float(artifact["bias"])
    except (KeyError, TypeError, ValueError):
        return None

    if algorithm == "linear_regression":
        return predict_linear(test_x, weight=weight, bias=bias)
    probabilities, _ = predict_logistic(
        test_x,
        weight=weight,
        bias=bias,
        threshold=threshold,
    )
    return probabilities


async def run_training_pipeline(
    db: AsyncSession,
    *,
    model_key: str,
    algorithm: str,
    x: Sequence[float],
    y: Sequence[float | int],
    created_by: str,
    learning_rate: float = 0.01,
    epochs: int = 1000,
    test_fraction: float = 0.2,
    seed: int = 42,
    threshold: float = 0.5,
    gates: Sequence[dict] = (),
    metadata: dict | None = None,
    promote_if_passed: bool = False,
) -> TrainingPipelineResult:
    algorithm = algorithm.strip()
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError("algorithm must be 'linear_regression' or 'logistic_regression'")
    if len(x) != len(y):
        raise ValueError("x and y must contain the same number of values")
    if len(x) < 5:
        raise ValueError("at least five samples are required for the automated training pipeline")

    train_indices, test_indices = train_test_split_indices(
        len(x),
        test_fraction=test_fraction,
        seed=seed,
    )
    train_x = [float(v) for v in _subset(x, train_indices)]
    test_x = [float(v) for v in _subset(x, test_indices)]

    active = await get_active_model(db, model_key)
    previous_active_version = active.version if active is not None else None

    if algorithm == "linear_regression":
        train_y = [float(v) for v in _subset(y, train_indices)]
        test_y = [float(v) for v in _subset(y, test_indices)]
        trained = train_linear_regression(
            train_x,
            train_y,
            learning_rate=learning_rate,
            epochs=epochs,
        )
        artifact = {
            "weight": trained.weight,
            "bias": trained.bias,
            "learning_rate": trained.learning_rate,
            "epochs": trained.epochs,
        }
        test_predictions = predict_linear(
            test_x,
            weight=trained.weight,
            bias=trained.bias,
        )
        task = "regression"
        training_metrics = {"mse": trained.mse, "r2": trained.r2}
    else:
        train_y = [int(v) for v in _subset(y, train_indices)]
        test_y = [int(v) for v in _subset(y, test_indices)]
        trained = train_logistic_regression(
            train_x,
            train_y,
            learning_rate=learning_rate,
            epochs=epochs,
            threshold=threshold,
        )
        artifact = {
            "weight": trained.weight,
            "bias": trained.bias,
            "learning_rate": trained.learning_rate,
            "epochs": trained.epochs,
            "threshold": threshold,
        }
        test_predictions, _ = predict_logistic(
            test_x,
            weight=trained.weight,
            bias=trained.bias,
            threshold=threshold,
        )
        task = "binary_classification"
        training_metrics = {
            "log_loss": trained.log_loss,
            "accuracy": trained.accuracy,
        }

    baseline_predictions = _baseline_predictions(active, algorithm, test_x, threshold)
    evaluation = evaluate_predictions(
        task=task,
        actual=test_y,
        predicted=test_predictions,
        baseline_predicted=baseline_predictions,
        threshold=threshold,
        gates=gates,
    )

    model_metadata = dict(metadata or {})
    model_metadata["training_pipeline"] = {
        "seed": seed,
        "test_fraction": test_fraction,
        "train_size": len(train_indices),
        "test_size": len(test_indices),
        "previous_active_version": previous_active_version,
    }

    row = await register_model(
        db,
        model_key=model_key,
        algorithm=algorithm,
        artifact=artifact,
        metrics={"training": training_metrics},
        metadata=model_metadata,
        created_by=created_by,
    )
    row = await record_validation(
        db,
        model_key,
        row.version,
        task=evaluation.task,
        metrics=evaluation.metrics,
        baseline_metrics=evaluation.baseline_metrics,
        baseline_improvement=evaluation.baseline_improvement,
        gates=evaluation.gates,
        passed=evaluation.passed,
        validated_by=created_by,
    )

    promoted = False
    if promote_if_passed and evaluation.passed:
        row = await activate_model(db, model_key, row.version)
        promoted = True

    return TrainingPipelineResult(
        algorithm=algorithm,
        task=task,
        train_size=len(train_indices),
        test_size=len(test_indices),
        model=serialize_model(row),
        evaluation={
            "passed": evaluation.passed,
            "metrics": evaluation.metrics,
            "baseline_metrics": evaluation.baseline_metrics,
            "baseline_improvement": evaluation.baseline_improvement,
            "gates": evaluation.gates,
        },
        promoted=promoted,
        previous_active_version=previous_active_version,
    )
