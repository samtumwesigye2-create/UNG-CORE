import httpx

from app.core.config import settings
from app.schemas.contracts import Principal


async def resolve_principal(bearer_token: str) -> Principal:
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.post(
            f"{settings.iam_base_url}/v1/auth/introspect",
            headers={"Authorization": f"Bearer {bearer_token}"},
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("active"):
            raise httpx.HTTPStatusError(
                "inactive identity session",
                request=r.request,
                response=r,
            )
        identity = data.get("principal") or {}
        return Principal(
            subject=str(identity.get("subject") or identity.get("id")),
            display_name=identity.get("display_name"),
            roles=list(identity.get("roles") or []),
            permissions=list(identity.get("permissions") or []),
        )
