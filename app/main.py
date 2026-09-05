import asyncio
from contextlib import asynccontextmanager, suppress
from fnmatch import fnmatch

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

import app.models.audit  # noqa: F401
import app.models.service_registry  # noqa: F401
import app.models.service_heartbeat  # noqa: F401
import app.models.incident  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.control_plane  # noqa: F401
import app.models.config_history  # noqa: F401
import app.models.gateway  # noqa: F401
import app.models.routing  # noqa: F401
import app.models.telemetry  # noqa: F401
import app.models.alerting  # noqa: F401
import app.models.command_history  # noqa: F401
import app.models.approval  # noqa: F401
import app.models.scheduled_job  # noqa: F401
import app.models.event_delivery  # noqa: F401
import app.models.security_resilience  # noqa: F401
from app.api.routes import router
from app.api.auth_routes import router as auth_router
from app.api.control_center_routes import router as control_center_router
from app.api.operator_routes import router as operator_router
from app.api.gateway_routes import router as gateway_router
from app.api.routing_routes import router as routing_router
from app.api.telemetry_routes import router as telemetry_router
from app.api.alerting_routes import router as alerting_router
from app.api.audit_command_routes import router as audit_command_router
from app.api.approval_routes import router as approval_router
from app.api.scheduler_routes import router as scheduler_router
from app.api.event_delivery_routes import router as event_delivery_router
from app.api.recovery_routes import router as recovery_router
from app.core.config import settings
from app.core.hardening import production_readiness
from app.db.base import Base
from app.db.session import engine
from app.services.health_poller import health_poll_loop
from app.services.registry_bootstrap import bootstrap_registry
from app.services.scheduler import scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    readiness = production_readiness()
    if settings.environment.lower() == "production" and not readiness["ready"]:
        failed = ", ".join(item["key"] for item in readiness["checks"] if not item["ok"])
        raise RuntimeError(f"production readiness checks failed: {failed}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.registry_bootstrap = await bootstrap_registry()
    poller = asyncio.create_task(health_poll_loop(max(10, settings.health_poll_interval_seconds))) if settings.health_poll_enabled else None
    scheduler = asyncio.create_task(scheduler_loop(max(1, settings.scheduler_interval_seconds))) if settings.scheduler_enabled else None
    yield
    for task in (poller, scheduler):
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    await engine.dispose()


app = FastAPI(title=settings.app_name, version=settings.service_version, lifespan=lifespan)
trusted_hosts = [item.strip().lower() for item in settings.trusted_hosts.split(",") if item.strip()]


def _host_allowed(host: str) -> bool:
    if not trusted_hosts or trusted_hosts == ["*"]:
        return True
    hostname = host.split(":", 1)[0].lower()
    return any(fnmatch(hostname, pattern) for pattern in trusted_hosts)


@app.middleware("http")
async def hardening_middleware(request: Request, call_next):
    if request.url.path not in {"/health", "/ready"}:
        host = request.headers.get("host", "")
        if not _host_allowed(host):
            return JSONResponse(status_code=400, content={"detail": "invalid host header"})

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.request_body_limit_bytes:
        return JSONResponse(status_code=413, content={"detail": "request body too large"})
    try:
        response = await asyncio.wait_for(call_next(request), timeout=settings.request_timeout_seconds)
    except asyncio.TimeoutError:
        return JSONResponse(status_code=504, content={"detail": "request timed out"})
    if settings.security_headers_enabled:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.environment.lower() == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/v1/control-center/ui", status_code=307)


app.include_router(router)
app.include_router(auth_router)
app.include_router(control_center_router)
app.include_router(operator_router)
app.include_router(gateway_router)
app.include_router(routing_router)
app.include_router(telemetry_router)
app.include_router(alerting_router)
app.include_router(audit_command_router)
app.include_router(approval_router)
app.include_router(scheduler_router)
app.include_router(event_delivery_router)
app.include_router(recovery_router)
