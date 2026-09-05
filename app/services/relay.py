import httpx
from app.core.config import settings
from app.schemas.contracts import RelayEnvelope

async def publish(envelope: RelayEnvelope) -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.post(f"{settings.data_relay_base_url}/v1/events", json=envelope.model_dump())
        r.raise_for_status()
