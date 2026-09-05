import fnmatch
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalDecision, ApprovalPolicy, ApprovalRequest


def _now() -> datetime:
    return datetime.now(timezone.utc)


def serialize_policy(row: ApprovalPolicy) -> dict:
    return {
        "policy_id": row.policy_id,
        "policy_key": row.policy_key,
        "action_pattern": row.action_pattern,
        "system_key": row.system_key,
        "required_approvals": row.required_approvals,
        "required_roles": json.loads(row.required_roles_json or "[]"),
        "expires_minutes": row.expires_minutes,
        "enabled": row.enabled,
    }


def serialize_request(row: ApprovalRequest) -> dict:
    return {
        "request_id": row.request_id,
        "policy_key": row.policy_key,
        "action": row.action,
        "actor_id": row.actor_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "system_key": row.system_key,
        "correlation_id": row.correlation_id,
        "context": json.loads(row.context_json or "{}"),
        "status": row.status,
        "required_approvals": row.required_approvals,
        "approval_count": row.approval_count,
        "requested_at": row.requested_at,
        "expires_at": row.expires_at,
        "decided_at": row.decided_at,
    }


async def upsert_policy(db: AsyncSession, policy_key: str, body) -> ApprovalPolicy:
    key = policy_key.lower()
    row = (await db.execute(select(ApprovalPolicy).where(ApprovalPolicy.policy_key == key))).scalar_one_or_none()
    values = {
        "action_pattern": body.action_pattern,
        "system_key": body.system_key.upper() if body.system_key else None,
        "required_approvals": body.required_approvals,
        "required_roles_json": json.dumps(body.required_roles),
        "expires_minutes": body.expires_minutes,
        "enabled": body.enabled,
    }
    if row is None:
        row = ApprovalPolicy(policy_key=key, **values)
        db.add(row)
    else:
        for field, value in values.items():
            setattr(row, field, value)
    await db.commit(); await db.refresh(row)
    return row


async def list_policies(db: AsyncSession) -> list[ApprovalPolicy]:
    return list((await db.execute(select(ApprovalPolicy).order_by(ApprovalPolicy.policy_key))).scalars().all())


async def matching_policy(db: AsyncSession, action: str, system_key: str | None) -> ApprovalPolicy | None:
    for policy in await list_policies(db):
        if not policy.enabled:
            continue
        if policy.system_key and policy.system_key != (system_key or "").upper():
            continue
        if fnmatch.fnmatchcase(action, policy.action_pattern):
            return policy
    return None


async def create_request(db: AsyncSession, policy: ApprovalPolicy, actor_id: str, action: str, target_type: str, target_id: str | None, system_key: str | None, correlation_id: str | None, context: dict) -> ApprovalRequest:
    now = _now()
    row = ApprovalRequest(
        policy_key=policy.policy_key,
        action=action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        system_key=system_key.upper() if system_key else None,
        correlation_id=correlation_id,
        context_json=json.dumps(context),
        required_approvals=policy.required_approvals,
        expires_at=now + timedelta(minutes=policy.expires_minutes),
    )
    db.add(row); await db.commit(); await db.refresh(row)
    return row


async def _refresh_expiry(db: AsyncSession, row: ApprovalRequest) -> ApprovalRequest:
    if row.status == "pending" and _now() >= row.expires_at.replace(tzinfo=row.expires_at.tzinfo or timezone.utc):
        row.status = "expired"
        row.decided_at = _now()
        await db.commit(); await db.refresh(row)
    return row


async def decide_request(db: AsyncSession, request_id: str, approver_id: str, approver_roles: list[str], decision: str, note: str | None = None) -> ApprovalRequest:
    row = await db.get(ApprovalRequest, request_id)
    if row is None:
        raise LookupError("approval request not found")
    row = await _refresh_expiry(db, row)
    if row.status != "pending":
        raise ValueError(f"approval request is {row.status}")
    if approver_id == row.actor_id:
        raise PermissionError("requester cannot approve own sensitive action")
    policy = (await db.execute(select(ApprovalPolicy).where(ApprovalPolicy.policy_key == row.policy_key))).scalar_one_or_none()
    required_roles = set(json.loads(policy.required_roles_json or "[]")) if policy else set()
    if required_roles and not required_roles.intersection(approver_roles):
        raise PermissionError("approver lacks required role")
    existing = (await db.execute(select(ApprovalDecision).where(ApprovalDecision.request_id == request_id, ApprovalDecision.approver_id == approver_id))).scalar_one_or_none()
    if existing is not None:
        raise ValueError("approver already decided")
    db.add(ApprovalDecision(request_id=request_id, approver_id=approver_id, decision=decision, roles_json=json.dumps(approver_roles), note=note))
    if decision == "deny":
        row.status = "denied"
        row.decided_at = _now()
    else:
        row.approval_count += 1
        if row.approval_count >= row.required_approvals:
            row.status = "approved"
            row.decided_at = _now()
    await db.commit(); await db.refresh(row)
    return row


async def get_request(db: AsyncSession, request_id: str) -> ApprovalRequest | None:
    row = await db.get(ApprovalRequest, request_id)
    return await _refresh_expiry(db, row) if row else None


async def list_requests(db: AsyncSession, status: str | None = None, system_key: str | None = None, limit: int = 100) -> list[ApprovalRequest]:
    stmt = select(ApprovalRequest).order_by(ApprovalRequest.requested_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    if system_key:
        stmt = stmt.where(ApprovalRequest.system_key == system_key.upper())
    rows = list((await db.execute(stmt)).scalars().all())
    result = []
    for row in rows:
        result.append(await _refresh_expiry(db, row))
    return result


async def assert_gate(db: AsyncSession, action: str, actor_id: str, target_type: str, target_id: str | None = None, system_key: str | None = None, correlation_id: str | None = None, context: dict | None = None, approval_request_id: str | None = None) -> dict:
    policy = await matching_policy(db, action, system_key)
    if policy is None:
        return {"allowed": True, "approval_required": False, "request": None}
    if approval_request_id:
        row = await get_request(db, approval_request_id)
        if row and row.actor_id == actor_id and row.action == action and row.target_type == target_type and row.target_id == target_id and row.status == "approved":
            return {"allowed": True, "approval_required": True, "request": serialize_request(row)}
        if row:
            return {"allowed": False, "approval_required": True, "request": serialize_request(row)}
    row = await create_request(db, policy, actor_id, action, target_type, target_id, system_key, correlation_id, context or {})
    return {"allowed": False, "approval_required": True, "request": serialize_request(row)}


async def approval_summary(db: AsyncSession) -> dict:
    rows = await list_requests(db, limit=500)
    return {
        "pending": sum(r.status == "pending" for r in rows),
        "approved": sum(r.status == "approved" for r in rows),
        "denied": sum(r.status == "denied" for r in rows),
        "expired": sum(r.status == "expired" for r in rows),
    }
