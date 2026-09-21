import pytest

from app.models.ml_model_registry import MLModelVersion
from app.services.ml.production_performance import evaluate_production_performance


def _model(algorithm, metrics):
    return MLModelVersion(
        model_key="demo",
        version=2,
        algorithm=algorithm,
        status="registered",
        artifact_json='{"weight":1.0,"bias":0.0}',
        metrics_json=metrics,
        metadata_json='{"validation":{"passed":true}}',
        created_by="tester",
    )


def _feedback(metrics):
    return {
        "action": "ml.prediction_feedback",
        "payload": {
            "model_key": "demo",
            "model_version": 2,
            "metrics": metrics,
        },
    }


def test_linear_production_gate_detects_rmse_degradation():
    model = _model("linear_regression", '{"validation":{"rmse":1.0}}')
    feedback = [_feedback({"squared_error": 4.0}) for _ in range(20)]
    gate = evaluate_production_performance(
        model,
        feedback,
        minimum_feedback=20,
        maximum_degradation_fraction=0.25,
    )
    assert gate.production_value == pytest.approx(2.0)
    assert gate.degradation_fraction == pytest.approx(1.0)
    assert gate.degraded is True
    assert gate.passed is False


def test_logistic_production_gate_detects_accuracy_degradation():
    model = _model("logistic_regression", '{"validation":{"accuracy":0.9}}')
    feedback = [
        _feedback({"correct": index < 12, "brier_score": 0.2})
        for index in range(20)
    ]
    gate = evaluate_production_performance(
        model,
        feedback,
        minimum_feedback=20,
        maximum_degradation_fraction=0.20,
    )
    assert gate.production_value == pytest.approx(0.6)
    assert gate.degraded is True
    assert gate.passed is False


def test_production_gate_is_nonblocking_when_feedback_is_insufficient():
    model = _model("linear_regression", '{"validation":{"rmse":1.0}}')
    gate = evaluate_production_performance(
        model,
        [_feedback({"squared_error": 100.0})],
        minimum_feedback=20,
    )
    assert gate.status == "insufficient_feedback"
    assert gate.passed is True
