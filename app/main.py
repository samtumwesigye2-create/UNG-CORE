from fastapi import FastAPI
from app.api.routes import router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
import app.models.audit  # noqa

app = FastAPI(title=settings.app_name, version=settings.service_version)
app.include_router(router)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
