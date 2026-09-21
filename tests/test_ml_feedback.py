import json

import pytest

from app.models.audit import AuditEvent
from app.services.ml.feedback import summarize_feedback_events


def _feedback(model_key, algorithm, metrics):
    return {
        "action": "ml.prediction_feedback",
        "payload": {
            "model_key": model_key,
            "algorithm": algorithm,
            "metrics": metrics,
        },
    }


def test_feedback_summary_regression_metrics():
    result = summarize_feedback_events([
        _feedback("r", "linear_regression", {"absolute_error": 1.0, "squared_error": 1.0}),
        _feedback("r", "linear_regression", {"absolute_error": 3.0, "squared_error": 9.0}),
    ])
    assert result["regression"]["mae"] == pytest.approx(2.0)
    assert result["regression"]["rmse"] == pytest.approx((5.0) ** 0.5)
    assert result["by_model"]["r"]["feedback_count"] == 2


def test_feedback_summary_classification_metrics():
    result = summarize_feedback_events([
        _feedback("c", "logistic_regression", {"correct": True, "brier_score": 0.04}),
        _feedback("c", "logistic_regression", {"correct": False, "brier_score": 0.64}),
    ])
    assert result["classification"]["accuracy"] == pytest.approx(0.5)
    assert result["classification"]["brier_score"] == pytest.approx(0.34)
    assert result["by_model"]["c"]["feedback_count"] == 2
