from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.foundation_persistence import list_namespace, load_state, save_state

router = APIRouter(prefix="/v1/foundation/state", tags=["foundation-state"])


class FoundationStateIn(BaseModel):
    value: dict = Field(default_factory=dict)


@router.put("/{namespace}/{state_key}")
async def put_foundation_state(
    namespace: str,
    state_key: str,
    body: FoundationStateIn,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_permission("ung.core.config.write")),
):
    row = await save_state(db, namespace, state_key, body.value, principal.subject)
    return {"namespace": row.namespace, "state_key": row.state_key, "updated_at": row.updated_at, "updated_by": row.updated_by}


@router.get("/{namespace}/{state_key}")
async def get_foundation_state(
    namespace: str,
    state_key: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.config.read")),
):
    value = await load_state(db, namespace, state_key)
    if value is None:
        raise HTTPException(404, "foundation state not found")
    return {"namespace": namespace, "state_key": state_key, "value": value}


@router.get("/{namespace}")
async def foundation_namespace(
    namespace: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.config.read")),
):
    return await list_namespace(db, namespace)
