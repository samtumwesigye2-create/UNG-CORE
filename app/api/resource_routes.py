from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.resource_catalog import ResourceConflict, find_resources, get_resource, register_resource, serialize_resource

router = APIRouter(prefix="/v1/resources", tags=["resources"])


class ResourceIn(BaseModel):
    resource_id: str = Field(min_length=1, max_length=255)
    resource_type: str = Field(min_length=1, max_length=80)
    system_key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=255)
    version: str | None = None
    health_state: str = "unknown"
    metadata: dict = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    controllable: bool = False


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_resource(body: ResourceIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.registry.write"))):
    try:
        row = await register_resource(db, body.model_dump())
    except ResourceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_resource(row)


@router.get("/find")
async def search_resources(q: str = Query(default=""), resource_type: str | None = None, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.registry.read"))):
    rows = await find_resources(db, q, resource_type=resource_type)
    return {"count": len(rows), "resources": [serialize_resource(row) for row in rows]}


@router.get("/{resource_id:path}")
async def resource_detail(resource_id: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.registry.read"))):
    row = await get_resource(db, resource_id)
    if row is None:
        raise HTTPException(status_code=404, detail="resource not found")
    return serialize_resource(row)
