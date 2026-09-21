from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ml.drift_monitoring import monitor_model_drift
from app.services.ml.model_registry import get_active_model, serialize_model
from app.services.ml.training_pipeline import run_training_pipeline


@dataclass(frozen=True)
class AutoRetrainingResult:
    model_key: str
    drift: dict
    retraining_started: bool
    candidate: dict | None
    promoted: bool
    previous_active_version: int | None
    active_version: int | None


async def run_controlled_auto_retraining(
    db: AsyncSession,
    *,
    model_key: str,
    x: Sequence[float],
    y: Sequence[float | int],
    actor_id: str,
    learning_rate: float = 0.01,
    epochs: int = 1000,
    test_fraction: float = 0.2,
    seed: int = 42,
    threshold: float = 0.5,
    gates: Sequence[dict] = (),
    mean_shift_threshold: float = 1.0,
    std_ratio_threshold: float = 2.0,
    performance_degradation_threshold: float = 0.15,
    promote_if_passed: bool = True,
    preprocessing: str = "standardize",
) -> AutoRetrainingResult:
    active = await get_active_model(db, model_key)
    if active is None:
        raise LookupError("active model not found")

    if len(x) != len(y):
        raise ValueError("x and y must contain the same number of values")
    if len(x) < 5:
        raise ValueError("at least five labeled samples are required for controlled retraining")

    drift = monitor_model_drift(
        active,
        current_x=x,
        current_y=y,
        mean_shift_threshold=mean_shift_threshold,
        std_ratio_threshold=std_ratio_threshold,
        performance_degradation_threshold=performance_degradation_threshold,
    )

    drift_payload = {
        "data_drift": drift.data_drift,
        "performance_drift": drift.performance_drift,
        "drift_detected": drift.drift_detected,
        "retraining_recommended": drift.retraining_recommended,
    }

    if not drift.retraining_recommended:
        return AutoRetrainingResult(
            model_key=model_key,
            drift=drift_payload,
            retraining_started=False,
            candidate=None,
            promoted=False,
            previous_active_version=active.version,
            active_version=active.version,
        )

    active_snapshot = serialize_model(active)
    algorithm = active_snapshot["algorithm"]
    candidate_result = await run_training_pipeline(
        db,
        model_key=model_key,
        algorithm=algorithm,
        x=x,
        y=y,
        created_by=actor_id,
        learning_rate=learning_rate,
        epochs=epochs,
        test_fraction=test_fraction,
        seed=seed,
        threshold=threshold,
        gates=gates,
        metadata={
            "retraining": {
                "trigger": "drift",
                "source_active_version": active.version,
                "drift": drift_payload,
            }
        },
        promote_if_passed=promote_if_passed,
        preprocessing=preprocessing,
    )

    latest_active = await get_active_model(db, model_key)
    return AutoRetrainingResult(
        model_key=model_key,
        drift=drift_payload,
        retraining_started=True,
        candidate=candidate_result.model,
        promoted=candidate_result.promoted,
        previous_active_version=active.version,
        active_version=latest_active.version if latest_active is not None else None,
    )
