import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command_history import OperatorCommand


def _dump(value: dict | None) -> str:
    return json.dumps(value or {}, separators=(",", ":"), sort_keys=True)


def serialize_command(row: OperatorCommand) -> dict:
    return {
        "command_id": row.command_id,
        "actor_id": row.actor_id,
        "command": row.command,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "system_key": row.system_key,
        "correlation_id": row.correlation_id,
        "status": row.status,
        "result_code": row.result_code,
        "request": json.loads(row.request_json or "{}"),
        "before": json.loads(row.before_json or "{}"),
        "after": json.loads(row.after_json or "{}"),
        "result": json.loads(row.result_json or "{}"),
        "requested_at": row.requested_at,
        "completed_at": row.completed_at,
    }


async def record_command(
    db: AsyncSession,
    actor_id: str,
    command: str,
    target_type: str,
    target_id: str | None = None,
    system_key: str | None = None,
    correlation_id: str | None = None,
    request: dict | None = None,
    before: dict | None = None,
    after: dict | None = None,
    status: str = "accepted",
    result_code: int | None = None,
    result: dict | None = None,
    completed: bool = False,
) -> OperatorCommand:
    row = OperatorCommand(
        actor_id=actor_id,
        command=command,
        target_type=target_type,
        target_id=target_id,
        system_key=system_key.upper() if system_key else None,
        correlation_id=correlation_id,
        status=status,
        result_code=result_code,
        request_json=_dump(request),
        before_json=_dump(before),
        after_json=_dump(after),
        result_json=_dump(result),
        completed_at=datetime.now(timezone.utc) if completed else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def complete_command(db: AsyncSession, command_id: str, status: str, result_code: int | None = None, result: dict | None = None, after: dict | None = None) -> OperatorCommand:
    row = await db.get(OperatorCommand, command_id)
    if row is None:
        raise LookupError("command not found")
    row.status = status
    row.result_code = result_code
    row.result_json = _dump(result)
    if after is not None:
        row.after_json = _dump(after)
    row.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def list_commands(db: AsyncSession, actor_id: str | None = None, system_key: str | None = None, status: str | None = None, correlation_id: str | None = None, limit: int = 100) -> list[OperatorCommand]:
    stmt = select(OperatorCommand).order_by(OperatorCommand.requested_at.desc()).limit(limit)
    if actor_id:
        stmt = stmt.where(OperatorCommand.actor_id == actor_id)
    if system_key:
        stmt = stmt.where(OperatorCommand.system_key == system_key.upper())
    if status:
        stmt = stmt.where(OperatorCommand.status == status)
    if correlation_id:
        stmt = stmt.where(OperatorCommand.correlation_id == correlation_id)
    return list((await db.execute(stmt)).scalars().all())


async def command_summary(db: AsyncSession) -> dict:
    rows = await list_commands(db, limit=500)
    return {
        "total_recent": len(rows),
        "accepted": sum(r.status == "accepted" for r in rows),
        "succeeded": sum(r.status == "succeeded" for r in rows),
        "failed": sum(r.status == "failed" for r in rows),
        "unique_actors": len({r.actor_id for r in rows}),
    }
