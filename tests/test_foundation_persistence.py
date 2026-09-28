import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
import app.models.foundation_state  # noqa: F401
from app.services.foundation_persistence import list_namespace, load_state, save_state


@pytest.mark.asyncio
async def test_foundation_state_round_trip_and_replace():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        await save_state(db, "config", "edge-1", {"version": "1"}, "tester")
        assert await load_state(db, "config", "edge-1") == {"version": "1"}
        await save_state(db, "config", "edge-1", {"version": "2"}, "tester")
        assert await load_state(db, "config", "edge-1") == {"version": "2"}
        rows = await list_namespace(db, "config")
        assert len(rows) == 1
    await engine.dispose()
