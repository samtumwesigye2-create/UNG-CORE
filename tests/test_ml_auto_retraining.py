import pytest

from app.services.ml.auto_retraining import run_controlled_auto_retraining
from app.services.ml.model_registry import activate_model, record_validation, register_model


class FakeSession:
    def __init__(self):
        self.ml_models = {}


async def _active_linear_model(db):
    row = await register_model(
        db,
        model_key="demo",
        algorithm="linear_regression",
        artifact={"weight": 2.0, "bias": 1.0, "learning_rate": 0.01, "epochs": 1000},
        metrics={"validation": {"rmse": 0.1, "r2": 0.99}},
        metadata={
            "training_baseline": {
                "x": {
                    "count": 5.0,
                    "mean": 3.0,
                    "std": 1.41421356237,
                    "min": 1.0,
                    "max": 5.0,
                }
            }
        },
        created_by="tester",
    )
    await record_validation(
        db,
        "demo",
        row.version,
        task="regression",
        metrics={"rmse": 0.1, "r2": 0.99},
        baseline_metrics=None,
        baseline_improvement=None,
        gates=[],
        passed=True,
        validated_by="tester",
    )
    return await activate_model(db, "demo", row.version)


@pytest.mark.asyncio
async def test_no_drift_does_not_retrain():
    db = FakeSession()
    active = await _active_linear_model(db)

    result = await run_controlled_auto_retraining(
        db,
        model_key="demo",
        x=[1, 2, 3, 4, 5],
        y=[3, 5, 7, 9, 11],
        actor_id="tester",
    )

    assert result.retraining_started is False
    assert result.promoted is False
    assert result.active_version == active.version
    assert len(db.ml_models) == 1


@pytest.mark.asyncio
async def test_drift_creates_candidate_and_promotes_when_gates_pass():
    db = FakeSession()
    active = await _active_linear_model(db)
    # Simulate an active model that has become stale relative to the new regime.
    active.artifact_json = '{"weight":1.0,"bias":0.0,"learning_rate":0.01,"epochs":1000}'

    x = [20, 21, 22, 23, 24, 25, 26, 27, 28, 29]
    y = [2 * value + 1 for value in x]
    result = await run_controlled_auto_retraining(
        db,
        model_key="demo",
        x=x,
        y=y,
        actor_id="tester",
        learning_rate=0.0005,
        epochs=5000,
        gates=[{"metric": "r2", "operator": "gte", "value": 0.95}],
        promote_if_passed=True,
    )

    assert result.retraining_started is True
    assert result.candidate is not None
    assert result.promoted is True
    assert result.previous_active_version == active.version
    assert result.active_version == 2


@pytest.mark.asyncio
async def test_drift_candidate_stays_inactive_when_gate_fails():
    db = FakeSession()
    active = await _active_linear_model(db)

    x = [20, 21, 22, 23, 24, 25]
    y = [1, 2, 1, 2, 1, 2]
    result = await run_controlled_auto_retraining(
        db,
        model_key="demo",
        x=x,
        y=y,
        actor_id="tester",
        epochs=100,
        gates=[{"metric": "r2", "operator": "gte", "value": 0.99999}],
        promote_if_passed=True,
    )

    assert result.retraining_started is True
    assert result.promoted is False
    assert result.active_version == active.version
    assert result.candidate["status"] == "registered"
