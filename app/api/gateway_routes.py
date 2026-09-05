from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.schemas.gateway import CorrelatedEventIn, GatewayRouteIn
from app.services.gateway import list_correlated_events, list_routes, record_correlated_event, serialize_correlated_event, serialize_route, upsert_route
from app.services.routing import correlate_and_route

router = APIRouter(prefix="/v1")


@router.put("/gateway/routes/{route_key}")
async def register_gateway_route(route_key: str, body: GatewayRouteIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.gateway.write"))):
    if route_key != body.route_key:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="route_key path/body mismatch")
    return serialize_route(await upsert_route(db, body))


@router.get("/gateway/routes")
async def gateway_routes(system_key: str | None = None, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.gateway.read"))):
    return [serialize_route(row) for row in await list_routes(db, system_key)]


@router.post("/events/correlated", status_code=status.HTTP_202_ACCEPTED)
async def create_correlated_event(body: CorrelatedEventIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.events.correlate"))):
    row = await record_correlated_event(db, body)
    routing = await correlate_and_route(db, row)
    return {"event": serialize_correlated_event(row), "routing": routing}


@router.get("/events/correlated")
async def correlated_events(correlation_id: str | None = None, incident_id: str | None = None, limit: int = Query(default=100, ge=1, le=500), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.events.read"))):
    return [serialize_correlated_event(row) for row in await list_correlated_events(db, correlation_id, incident_id, limit)]
