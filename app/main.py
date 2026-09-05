import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

import app.models.audit  # noqa: F401
import app.models.service_registry  # noqa: F401
import app.models.service_heartbeat  # noqa: F401
import app.models.incident  # noqa: F401
from app.api.routes import router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.services.health_poller import health_poll_loop

@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    poller = None
    if settings.health_poll_enabled:
        poller = asyncio.create_task(health_poll_loop(max(10, settings.health_poll_interval_seconds)))

    yield

    if poller is not None:
        poller.cancel()
        with suppress(asyncio.CancelledError):
            await poller
    await engine.dispose()

app = FastAPI(title=settings.app_name, version=settings.service_version, lifespan=lifespan)
app.include_router(router)
