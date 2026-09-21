from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewAssessment:
    required: bool
    reasons: list[str]
    severity: str


def assess_human_review(
    *,
    selected_low_confidence: bool,
    fallback_used: bool,
    ensemble_agreement: float | None,
    shadow_difference: float | None,
    canary_difference: float | None,
    minimum_ensemble_agreement: float = 0.75,
    maximum_shadow_difference: float = 0.20,
    maximum_canary_difference: float = 0.20,
) -> ReviewAssessment:
    reasons: list[str] = []
    if selected_low_confidence:
        reasons.append("low_confidence")
    if fallback_used:
        reasons.append("fallback_ensemble_used")
    if ensemble_agreement is not None and ensemble_agreement < minimum_ensemble_agreement:
        reasons.append("low_ensemble_agreement")
    if shadow_difference is not None and shadow_difference > maximum_shadow_difference:
        reasons.append("shadow_divergence")
    if canary_difference is not None and canary_difference > maximum_canary_difference:
        reasons.append("canary_divergence")

    severity = "critical" if "low_confidence" in reasons and len(reasons) > 1 else ("warning" if reasons else "none")
    return ReviewAssessment(required=bool(reasons), reasons=reasons, severity=severity)
