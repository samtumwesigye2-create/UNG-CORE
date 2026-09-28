from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.foundation_state import FoundationState


async def save_state(db: AsyncSession, namespace: str, state_key: str, value: dict[str, Any], updated_by: str) -> FoundationState:
    stmt = select(FoundationState).where(
        FoundationState.namespace == namespace,
        FoundationState.state_key == state_key,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    now = datetime.now(timezone.utc)
    if row is None:
        row = FoundationState(namespace=namespace, state_key=state_key, value_json=encoded, updated_by=updated_by, updated_at=now)
        db.add(row)
    else:
        row.value_json = encoded
        row.updated_by = updated_by
        row.updated_at = now
    await db.commit()
    await db.refresh(row)
    return row


async def load_state(db: AsyncSession, namespace: str, state_key: str) -> dict[str, Any] | None:
    stmt = select(FoundationState).where(
        FoundationState.namespace == namespace,
        FoundationState.state_key == state_key,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    return None if row is None else json.loads(row.value_json)


async def list_namespace(db: AsyncSession, namespace: str) -> list[dict[str, Any]]:
    stmt = select(FoundationState).where(FoundationState.namespace == namespace).order_by(FoundationState.state_key)
    rows = list((await db.execute(stmt)).scalars().all())
    return [
        {
            "namespace": row.namespace,
            "state_key": row.state_key,
            "value": json.loads(row.value_json),
            "updated_by": row.updated_by,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]
