import pytest

from app.services.ml.anomaly_detection import (
    AnomalyBaseline,
    detect_anomalies,
    fit_anomaly_baseline,
    score_anomalies,
)


def test_zscore_flags_large_outlier_against_baseline():
    baseline = fit_anomaly_baseline([9.8, 10.0, 10.1, 10.2, 9.9], method="zscore")
    result = score_anomalies([10.0, 10.2, 25.0], baseline)

    assert result.anomalies == [False, False, True]
    assert result.anomaly_indices == [2]
    assert result.scores[2] > baseline.threshold


def test_mad_is_robust_to_outlier_in_detection_batch():
    result = detect_anomalies([10, 10.1, 9.9, 10.2, 10.0, 50], method="mad")
    assert result.anomalies[-1] is True
    assert result.anomaly_indices == [5]


def test_custom_threshold_is_preserved():
    baseline = fit_anomaly_baseline([1, 2, 3, 4, 5], threshold=2.0)
    assert baseline.threshold == 2.0


def test_zero_variation_baseline_is_rejected():
    with pytest.raises(ValueError, match="zero variation"):
        fit_anomaly_baseline([5, 5, 5])


def test_invalid_baseline_is_rejected():
    with pytest.raises(ValueError, match="scale"):
        score_anomalies([1, 2], AnomalyBaseline("zscore", 0.0, 0.0, 3.0))
