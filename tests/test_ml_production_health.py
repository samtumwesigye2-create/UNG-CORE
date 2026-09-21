from app.models.ml_model_registry import MLModelVersion
from app.services.ml.health_dashboard import summarize_ml_health
from app.services.ml.health_alerts import MLAlertThresholds, evaluate_ml_health_findings


def _active_linear():
    return MLModelVersion(
        model_key="prod-demo",
        version=3,
        algorithm="linear_regression",
        status="active",
        artifact_json='{"weight":1.0,"bias":0.0}',
        metrics_json='{"validation":{"rmse":1.0}}',
        metadata_json='{"validation":{"passed":true}}',
        created_by="tester",
    )


def _feedback():
    return {
        "action": "ml.prediction_feedback",
        "payload": {
            "model_key": "prod-demo",
            "model_version": 3,
            "algorithm": "linear_regression",
            "metrics": {"absolute_error": 2.0, "squared_error": 4.0},
        },
        "occurred_at": "2026-01-01T00:00:00",
    }


def test_health_dashboard_flags_degraded_production_model():
    events = [_feedback() for _ in range(20)]
    dashboard = summarize_ml_health([_active_linear()], events)

    assert dashboard["production_performance"]["degraded_count"] == 1
    gate = dashboard["production_performance"]["gates"][0]
    assert gate["status"] == "degraded"
    assert gate["passed"] is False


def test_health_alerts_include_production_degradation_finding():
    events = [_feedback() for _ in range(20)]
    findings = evaluate_ml_health_findings(
        [_active_linear()],
        events,
        MLAlertThresholds(),
    )
    states = {item["state"] for item in findings}
    assert "ml_production_performance_degraded" in states
