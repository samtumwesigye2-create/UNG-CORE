from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.approvals import decide_request, get_request, list_policies, list_requests, serialize_policy, serialize_request, upsert_policy

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


class ApprovalPolicyIn(BaseModel):
    action_pattern: str = Field(min_length=1, max_length=160)
    system_key: str | None = None
    required_approvals: int = Field(default=1, ge=1, le=10)
    required_roles: list[str] = Field(default_factory=list)
    expires_minutes: int = Field(default=60, ge=1, le=10080)
    enabled: bool = True


class DecisionIn(BaseModel):
    decision: str
    note: str | None = None


@router.put("/policies/{policy_key}")
async def set_policy(policy_key: str, body: ApprovalPolicyIn, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.approvals.policy.write"))):
    return serialize_policy(await upsert_policy(db, policy_key, body))


@router.get("/policies")
async def policies(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.approvals.read"))):
    return [serialize_policy(row) for row in await list_policies(db)]


@router.get("/requests")
async def requests(status: str | None = None, system_key: str | None = None, limit: int = Query(default=100, ge=1, le=500), db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.approvals.read"))):
    return [serialize_request(row) for row in await list_requests(db, status, system_key, limit)]


@router.get("/requests/{request_id}")
async def request(request_id: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.approvals.read"))):
    row = await get_request(db, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="approval request not found")
    return serialize_request(row)


@router.post("/requests/{request_id}/decision")
async def decide(request_id: str, body: DecisionIn, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.approvals.decide"))):
    if body.decision not in {"approve", "deny"}:
        raise HTTPException(status_code=400, detail="decision must be approve or deny")
    try:
        row = await decide_request(db, request_id, principal.subject, principal.roles, body.decision, body.note)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="approval request not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_request(row)
