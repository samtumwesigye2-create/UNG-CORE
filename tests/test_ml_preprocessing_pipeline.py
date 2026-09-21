import pytest

from app.models.ml_model_registry import MLModelVersion
from app.services.ml.explainability import explain_prediction
from app.services.ml.training_pipeline import run_training_pipeline


class FakeSession:
    def __init__(self):
        self.ml_models = {}


@pytest.mark.asyncio
async def test_training_pipeline_persists_standardization_and_inference_reuses_it():
    db = FakeSession()
    result = await run_training_pipeline(
        db,
        model_key="scaled-linear",
        algorithm="linear_regression",
        x=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        y=[21, 41, 61, 81, 101, 121, 141, 161, 181, 201],
        created_by="tester",
        epochs=5000,
        preprocessing="standardize",
    )

    artifact = result.model["artifact"]
    assert artifact["preprocessing"]["method"] == "standardize"
    assert artifact["preprocessing"]["mean"] is not None
    assert artifact["preprocessing"]["std"] > 0

    row = next(iter(db.ml_models.values()))
    explanation = explain_prediction(row, 55)
    transformed = (55 - artifact["preprocessing"]["mean"]) / artifact["preprocessing"]["std"]
    expected = artifact["weight"] * transformed + artifact["bias"]

    assert explanation.output == pytest.approx(expected)
    assert explanation.contributions["transformed_input"] == pytest.approx(transformed)


@pytest.mark.asyncio
async def test_training_pipeline_supports_minmax_preprocessing():
    db = FakeSession()
    result = await run_training_pipeline(
        db,
        model_key="minmax-linear",
        algorithm="linear_regression",
        x=[1, 2, 3, 4, 5, 6],
        y=[3, 5, 7, 9, 11, 13],
        created_by="tester",
        epochs=5000,
        preprocessing="minmax",
    )
    assert result.model["artifact"]["preprocessing"]["method"] == "minmax"


def test_legacy_model_without_preprocessing_remains_identity_compatible():
    row = MLModelVersion(
        model_key="legacy",
        version=1,
        algorithm="linear_regression",
        status="active",
        artifact_json='{"weight":2.0,"bias":1.0}',
        metrics_json="{}",
        metadata_json="{}",
        created_by="tester",
    )
    result = explain_prediction(row, 3)
    assert result.output == 7.0
    assert result.parameters["preprocessing"]["method"] == "none"
