import pytest

from app.services.ml.time_series import (
    forecast_exponential_smoothing,
    forecast_linear_trend,
    forecast_time_series,
)


def test_linear_trend_forecasts_exact_sequence():
    result = forecast_linear_trend([2, 4, 6, 8, 10], horizon=3)
    assert result.forecast == pytest.approx([12, 14, 16])
    assert result.slope == pytest.approx(2.0)
    assert result.rmse == pytest.approx(0.0)


def test_exponential_smoothing_returns_requested_horizon():
    result = forecast_exponential_smoothing([10, 11, 13, 12, 14], horizon=4, alpha=0.5)
    assert len(result.forecast) == 4
    assert len(set(result.forecast)) == 1
    assert result.alpha == 0.5
    assert result.mae >= 0


def test_dispatches_supported_method():
    result = forecast_time_series([1, 2, 3, 4], method="linear_trend", horizon=2)
    assert result.method == "linear_trend"
    assert result.forecast == pytest.approx([5, 6])


def test_rejects_invalid_alpha():
    with pytest.raises(ValueError, match="alpha"):
        forecast_exponential_smoothing([1, 2, 3], alpha=0)


def test_rejects_short_series():
    with pytest.raises(ValueError, match="three observations"):
        forecast_linear_trend([1, 2])
