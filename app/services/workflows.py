import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import WorkflowExecution
from app.schemas.workflows import WorkflowStartIn


async def start_workflow(db: AsyncSession, body: WorkflowStartIn, requested_by: str) -> WorkflowExecution:
    row = WorkflowExecution(
        workflow_key=body.workflow_key,
        subject=body.subject,
        requested_by=requested_by,
        status="accepted",
        input_json=json.dumps(body.input, separators=(",", ":"), sort_keys=True),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_workflow(db: AsyncSession, execution_id: str) -> WorkflowExecution | None:
    return await db.get(WorkflowExecution, execution_id)


async def list_workflows(db: AsyncSession, limit: int = 100) -> list[WorkflowExecution]:
    result = await db.execute(select(WorkflowExecution).order_by(WorkflowExecution.created_at.desc()).limit(limit))
    return list(result.scalars().all())


def serialize_workflow(row: WorkflowExecution) -> dict:
    return {
        "execution_id": row.execution_id,
        "workflow_key": row.workflow_key,
        "subject": row.subject,
        "requested_by": row.requested_by,
        "status": row.status,
        "input": json.loads(row.input_json),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
