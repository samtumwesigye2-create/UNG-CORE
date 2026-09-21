from app.models.ml_model_registry import MLModelVersion
from app.services.ml.health_dashboard import summarize_ml_health


def _model(key, status="active", algorithm="linear_regression"):
    return MLModelVersion(
        model_key=key,
        version=1,
        algorithm=algorithm,
        status=status,
        artifact_json='{"weight":1.0,"bias":0.0}',
        metrics_json='{"validation":{"rmse":0.2}}',
        metadata_json='{"validation":{"passed":true}}',
        created_by="tester",
    )


def test_health_dashboard_aggregates_prediction_and_serving_metrics():
    models = [_model("a"), _model("b", status="registered")]
    events = [
        {
            "action": "ml.prediction",
            "payload": {"uncertainty": {"confidence_score": 0.8, "low_confidence": False}},
            "occurred_at": "2026-01-01T00:00:00",
        },
        {
            "action": "ml.prediction",
            "payload": {"uncertainty": {"confidence_score": 0.6, "low_confidence": True}},
            "occurred_at": "2026-01-01T00:00:01",
        },
        {
            "action": "ml.serving_policy_prediction",
            "payload": {
                "route": "fallback_ensemble",
                "fallback_used": True,
                "canary_selected": False,
                "primary": {"output": 10.0},
                "shadows": [{"output": 12.0}],
            },
            "occurred_at": "2026-01-01T00:00:02",
        },
    ]

    result = summarize_ml_health(models, events)
    assert result["models"]["active_count"] == 1
    assert result["predictions"]["single_count"] == 2
    assert result["predictions"]["average_confidence"] == 0.7
    assert result["predictions"]["low_confidence_rate"] == 0.5
    assert result["serving"]["fallback_rate"] == 1.0
    assert result["serving"]["average_shadow_absolute_difference"] == 2.0


def test_health_dashboard_keeps_latest_drift_per_model():
    result = summarize_ml_health(
        [_model("a")],
        [
            {
                "action": "ml.drift_check",
                "payload": {"model_key": "a", "model_version": 1, "drift_detected": False},
                "occurred_at": "2026-01-01T00:00:00",
            },
            {
                "action": "ml.drift_check",
                "payload": {"model_key": "a", "model_version": 1, "drift_detected": True, "retraining_recommended": True},
                "occurred_at": "2026-01-02T00:00:00",
            },
        ],
    )
    assert result["drift"]["check_count"] == 2
    assert result["drift"]["latest_by_model"]["a"]["drift_detected"] is True
    assert result["drift"]["models_with_detected_drift"] == 1
