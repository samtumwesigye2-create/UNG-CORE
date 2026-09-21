from app.models.ml_model_registry import MLModelVersion
from app.services.ml.explainability import explain_prediction
from app.services.ml.prediction_audit import explanation_fingerprint


def _model():
    return MLModelVersion(
        model_key="audit-demo",
        version=4,
        algorithm="linear_regression",
        status="active",
        artifact_json='{"weight":2.0,"bias":1.0}',
        metrics_json="{}",
        metadata_json="{}",
        created_by="tester",
    )


def test_explanation_fingerprint_is_stable():
    explanation = explain_prediction(_model(), 3.0)
    first = explanation_fingerprint(explanation)
    second = explanation_fingerprint(explanation)

    assert first == second
    assert len(first) == 64


def test_explanation_fingerprint_changes_with_input():
    first = explanation_fingerprint(explain_prediction(_model(), 3.0))
    second = explanation_fingerprint(explain_prediction(_model(), 4.0))
    assert first != second
