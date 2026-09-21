from app.models.ml_model_registry import MLModelVersion
from app.services.ml.serving_policy import evaluate_serving_policy


def _model(key, algorithm, artifact, metrics='{"validation":{"rmse":0.1,"f1":0.9}}'):
    return MLModelVersion(
        model_key=key,
        version=1,
        algorithm=algorithm,
        status="active",
        artifact_json=artifact,
        metrics_json=metrics,
        metadata_json="{}",
        created_by="tester",
    )


def test_low_confidence_primary_uses_fallback_ensemble():
    primary = _model("p", "linear_regression", '{"weight":1.0,"bias":0.0}', '{"validation":{"rmse":10.0}}')
    a = _model("a", "linear_regression", '{"weight":2.0,"bias":0.0}')
    b = _model("b", "linear_regression", '{"weight":4.0,"bias":0.0}')
    result = evaluate_serving_policy(primary_row=primary, value=2, fallback_rows=[a,b])
    assert result.route == "fallback_ensemble"
    assert result.selected_ensemble is not None
    assert result.fallback_used is True


def test_canary_selection_is_deterministic():
    primary = _model("p", "linear_regression", '{"weight":1.0,"bias":0.0}')
    canary = _model("c", "linear_regression", '{"weight":2.0,"bias":0.0}')
    first = evaluate_serving_policy(primary_row=primary, value=2, canary_row=canary, canary_percentage=0.5, routing_key="abc")
    second = evaluate_serving_policy(primary_row=primary, value=2, canary_row=canary, canary_percentage=0.5, routing_key="abc")
    assert first.canary_selected == second.canary_selected


def test_shadow_predictions_do_not_change_selected_route():
    primary = _model("p", "logistic_regression", '{"weight":4.0,"bias":-2.0,"threshold":0.5}', '{}')
    shadow = _model("s", "logistic_regression", '{"weight":1.0,"bias":0.0,"threshold":0.5}', '{}')
    result = evaluate_serving_policy(primary_row=primary, value=2, shadow_rows=[shadow], low_confidence_threshold=0.5)
    assert result.route == "primary"
    assert len(result.shadows) == 1
