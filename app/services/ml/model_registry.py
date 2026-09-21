from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ml_model_registry import MLModelVersion


VALID_STATUSES = {"registered", "active", "retired"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def serialize_model(row: MLModelVersion) -> dict:
    return {
        "id": row.id,
        "model_key": row.model_key,
        "version": row.version,
        "algorithm": row.algorithm,
        "status": row.status,
        "artifact": json.loads(row.artifact_json or "{}"),
        "metrics": json.loads(row.metrics_json or "{}"),
        "metadata": json.loads(row.metadata_json or "{}"),
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
        "retired_at": row.retired_at.isoformat() if row.retired_at else None,
    }


async def _versions_for_key(db: AsyncSession, model_key: str) -> list[MLModelVersion]:
    if hasattr(db, "ml_models"):
        return sorted(
            [row for row in db.ml_models.values() if row.model_key == model_key],
            key=lambda row: row.version,
        )
    stmt = (
        select(MLModelVersion)
        .where(MLModelVersion.model_key == model_key)
        .order_by(MLModelVersion.version.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def register_model(
    db: AsyncSession,
    *,
    model_key: str,
    algorithm: str,
    artifact: dict,
    metrics: dict,
    metadata: dict,
    created_by: str,
) -> MLModelVersion:
    model_key = model_key.strip()
    algorithm = algorithm.strip()
    if not model_key:
        raise ValueError("model_key is required")
    if not algorithm:
        raise ValueError("algorithm is required")
    if not isinstance(artifact, dict) or not artifact:
        raise ValueError("artifact must be a non-empty object")
    if not isinstance(metrics, dict) or not isinstance(metadata, dict):
        raise ValueError("metrics and metadata must be objects")

    if hasattr(db, "ml_models"):
        versions = await _versions_for_key(db, model_key)
        next_version = (versions[-1].version + 1) if versions else 1
        row = MLModelVersion(
            model_key=model_key,
            version=next_version,
            algorithm=algorithm,
            status="registered",
            artifact_json=_serialize_json(artifact),
            metrics_json=_serialize_json(metrics),
            metadata_json=_serialize_json(metadata),
            created_by=created_by,
            created_at=_now(),
        )
        if row.id is None:
            import uuid
            row.id = str(uuid.uuid4())
        db.ml_models[row.id] = row
        return row

    stmt = select(func.max(MLModelVersion.version)).where(MLModelVersion.model_key == model_key)
    current = (await db.execute(stmt)).scalar_one_or_none()
    row = MLModelVersion(
        model_key=model_key,
        version=(current or 0) + 1,
        algorithm=algorithm,
        status="registered",
        artifact_json=_serialize_json(artifact),
        metrics_json=_serialize_json(metrics),
        metadata_json=_serialize_json(metadata),
        created_by=created_by,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_model(db: AsyncSession, model_key: str, version: int) -> MLModelVersion | None:
    if hasattr(db, "ml_models"):
        return next(
            (row for row in db.ml_models.values() if row.model_key == model_key and row.version == version),
            None,
        )
    stmt = select(MLModelVersion).where(
        MLModelVersion.model_key == model_key,
        MLModelVersion.version == version,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_active_model(db: AsyncSession, model_key: str) -> MLModelVersion | None:
    if hasattr(db, "ml_models"):
        return next(
            (row for row in db.ml_models.values() if row.model_key == model_key and row.status == "active"),
            None,
        )
    stmt = select(MLModelVersion).where(
        MLModelVersion.model_key == model_key,
        MLModelVersion.status == "active",
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_models(db: AsyncSession, model_key: str | None = None) -> list[MLModelVersion]:
    if hasattr(db, "ml_models"):
        rows = list(db.ml_models.values())
        if model_key:
            rows = [row for row in rows if row.model_key == model_key]
        return sorted(rows, key=lambda row: (row.model_key, -row.version))

    stmt = select(MLModelVersion)
    if model_key:
        stmt = stmt.where(MLModelVersion.model_key == model_key)
    stmt = stmt.order_by(MLModelVersion.model_key.asc(), MLModelVersion.version.desc())
    return list((await db.execute(stmt)).scalars().all())


async def activate_model(db: AsyncSession, model_key: str, version: int) -> MLModelVersion:
    target = await get_model(db, model_key, version)
    if target is None:
        raise LookupError("model version not found")
    if target.status == "retired":
        raise ValueError("retired model versions cannot be activated")

    now = _now()
    if hasattr(db, "ml_models"):
        for row in db.ml_models.values():
            if row.model_key == model_key and row.status == "active" and row.version != version:
                row.status = "registered"
                row.activated_at = None
        target.status = "active"
        target.activated_at = now
        return target

    await db.execute(
        update(MLModelVersion)
        .where(
            MLModelVersion.model_key == model_key,
            MLModelVersion.status == "active",
            MLModelVersion.version != version,
        )
        .values(status="registered", activated_at=None)
    )
    target.status = "active"
    target.activated_at = now
    await db.commit()
    await db.refresh(target)
    return target


async def retire_model(db: AsyncSession, model_key: str, version: int) -> MLModelVersion:
    target = await get_model(db, model_key, version)
    if target is None:
        raise LookupError("model version not found")
    target.status = "retired"
    target.retired_at = _now()
    target.activated_at = None
    if not hasattr(db, "ml_models"):
        await db.commit()
        await db.refresh(target)
    return target


async def rollback_model(db: AsyncSession, model_key: str) -> MLModelVersion:
    active = await get_active_model(db, model_key)
    if active is None:
        raise ValueError("no active model exists to roll back")

    versions = await _versions_for_key(db, model_key)
    candidates = [
        row for row in versions
        if row.version < active.version and row.status != "retired"
    ]
    if not candidates:
        raise ValueError("no earlier non-retired model version is available")
    previous = max(candidates, key=lambda row: row.version)
    return await activate_model(db, model_key, previous.version)
