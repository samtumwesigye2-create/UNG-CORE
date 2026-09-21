from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import mean
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alerting import AlertPolicy
from app.services.alerting import evaluate_signal, serialize_alert
from app.services.ml.health_dashboard import summarize_ml_health


@dataclass(frozen=True)
class MLAlertThresholds:
    minimum_average_confidence: float = 0.70
    maximum_low_confidence_rate: float = 0.25
    maximum_fallback_rate: float = 0.25
    maximum_shadow_difference: float = 0.20
    maximum_canary_difference: float = 0.20


def _payload(row) -> dict:
    if isinstance(row, dict):
        value = row.get("payload", {})
        return value if isinstance(value, dict) else {}
    return json.loads(getattr(row, "payload_json", "{}") or "{}")


def _action(row) -> str:
    if isinstance(row, dict):
        return str(row.get("action", ""))
    return str(getattr(row, "action", ""))


def _canary_differences(audit_rows: Sequence) -> list[float]:
    differences: list[float] = []
    for row in audit_rows:
        if _action(row) != "ml.serving_policy_prediction":
            continue
        payload = _payload(row)
        primary = payload.get("primary") or {}
        canary = payload.get("canary") or {}
        primary_output = primary.get("output")
        canary_output = canary.get("output")
        if isinstance(primary_output, (int, float)) and isinstance(canary_output, (int, float)):
            differences.append(abs(float(canary_output) - float(primary_output)))
    return differences


def evaluate_ml_health_findings(model_rows: Sequence, audit_rows: Sequence, thresholds: MLAlertThresholds) -> list[dict]:
    dashboard = summarize_ml_health(model_rows, audit_rows)
    findings: list[dict] = []

    average_confidence = dashboard["predictions"]["average_confidence"]
    if average_confidence is not None and average_confidence < thresholds.minimum_average_confidence:
        findings.append({
            "state": "ml_confidence_low",
            "severity": "degraded",
            "details": {
                "average_confidence": average_confidence,
                "threshold": thresholds.minimum_average_confidence,
            },
        })

    low_rate = dashboard["predictions"]["low_confidence_rate"]
    if low_rate is not None and low_rate > thresholds.maximum_low_confidence_rate:
        findings.append({
            "state": "ml_low_confidence_rate_high",
            "severity": "degraded",
            "details": {
                "low_confidence_rate": low_rate,
                "threshold": thresholds.maximum_low_confidence_rate,
            },
        })

    fallback_rate = dashboard["serving"]["fallback_rate"]
    if fallback_rate is not None and fallback_rate > thresholds.maximum_fallback_rate:
        findings.append({
            "state": "ml_fallback_rate_high",
            "severity": "degraded",
            "details": {
                "fallback_rate": fallback_rate,
                "threshold": thresholds.maximum_fallback_rate,
            },
        })

    shadow_difference = dashboard["serving"]["average_shadow_absolute_difference"]
    if shadow_difference is not None and shadow_difference > thresholds.maximum_shadow_difference:
        findings.append({
            "state": "ml_shadow_divergence",
            "severity": "warning",
            "details": {
                "average_shadow_absolute_difference": shadow_difference,
                "threshold": thresholds.maximum_shadow_difference,
            },
        })

    canary_differences = _canary_differences(audit_rows)
    if canary_differences:
        average_canary_difference = mean(canary_differences)
        if average_canary_difference > thresholds.maximum_canary_difference:
            findings.append({
                "state": "ml_canary_divergence",
                "severity": "warning",
                "details": {
                    "average_canary_absolute_difference": average_canary_difference,
                    "comparison_count": len(canary_differences),
                    "threshold": thresholds.maximum_canary_difference,
                },
            })

    if dashboard["drift"]["models_with_detected_drift"] > 0:
        findings.append({
            "state": "ml_drift_detected",
            "severity": "critical",
            "details": {
                "models_with_detected_drift": dashboard["drift"]["models_with_detected_drift"],
                "latest_by_model": dashboard["drift"]["latest_by_model"],
            },
        })

    failed_validation = []
    for item in dashboard["models"]["active_validation"]:
        validation = item.get("validation") or {}
        if validation.get("passed") is False:
            failed_validation.append({
                "model_key": item.get("model_key"),
                "version": item.get("version"),
                "algorithm": item.get("algorithm"),
            })
    if failed_validation:
        findings.append({
            "state": "ml_active_validation_failed",
            "severity": "critical",
            "details": {"models": failed_validation},
        })

    return findings


async def ensure_ml_alert_policy(db: AsyncSession) -> AlertPolicy:
    policy_key = "ml-health"
    row = (
        await db.execute(select(AlertPolicy).where(AlertPolicy.policy_key == policy_key))
    ).scalar_one_or_none()
    if row is not None:
        return row

    row = AlertPolicy(
        policy_key=policy_key,
        service_key="ML",
        minimum_severity="warning",
        trigger_states_json=json.dumps([
            "ml_confidence_low",
            "ml_low_confidence_rate_high",
            "ml_fallback_rate_high",
            "ml_shadow_divergence",
            "ml_canary_divergence",
            "ml_drift_detected",
            "ml_active_validation_failed",
        ]),
        escalation_minutes_json=json.dumps([5, 15, 30]),
        targets_json=json.dumps(["ml-operators"]),
        enabled=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def evaluate_and_raise_ml_alerts(
    db: AsyncSession,
    *,
    model_rows: Sequence,
    audit_rows: Sequence,
    thresholds: MLAlertThresholds,
) -> dict:
    await ensure_ml_alert_policy(db)
    findings = evaluate_ml_health_findings(model_rows, audit_rows, thresholds)
    alerts = []
    for finding in findings:
        changed = await evaluate_signal(
            db,
            "ML",
            finding["state"],
            finding["severity"],
            finding["details"],
        )
        alerts.extend(serialize_alert(row) for row in changed)

    return {
        "finding_count": len(findings),
        "findings": findings,
        "alert_count": len(alerts),
        "alerts": alerts,
    }
