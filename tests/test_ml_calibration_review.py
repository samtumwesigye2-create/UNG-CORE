import pytest

from app.services.ml.calibration import apply_platt_calibration, expected_calibration_error, fit_platt_calibration
from app.services.ml.human_review import assess_human_review


def test_platt_calibration_produces_valid_probabilities_and_metrics():
    probabilities = [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9]
    labels = [0, 0, 0, 0, 1, 1, 1, 1]
    result = fit_platt_calibration(probabilities, labels, epochs=500)
    calibrated = [apply_platt_calibration(p, result) for p in probabilities]
    assert all(0 <= p <= 1 for p in calibrated)
    assert result["sample_count"] == 8
    assert result["brier_after"] <= result["brier_before"]


def test_human_review_reasons_are_explicit():
    assessment = assess_human_review(
        selected_low_confidence=True,
        fallback_used=True,
        ensemble_agreement=0.6,
        shadow_difference=0.5,
        canary_difference=0.4,
    )
    assert assessment.required is True
    assert "low_confidence" in assessment.reasons
    assert "fallback_ensemble_used" in assessment.reasons
    assert assessment.severity == "critical"
