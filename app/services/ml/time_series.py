from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal, Sequence

Method = Literal["linear_trend", "simple_exponential_smoothing"]


@dataclass(frozen=True)
class TimeSeriesForecastResult:
    method: Method
    horizon: int
    forecast: list[float]
    fitted: list[float]
    mae: float
    rmse: float
    slope: float | None = None
    intercept: float | None = None
    alpha: float | None = None
    level: float | None = None


def _validate(values: Sequence[float], horizon: int) -> list[float]:
    if len(values) < 3:
        raise ValueError("at least three observations are required")
    data = [float(v) for v in values]
    if not all(isfinite(v) for v in data):
        raise ValueError("values must contain only finite numbers")
    if horizon < 1 or horizon > 10_000:
        raise ValueError("horizon must be between 1 and 10000")
    return data


def _metrics(actual: list[float], fitted: list[float]) -> tuple[float, float]:
    errors = [a - f for a, f in zip(actual, fitted)]
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = (sum(e * e for e in errors) / len(errors)) ** 0.5
    return mae, rmse


def forecast_linear_trend(values: Sequence[float], *, horizon: int = 1) -> TimeSeriesForecastResult:
    data = _validate(values, horizon)
    n = len(data)
    mean_t = (n - 1) / 2.0
    mean_y = sum(data) / n
    denominator = sum((t - mean_t) ** 2 for t in range(n))
    slope = sum((t - mean_t) * (y - mean_y) for t, y in enumerate(data)) / denominator
    intercept = mean_y - slope * mean_t

    fitted = [intercept + slope * t for t in range(n)]
    forecast = [intercept + slope * t for t in range(n, n + horizon)]
    mae, rmse = _metrics(data, fitted)
    return TimeSeriesForecastResult(
        method="linear_trend",
        horizon=horizon,
        forecast=forecast,
        fitted=fitted,
        mae=mae,
        rmse=rmse,
        slope=slope,
        intercept=intercept,
    )


def forecast_exponential_smoothing(
    values: Sequence[float],
    *,
    horizon: int = 1,
    alpha: float = 0.3,
) -> TimeSeriesForecastResult:
    data = _validate(values, horizon)
    alpha = float(alpha)
    if not isfinite(alpha) or not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be greater than 0 and at most 1")

    level = data[0]
    fitted = [level]
    for value in data[1:]:
        fitted.append(level)
        level = alpha * value + (1.0 - alpha) * level

    # SES has a flat multi-step forecast at the final estimated level.
    forecast = [level for _ in range(horizon)]
    mae, rmse = _metrics(data[1:], fitted[1:])
    return TimeSeriesForecastResult(
        method="simple_exponential_smoothing",
        horizon=horizon,
        forecast=forecast,
        fitted=fitted,
        mae=mae,
        rmse=rmse,
        alpha=alpha,
        level=level,
    )


def forecast_time_series(
    values: Sequence[float],
    *,
    method: Method = "linear_trend",
    horizon: int = 1,
    alpha: float = 0.3,
) -> TimeSeriesForecastResult:
    if method == "linear_trend":
        return forecast_linear_trend(values, horizon=horizon)
    if method == "simple_exponential_smoothing":
        return forecast_exponential_smoothing(values, horizon=horizon, alpha=alpha)
    raise ValueError("method must be 'linear_trend' or 'simple_exponential_smoothing'")
