import pytest

from app.services.ml.evaluation import (
    binary_classification_metrics,
    evaluate_predictions,
    regression_metrics,
    train_test_split_indices,
)


def test_train_test_split_is_deterministic_and_complete():
    train_a, test_a = train_test_split_indices(10, test_fraction=0.2, seed=7)
    train_b, test_b = train_test_split_indices(10, test_fraction=0.2, seed=7)
    assert (train_a, test_a) == (train_b, test_b)
    assert sorted(train_a + test_a) == list(range(10))
    assert set(train_a).isdisjoint(test_a)


def test_regression_metrics_detect_good_fit():
    metrics = regression_metrics([1, 2, 3], [1.1, 1.9, 3.0])
    assert metrics["rmse"] < 0.1
    assert metrics["r2"] > 0.98


def test_binary_metrics_calculate_standard_scores():
    metrics = binary_classification_metrics([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    assert metrics["accuracy"] == 1.0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0


def test_evaluation_applies_metric_and_baseline_gates():
    result = evaluate_predictions(
        task="regression",
        actual=[1, 2, 3, 4],
        predicted=[1.0, 2.1, 2.9, 4.0],
        baseline_predicted=[2.5, 2.5, 2.5, 2.5],
        gates=[{"metric": "rmse", "operator": "lte", "value": 0.2}],
    )
    assert result.passed is True
    assert all(gate["passed"] for gate in result.gates)


def test_evaluation_fails_promotion_gate():
    result = evaluate_predictions(
        task="binary_classification",
        actual=[0, 0, 1, 1],
        predicted=[0.4, 0.6, 0.4, 0.6],
        gates=[{"metric": "accuracy", "operator": "gte", "value": 0.9}],
    )
    assert result.passed is False
