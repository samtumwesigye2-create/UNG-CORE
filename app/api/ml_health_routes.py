from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.audit import list_audit_events
from app.services.ml.health_dashboard import summarize_ml_health
from app.services.ml.model_registry import list_models

router = APIRouter(prefix="/v1/ml/health", tags=["machine-learning-health"])


@router.get("/dashboard")
async def ml_health_dashboard(
    event_limit: int = Query(default=1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_permission("ung.core.ml.monitor")),
):
    models = await list_models(db)
    events = await list_audit_events(db, limit=event_limit)
    return summarize_ml_health(models, events)
