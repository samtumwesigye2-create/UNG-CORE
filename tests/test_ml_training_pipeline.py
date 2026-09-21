import pytest

from app.services.ml.training_pipeline import run_training_pipeline


class FakeSession:
    def __init__(self):
        self.ml_models = {}


@pytest.mark.asyncio
async def test_linear_pipeline_registers_validates_and_promotes():
    db = FakeSession()
    result = await run_training_pipeline(
        db,
        model_key="linear-demo",
        algorithm="linear_regression",
        x=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        y=[3, 5, 7, 9, 11, 13, 15, 17, 19, 21],
        created_by="tester",
        learning_rate=0.01,
        epochs=5000,
        gates=[{"metric": "r2", "operator": "gte", "value": 0.95}],
        promote_if_passed=True,
    )

    assert result.evaluation["passed"] is True
    assert result.promoted is True
    assert result.model["status"] == "active"
    assert result.model["version"] == 1


@pytest.mark.asyncio
async def test_failed_gate_registers_but_does_not_promote():
    db = FakeSession()
    result = await run_training_pipeline(
        db,
        model_key="linear-demo",
        algorithm="linear_regression",
        x=[1, 2, 3, 4, 5, 6],
        y=[1, 2, 1, 2, 1, 2],
        created_by="tester",
        epochs=100,
        gates=[{"metric": "r2", "operator": "gte", "value": 0.99999}],
        promote_if_passed=True,
    )

    assert result.evaluation["passed"] is False
    assert result.promoted is False
    assert result.model["status"] == "registered"


@pytest.mark.asyncio
async def test_logistic_pipeline_trains_binary_classifier():
    db = FakeSession()
    result = await run_training_pipeline(
        db,
        model_key="binary-demo",
        algorithm="logistic_regression",
        x=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        y=[0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
        created_by="tester",
        learning_rate=0.1,
        epochs=3000,
        gates=[{"metric": "accuracy", "operator": "gte", "value": 0.8}],
    )

    assert result.task == "binary_classification"
    assert result.evaluation["metrics"]["accuracy"] >= 0.8
    assert result.model["version"] == 1


@pytest.mark.asyncio
async def test_pipeline_rejects_unsupported_algorithm():
    db = FakeSession()
    with pytest.raises(ValueError, match="algorithm"):
        await run_training_pipeline(
            db,
            model_key="bad",
            algorithm="neural_network",
            x=[1, 2, 3, 4, 5],
            y=[1, 2, 3, 4, 5],
            created_by="tester",
        )
