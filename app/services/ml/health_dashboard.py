from __future__ import annotations

import json
from collections import Counter
from statistics import mean
from typing import Sequence

from app.services.ml.model_registry import serialize_model


ML_ACTIONS = {
    "ml.prediction",
    "ml.ensemble_prediction",
    "ml.serving_policy_prediction",
    "ml.drift_check",
}


def _payload(row) -> dict:
    if isinstance(row, dict):
        value = row.get("payload", {})
        return value if isinstance(value, dict) else {}
    return json.loads(getattr(row, "payload_json", "{}") or "{}")


def _action(row) -> str:
    if isinstance(row, dict):
        return str(row.get("action", ""))
    return str(getattr(row, "action", ""))


def _occurred_at(row):
    if isinstance(row, dict):
        return row.get("occurred_at")
    return getattr(row, "occurred_at", None)


def summarize_ml_health(model_rows: Sequence, audit_rows: Sequence) -> dict:
    models = [serialize_model(row) if not isinstance(row, dict) else row for row in model_rows]
    events = [row for row in audit_rows if _action(row) in ML_ACTIONS]

    status_counts = Counter(model.get("status") for model in models)
    algorithm_counts = Counter(model.get("algorithm") for model in models)
    active_models = [model for model in models if model.get("status") == "active"]

    single_predictions = [row for row in events if _action(row) == "ml.prediction"]
    ensemble_predictions = [row for row in events if _action(row) == "ml.ensemble_prediction"]
    serving_predictions = [row for row in events if _action(row) == "ml.serving_policy_prediction"]
    drift_checks = [row for row in events if _action(row) == "ml.drift_check"]

    confidence_scores: list[float] = []
    low_confidence = 0
    for row in single_predictions:
        uncertainty = _payload(row).get("uncertainty", {})
        score = uncertainty.get("confidence_score")
        if isinstance(score, (int, float)):
            confidence_scores.append(float(score))
        if uncertainty.get("low_confidence") is True:
            low_confidence += 1

    route_counts = Counter()
    fallback_count = 0
    canary_count = 0
    shadow_differences: list[float] = []
    for row in serving_predictions:
        payload = _payload(row)
        route_counts[str(payload.get("route", "unknown"))] += 1
        fallback_count += int(payload.get("fallback_used") is True)
        canary_count += int(payload.get("canary_selected") is True)

        primary = payload.get("primary") or {}
        primary_output = primary.get("output")
        if isinstance(primary_output, (int, float)):
            for shadow in payload.get("shadows") or []:
                shadow_output = shadow.get("output")
                if isinstance(shadow_output, (int, float)):
                    shadow_differences.append(abs(float(shadow_output) - float(primary_output)))

    latest_drift: dict[str, dict] = {}
    ordered_drift = sorted(drift_checks, key=lambda row: str(_occurred_at(row) or ""), reverse=True)
    for row in ordered_drift:
        payload = _payload(row)
        key = str(payload.get("model_key", ""))
        if key and key not in latest_drift:
            latest_drift[key] = {
                "model_version": payload.get("model_version"),
                "drift_detected": payload.get("drift_detected"),
                "retraining_recommended": payload.get("retraining_recommended"),
                "data_drift": payload.get("data_drift"),
                "performance_drift": payload.get("performance_drift"),
                "occurred_at": _occurred_at(row),
            }

    active_validation = []
    for model in active_models:
        active_validation.append({
            "model_key": model.get("model_key"),
            "version": model.get("version"),
            "algorithm": model.get("algorithm"),
            "validation_metrics": (model.get("metrics") or {}).get("validation", {}),
            "validation": (model.get("metadata") or {}).get("validation", {}),
        })

    total_single = len(single_predictions)
    total_serving = len(serving_predictions)

    return {
        "models": {
            "total_versions": len(models),
            "active_count": len(active_models),
            "status_counts": dict(status_counts),
            "algorithm_counts": dict(algorithm_counts),
            "active_validation": active_validation,
        },
        "predictions": {
            "single_count": total_single,
            "ensemble_count": len(ensemble_predictions),
            "serving_policy_count": total_serving,
            "average_confidence": mean(confidence_scores) if confidence_scores else None,
            "low_confidence_count": low_confidence,
            "low_confidence_rate": (low_confidence / total_single) if total_single else None,
        },
        "serving": {
            "route_counts": dict(route_counts),
            "fallback_count": fallback_count,
            "fallback_rate": (fallback_count / total_serving) if total_serving else None,
            "canary_selected_count": canary_count,
            "canary_selected_rate": (canary_count / total_serving) if total_serving else None,
            "shadow_comparison_count": len(shadow_differences),
            "average_shadow_absolute_difference": mean(shadow_differences) if shadow_differences else None,
        },
        "drift": {
            "check_count": len(drift_checks),
            "latest_by_model": latest_drift,
            "models_with_detected_drift": sum(
                1 for item in latest_drift.values() if item.get("drift_detected") is True
            ),
        },
        "event_count": len(events),
    }
