import pytest

from app.models.resource_catalog import ResourceRecord
from app.services.resource_catalog import ResourceConflict, find_resources, get_resource, register_resource


class FakeSession:
    def __init__(self):
        self.resources = {}


@pytest.mark.asyncio
async def test_register_and_get_resource():
    db = FakeSession()
    row = await register_resource(db, {"resource_id": "svc:vector", "resource_type": "service", "system_key": "UNG-VECTOR", "name": "VECTOR", "version": "1.0.0", "health_state": "healthy", "metadata": {"region": "primary"}, "dependencies": ["svc:pulsar"], "controllable": True})
    assert isinstance(row, ResourceRecord)
    assert (await get_resource(db, "svc:vector")).name == "VECTOR"


@pytest.mark.asyncio
async def test_duplicate_resource_id_is_rejected():
    db = FakeSession()
    payload = {"resource_id": "svc:nexus", "resource_type": "service", "system_key": "UNG-NEXUS", "name": "NEXUS"}
    await register_resource(db, payload)
    with pytest.raises(ResourceConflict):
        await register_resource(db, payload)


@pytest.mark.asyncio
async def test_find_resources_filters_text_and_type_and_sorts():
    db = FakeSession()
    await register_resource(db, {"resource_id": "db:vector", "resource_type": "database", "system_key": "UNG-VECTOR", "name": "Vector Primary"})
    await register_resource(db, {"resource_id": "svc:vector", "resource_type": "service", "system_key": "UNG-VECTOR", "name": "Vector API"})
    await register_resource(db, {"resource_id": "svc:ugaship", "resource_type": "service", "system_key": "UNG-UGASHIP", "name": "UGASHIP API"})
    rows = await find_resources(db, "vector", resource_type="service")
    assert [row.resource_id for row in rows] == ["svc:vector"]


@pytest.mark.asyncio
async def test_get_unknown_resource_returns_none():
    assert await get_resource(FakeSession(), "missing") is None
