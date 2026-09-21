from app.models.ml_model_registry import MLModelVersion
from app.services.ml.health_alerts import MLAlertThresholds, evaluate_ml_health_findings


def _model(validation_passed=True):
    return MLModelVersion(
        model_key="demo",
        version=1,
        algorithm="linear_regression",
        status="active",
        artifact_json='{"weight":1.0,"bias":0.0}',
        metrics_json='{"validation":{"rmse":0.2}}',
        metadata_json='{"validation":{"passed":' + ("true" if validation_passed else "false") + '}}',
        created_by="tester",
    )


def test_health_alerts_detect_confidence_fallback_and_divergence():
    events = [
        {
            "action": "ml.prediction",
            "payload": {"uncertainty": {"confidence_score": 0.4, "low_confidence": True}},
            "occurred_at": "2026-01-01T00:00:00",
        },
        {
            "action": "ml.serving_policy_prediction",
            "payload": {
                "route": "fallback_ensemble",
                "fallback_used": True,
                "canary_selected": True,
                "primary": {"output": 1.0},
                "canary": {"output": 2.0},
                "shadows": [{"output": 2.0}],
            },
            "occurred_at": "2026-01-01T00:00:01",
        },
    ]
    findings = evaluate_ml_health_findings(
        [_model()],
        events,
        MLAlertThresholds(
            minimum_average_confidence=0.7,
            maximum_low_confidence_rate=0.2,
            maximum_fallback_rate=0.2,
            maximum_shadow_difference=0.2,
            maximum_canary_difference=0.2,
        ),
    )
    states = {item["state"] for item in findings}
    assert "ml_confidence_low" in states
    assert "ml_low_confidence_rate_high" in states
    assert "ml_fallback_rate_high" in states
    assert "ml_shadow_divergence" in states
    assert "ml_canary_divergence" in states


def test_health_alerts_detect_drift_and_failed_active_validation():
    events = [
        {
            "action": "ml.drift_check",
            "payload": {
                "model_key": "demo",
                "model_version": 1,
                "drift_detected": True,
                "retraining_recommended": True,
            },
            "occurred_at": "2026-01-02T00:00:00",
        }
    ]
    findings = evaluate_ml_health_findings(
        [_model(validation_passed=False)],
        events,
        MLAlertThresholds(),
    )
    states = {item["state"] for item in findings}
    assert "ml_drift_detected" in states
    assert "ml_active_validation_failed" in states
