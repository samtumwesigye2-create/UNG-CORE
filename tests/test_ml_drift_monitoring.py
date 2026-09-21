from app.models.ml_model_registry import MLModelVersion
from app.services.ml.drift_monitoring import (
    compare_numeric_distribution,
    monitor_model_drift,
    summarize_numeric,
)


def _model(metadata_json: str, metrics_json: str, algorithm: str = "linear_regression"):
    return MLModelVersion(
        model_key="demo",
        version=1,
        algorithm=algorithm,
        status="active",
        artifact_json='{"weight":2.0,"bias":1.0,"threshold":0.5}',
        metrics_json=metrics_json,
        metadata_json=metadata_json,
        created_by="tester",
    )


def test_summarize_numeric_calculates_baseline():
    stats = summarize_numeric([1, 2, 3, 4])
    assert stats["mean"] == 2.5
    assert stats["std"] > 1.0


def test_distribution_shift_is_flagged():
    reference = summarize_numeric([1, 2, 3, 4, 5])
    result = compare_numeric_distribution(reference, [20, 21, 22, 23, 24])
    assert result["detected"] is True
    assert result["mean_drift"] is True


def test_no_drift_for_similar_distribution():
    reference = summarize_numeric([1, 2, 3, 4, 5])
    result = compare_numeric_distribution(reference, [1.1, 2.1, 3.1, 4.1, 5.1])
    assert result["detected"] is False


def test_monitor_flags_performance_degradation():
    row = _model(
        '{"training_baseline":{"x":{"count":5.0,"mean":3.0,"std":1.41421356237,"min":1.0,"max":5.0}}}',
        '{"validation":{"rmse":0.1}}',
    )
    result = monitor_model_drift(
        row,
        current_x=[1, 2, 3, 4, 5],
        current_y=[100, 100, 100, 100, 100],
    )
    assert result.performance_drift is not None
    assert result.performance_drift["degraded"] is True
    assert result.retraining_recommended is True
