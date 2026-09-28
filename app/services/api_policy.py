from __future__ import annotations
from dataclasses import dataclass
import time


@dataclass(frozen=True)
class RequestContext:
    service_identity: str
    role: str
    route: str
    body_bytes: int
    trace_id: str


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


class APIPolicyEngine:
    """Central authorization/rate/size policy core; transport middleware can call this."""

    def __init__(self, *, max_body_bytes: int = 1_048_576, requests_per_minute: int = 600) -> None:
        self.max_body_bytes=max_body_bytes
        self.requests_per_minute=requests_per_minute
        self._route_roles: dict[str,set[str]]={}
        self._buckets: dict[str,list[float]]={}

    def allow_roles(self, route: str, roles: set[str]) -> None:
        self._route_roles[route]=set(roles)

    def evaluate(self, request: RequestContext, *, now: float | None=None) -> PolicyDecision:
        if not request.service_identity:
            return PolicyDecision(False,"missing_service_identity")
        if request.body_bytes > self.max_body_bytes:
            return PolicyDecision(False,"request_too_large")
        allowed_roles=self._route_roles.get(request.route)
        if allowed_roles is not None and request.role not in allowed_roles:
            return PolicyDecision(False,"role_not_authorized")

        now=time.time() if now is None else now
        bucket=self._buckets.setdefault(request.service_identity,[])
        cutoff=now-60.0
        bucket[:]=[ts for ts in bucket if ts >= cutoff]
        if len(bucket) >= self.requests_per_minute:
            return PolicyDecision(False,"rate_limited")
        bucket.append(now)
        return PolicyDecision(True,"allowed")
