import pytest

from app.models.ml_model_registry import MLModelVersion
from app.services.ml.explainability import explain_prediction
from app.services.ml.uncertainty import estimate_uncertainty


def _model(algorithm: str, artifact: str, metrics: str):
    return MLModelVersion(
        model_key="uncertainty-demo",
        version=2,
        algorithm=algorithm,
        status="active",
        artifact_json=artifact,
        metrics_json=metrics,
        metadata_json="{}",
        created_by="tester",
    )


def test_regression_uncertainty_uses_validation_rmse():
    row = _model(
        "linear_regression",
        '{"weight":2.0,"bias":1.0}',
        '{"validation":{"rmse":0.5}}',
    )
    explanation = explain_prediction(row, 3.0)
    result = estimate_uncertainty(row, explanation, confidence_level=0.95)

    assert result.interval_lower < explanation.output < result.interval_upper
    assert result.uncertainty_width == pytest.approx(2 * 1.959963984540054 * 0.5)
    assert result.method == "validation_rmse_normal_interval"


def test_regression_without_rmse_is_low_confidence():
    row = _model("linear_regression", '{"weight":2.0,"bias":1.0}', "{}")
    explanation = explain_prediction(row, 3.0)
    result = estimate_uncertainty(row, explanation)

    assert result.low_confidence is True
    assert result.interval_lower is None


def test_logistic_confidence_uses_class_probability():
    row = _model(
        "logistic_regression",
        '{"weight":4.0,"bias":-2.0,"threshold":0.5}',
        '{"validation":{"f1":0.9}}',
    )
    explanation = explain_prediction(row, 2.0)
    result = estimate_uncertainty(row, explanation, low_confidence_threshold=0.7)

    assert result.confidence_score > 0.9
    assert result.low_confidence is False
    assert result.probability_margin is not None
    assert result.entropy is not None


def test_near_threshold_logistic_prediction_is_low_confidence():
    row = _model(
        "logistic_regression",
        '{"weight":0.0,"bias":0.0,"threshold":0.5}',
        "{}",
    )
    explanation = explain_prediction(row, 1.0)
    result = estimate_uncertainty(row, explanation, low_confidence_threshold=0.7)

    assert result.confidence_score == pytest.approx(0.5)
    assert result.low_confidence is True
    assert result.entropy == pytest.approx(1.0)
