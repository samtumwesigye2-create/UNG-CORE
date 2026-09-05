from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.contracts import Principal
from app.services.iam import resolve_principal

bearer = HTTPBearer(auto_error=False)


async def current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    try:
        return await resolve_principal(credentials.credentials)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or unavailable identity") from exc


def require_permission(permission: str) -> Callable:
    async def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if permission not in principal.permissions and "ung.core.admin" not in principal.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")
        return principal

    return dependency
