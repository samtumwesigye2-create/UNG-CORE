import pytest

from app.services.ml.model_registry import (
    activate_model,
    get_active_model,
    list_models,
    register_model,
    retire_model,
    rollback_model,
)


class FakeSession:
    def __init__(self):
        self.ml_models = {}


async def _register(db, model_key="demand-forecast", algorithm="linear_trend"):
    return await register_model(
        db,
        model_key=model_key,
        algorithm=algorithm,
        artifact={"slope": 2.0, "intercept": 1.0},
        metrics={"rmse": 0.1},
        metadata={"dataset": "demo"},
        created_by="tester",
    )


@pytest.mark.asyncio
async def test_registration_assigns_incrementing_versions():
    db = FakeSession()
    first = await _register(db)
    second = await _register(db)
    assert first.version == 1
    assert second.version == 2
    assert [row.version for row in await list_models(db, "demand-forecast")] == [2, 1]


@pytest.mark.asyncio
async def test_activation_keeps_only_one_active_version():
    db = FakeSession()
    first = await _register(db)
    second = await _register(db)

    await activate_model(db, first.model_key, first.version)
    await activate_model(db, second.model_key, second.version)

    assert (await get_active_model(db, first.model_key)).version == 2
    assert first.status == "registered"
    assert second.status == "active"


@pytest.mark.asyncio
async def test_retired_model_cannot_be_activated():
    db = FakeSession()
    row = await _register(db)
    await retire_model(db, row.model_key, row.version)
    with pytest.raises(ValueError, match="retired"):
        await activate_model(db, row.model_key, row.version)


@pytest.mark.asyncio
async def test_rollback_activates_previous_non_retired_version():
    db = FakeSession()
    first = await _register(db)
    second = await _register(db)
    await activate_model(db, second.model_key, second.version)

    rolled_back = await rollback_model(db, second.model_key)

    assert rolled_back.version == first.version
    assert rolled_back.status == "active"
    assert second.status == "registered"


@pytest.mark.asyncio
async def test_rollback_requires_previous_version():
    db = FakeSession()
    only = await _register(db)
    await activate_model(db, only.model_key, only.version)
    with pytest.raises(ValueError, match="earlier"):
        await rollback_model(db, only.model_key)
