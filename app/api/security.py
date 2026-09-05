from collections.abc import Callable

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.contracts import Principal
from app.services.iam import resolve_principal

bearer = HTTPBearer(auto_error=False)
SESSION_COOKIE = "ung_core_session"


async def current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Principal:
    token = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif session_token:
        token = session_token
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="UNG operator sign-in required")
    try:
        return await resolve_principal(token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired UNG identity session") from exc


def require_permission(permission: str) -> Callable:
    async def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if permission not in principal.permissions and "ung.core.admin" not in principal.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")
        return principal

    return dependency
