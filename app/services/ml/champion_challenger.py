from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import mean
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import list_audit_events
from app.services.ml.model_registry import get_active_model, get_model, list_models, serialize_model
from app.services.ml.production_performance import (
    activate_model_with_production_gate,
    evaluate_production_performance,
    serialize_production_gate,
)


@dataclass(frozen=True)
class ChallengerEvidence:
    model_key: str
    model_version: int
    comparison_count: int
    average_absolute_difference: float | None
    maximum_absolute_difference: float | None
    selected_count: int


def _payload(row) -> dict:
    if isinstance(row, dict):
        value = row.get("payload", {})
        return value if isinstance(value, dict) else {}
    return json.loads(getattr(row, "payload_json", "{}") or "{}")


def collect_canary_evidence(
    audit_rows: Sequence,
    *,
    model_key: str,
    model_version: int,
) -> ChallengerEvidence:
    differences: list[float] = []
    selected_count = 0
    for row in audit_rows:
        action = row.get("action") if isinstance(row, dict) else getattr(row, "action", "")
        if action != "ml.serving_policy_prediction":
            continue
        payload = _payload(row)
        canary = payload.get("canary") or {}
        primary = payload.get("primary") or {}
        if (
            canary.get("model_key") != model_key
            or int(canary.get("model_version", -1)) != model_version
        ):
            continue
        canary_output = canary.get("output")
        primary_output = primary.get("output")
        if isinstance(canary_output, (int, float)) and isinstance(primary_output, (int, float)):
            differences.append(abs(float(canary_output) - float(primary_output)))
        if payload.get("canary_selected") is True:
            selected_count += 1

    return ChallengerEvidence(
        model_key=model_key,
        model_version=model_version,
        comparison_count=len(differences),
        average_absolute_difference=mean(differences) if differences else None,
        maximum_absolute_difference=max(differences) if differences else None,
        selected_count=selected_count,
    )


def serialize_canary_evidence(evidence: ChallengerEvidence) -> dict:
    return {
        "model_key": evidence.model_key,
        "model_version": evidence.model_version,
        "comparison_count": evidence.comparison_count,
        "average_absolute_difference": evidence.average_absolute_difference,
        "maximum_absolute_difference": evidence.maximum_absolute_difference,
        "selected_count": evidence.selected_count,
    }


async def lifecycle_snapshot(
    db: AsyncSession,
    *,
    model_key: str,
    minimum_canary_comparisons: int = 10,
    maximum_canary_difference: float = 0.20,
    minimum_feedback: int = 20,
    maximum_production_degradation: float = 0.20,
) -> dict:
    if minimum_canary_comparisons < 0:
        raise ValueError("minimum_canary_comparisons must be non-negative")
    if maximum_canary_difference < 0:
        raise ValueError("maximum_canary_difference must be non-negative")

    rows = await list_models(db, model_key)
    if not rows:
        raise LookupError("model key not found")
    audits = await list_audit_events(db, limit=10000)

    champion_row = next((row for row in rows if row.status == "active"), None)
    challengers = []
    rollback_candidates = []

    for row in rows:
        model = serialize_model(row)
        metadata = model.get("metadata") or {}
        validation = metadata.get("validation") or {}
        validation_passed = validation.get("passed") is True
        production_gate = evaluate_production_performance(
            row,
            audits,
            minimum_feedback=minimum_feedback,
            maximum_degradation_fraction=maximum_production_degradation,
        )
        canary = collect_canary_evidence(
            audits,
            model_key=model_key,
            model_version=row.version,
        )
        canary_ready = (
            canary.comparison_count >= minimum_canary_comparisons
            and (
                canary.average_absolute_difference is None
                or canary.average_absolute_difference <= maximum_canary_difference
            )
        )
        promotion_ready = (
            row.status != "retired"
            and validation_passed
            and production_gate.passed
            and canary_ready
        )
        item = {
            "model": model,
            "validation_passed": validation_passed,
            "production_gate": serialize_production_gate(production_gate),
            "canary_evidence": serialize_canary_evidence(canary),
            "canary_ready": canary_ready,
            "promotion_ready": promotion_ready,
        }

        if champion_row is not None and row.version < champion_row.version and row.status != "retired":
            rollback_candidates.append({
                **item,
                "rollback_eligible": validation_passed and production_gate.passed,
            })
        elif row.status == "registered":
            challengers.append(item)

    rollback_candidates.sort(key=lambda item: item["model"]["version"], reverse=True)
    challengers.sort(key=lambda item: item["model"]["version"], reverse=True)

    return {
        "model_key": model_key,
        "champion": serialize_model(champion_row) if champion_row else None,
        "challengers": challengers,
        "rollback_candidates": rollback_candidates,
        "policy": {
            "minimum_canary_comparisons": minimum_canary_comparisons,
            "maximum_canary_difference": maximum_canary_difference,
            "minimum_feedback": minimum_feedback,
            "maximum_production_degradation": maximum_production_degradation,
        },
    }


async def promote_challenger(
    db: AsyncSession,
    *,
    model_key: str,
    version: int,
    minimum_canary_comparisons: int = 10,
    maximum_canary_difference: float = 0.20,
    minimum_feedback: int = 20,
    maximum_production_degradation: float = 0.20,
):
    snapshot = await lifecycle_snapshot(
        db,
        model_key=model_key,
        minimum_canary_comparisons=minimum_canary_comparisons,
        maximum_canary_difference=maximum_canary_difference,
        minimum_feedback=minimum_feedback,
        maximum_production_degradation=maximum_production_degradation,
    )
    challenger = next(
        (item for item in snapshot["challengers"] if item["model"]["version"] == version),
        None,
    )
    if challenger is None:
        row = await get_model(db, model_key, version)
        if row is None:
            raise LookupError("model version not found")
        raise ValueError("model version is not a challenger")
    if not challenger["promotion_ready"]:
        raise ValueError("challenger has not met promotion readiness requirements")

    row, gate = await activate_model_with_production_gate(
        db,
        model_key,
        version,
        minimum_feedback=minimum_feedback,
        maximum_degradation_fraction=maximum_production_degradation,
    )
    return {
        "champion": serialize_model(row),
        "production_gate": serialize_production_gate(gate),
        "canary_evidence": challenger["canary_evidence"],
    }
