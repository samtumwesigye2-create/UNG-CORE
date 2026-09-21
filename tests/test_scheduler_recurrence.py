import json
from datetime import datetime, timezone

import pytest

from app.models.scheduled_job import ScheduledJob
from app.services.scheduler import mark_job_result


class FakeSession:
    def __init__(self, row):
        self.row = row

    async def get(self, model, job_id):
        return self.row if self.row.job_id == job_id else None

    async def commit(self):
        return None

    async def refresh(self, row):
        return None


@pytest.mark.asyncio
async def test_recurring_job_is_rescheduled_after_success():
    now = datetime.now(timezone.utc)
    row = ScheduledJob(
        job_id="job-1",
        action="ml.health.evaluate",
        actor_id="tester",
        target_type="ml_health",
        target_id="global",
        system_key="ML",
        payload_json=json.dumps({"_repeat_interval_seconds": 300}),
        status="running",
        attempts=0,
        max_attempts=3,
        retry_delay_seconds=30,
        scheduled_for=now,
        next_attempt_at=now,
    )
    db = FakeSession(row)

    updated = await mark_job_result(db, "job-1", succeeded=True)

    assert updated.status == "scheduled"
    assert updated.attempts == 0
    assert updated.completed_at is None
    assert updated.next_attempt_at > now
    payload = json.loads(updated.payload_json)
    assert payload["_repeat_interval_seconds"] == 300
    assert payload["idempotency_key"].startswith("job:job-1:")


@pytest.mark.asyncio
async def test_non_recurring_job_remains_terminal_on_success():
    now = datetime.now(timezone.utc)
    row = ScheduledJob(
        job_id="job-2",
        action="event.publish",
        actor_id="tester",
        target_type="event",
        target_id=None,
        system_key="ML",
        payload_json="{}",
        status="running",
        attempts=0,
        max_attempts=3,
        retry_delay_seconds=30,
        scheduled_for=now,
        next_attempt_at=now,
    )
    db = FakeSession(row)

    updated = await mark_job_result(db, "job-2", succeeded=True)

    assert updated.status == "succeeded"
    assert updated.completed_at is not None
