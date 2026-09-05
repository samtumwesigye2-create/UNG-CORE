from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models.audit  # noqa: F401
from app.api.routes import router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.service_version,
    lifespan=lifespan,
)
app.include_router(router)
