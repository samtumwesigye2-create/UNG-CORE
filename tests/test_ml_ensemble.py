import pytest

from app.models.ml_model_registry import MLModelVersion
from app.services.ml.ensemble import predict_ensemble


def _model(key: str, version: int, algorithm: str, artifact: str):
    return MLModelVersion(
        model_key=key,
        version=version,
        algorithm=algorithm,
        status="active",
        artifact_json=artifact,
        metrics_json="{}",
        metadata_json="{}",
        created_by="tester",
    )


def test_linear_ensemble_averages_member_predictions():
    rows = [
        _model("a", 1, "linear_regression", '{"weight":2.0,"bias":1.0}'),
        _model("b", 1, "linear_regression", '{"weight":4.0,"bias":-1.0}'),
    ]
    result = predict_ensemble(rows, 3.0)

    assert result.output == pytest.approx((7.0 + 11.0) / 2)
    assert result.member_count == 2
    assert result.classification is None
    assert result.method == "weighted_mean"


def test_weighted_linear_ensemble_respects_weights():
    rows = [
        _model("a", 1, "linear_regression", '{"weight":1.0,"bias":0.0}'),
        _model("b", 1, "linear_regression", '{"weight":3.0,"bias":0.0}'),
    ]
    result = predict_ensemble(rows, 2.0, weights=[1, 3])
    assert result.output == pytest.approx(5.0)


def test_logistic_ensemble_returns_consensus():
    rows = [
        _model("a", 1, "logistic_regression", '{"weight":4.0,"bias":-2.0,"threshold":0.5}'),
        _model("b", 1, "logistic_regression", '{"weight":3.0,"bias":-1.0,"threshold":0.5}'),
    ]
    result = predict_ensemble(rows, 2.0, threshold=0.5)

    assert result.output > 0.5
    assert result.classification == 1
    assert result.agreement_fraction == pytest.approx(1.0)
    assert result.method == "weighted_probability_consensus"


def test_ensemble_rejects_mixed_algorithms():
    rows = [
        _model("a", 1, "linear_regression", '{"weight":1.0,"bias":0.0}'),
        _model("b", 1, "logistic_regression", '{"weight":1.0,"bias":0.0,"threshold":0.5}'),
    ]
    with pytest.raises(ValueError, match="same algorithm"):
        predict_ensemble(rows, 1.0)
