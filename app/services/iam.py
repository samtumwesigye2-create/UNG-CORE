import httpx
from app.core.config import settings
from app.schemas.contracts import Principal

async def resolve_principal(bearer_token: str) -> Principal:
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(f"{settings.iam_base_url}/v1/auth/me", headers={"Authorization": f"Bearer {bearer_token}"})
        r.raise_for_status()
        return Principal.model_validate(r.json())
