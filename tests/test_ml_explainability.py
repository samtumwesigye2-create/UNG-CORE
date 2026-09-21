from app.models.ml_model_registry import MLModelVersion
from app.services.ml.explainability import explain_batch, explain_prediction


def _model(algorithm: str, artifact: str):
    return MLModelVersion(
        model_key="demo",
        version=3,
        algorithm=algorithm,
        status="active",
        artifact_json=artifact,
        metrics_json="{}",
        metadata_json="{}",
        created_by="tester",
    )


def test_linear_explanation_shows_parameter_contributions():
    row = _model("linear_regression", '{"weight":2.0,"bias":1.0}')
    result = explain_prediction(row, 3.0)

    assert result.output == 7.0
    assert result.contributions["weighted_input"] == 6.0
    assert result.contributions["bias"] == 1.0
    assert result.classification is None
    assert "prediction is 7" in result.explanation.lower()


def test_logistic_explanation_returns_probability_and_class():
    row = _model("logistic_regression", '{"weight":2.0,"bias":-2.0,"threshold":0.5}')
    result = explain_prediction(row, 2.0)

    assert result.output > 0.5
    assert result.classification == 1
    assert result.threshold == 0.5
    assert "probability" in result.explanation.lower()


def test_batch_explainability_returns_one_result_per_input():
    row = _model("linear_regression", '{"weight":1.5,"bias":0.5}')
    results = explain_batch(row, [1, 2, 3])
    assert [item.output for item in results] == [2.0, 3.5, 5.0]
