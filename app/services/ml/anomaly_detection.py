from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import median
from typing import Literal, Sequence

Method = Literal["zscore", "mad"]


@dataclass(frozen=True)
class AnomalyBaseline:
    method: Method
    center: float
    scale: float
    threshold: float


@dataclass(frozen=True)
class AnomalyDetectionResult:
    baseline: AnomalyBaseline
    scores: list[float]
    anomalies: list[bool]
    anomaly_indices: list[int]


def _finite_values(values: Sequence[float], *, minimum: int = 1) -> list[float]:
    if len(values) < minimum:
        raise ValueError(f"at least {minimum} values are required")
    converted = [float(v) for v in values]
    if not all(isfinite(v) for v in converted):
        raise ValueError("values must contain only finite numbers")
    return converted


def fit_anomaly_baseline(
    values: Sequence[float],
    *,
    method: Method = "zscore",
    threshold: float | None = None,
) -> AnomalyBaseline:
    data = _finite_values(values, minimum=3)
    if method not in ("zscore", "mad"):
        raise ValueError("method must be 'zscore' or 'mad'")

    if threshold is None:
        threshold = 3.0 if method == "zscore" else 3.5
    threshold = float(threshold)
    if not isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be a finite number greater than zero")

    if method == "zscore":
        center = sum(data) / len(data)
        variance = sum((v - center) ** 2 for v in data) / len(data)
        scale = sqrt(variance)
    else:
        center = median(data)
        scale = median(abs(v - center) for v in data)

    if scale == 0:
        raise ValueError("baseline has zero variation; anomaly scores cannot be calibrated")

    return AnomalyBaseline(method=method, center=center, scale=scale, threshold=threshold)


def score_anomalies(values: Sequence[float], baseline: AnomalyBaseline) -> AnomalyDetectionResult:
    data = _finite_values(values)
    if not (isfinite(baseline.center) and isfinite(baseline.scale) and baseline.scale > 0):
        raise ValueError("baseline center and scale must be finite and scale must be greater than zero")
    if not isfinite(baseline.threshold) or baseline.threshold <= 0:
        raise ValueError("baseline threshold must be a finite number greater than zero")

    if baseline.method == "zscore":
        scores = [abs(v - baseline.center) / baseline.scale for v in data]
    elif baseline.method == "mad":
        # 0.67448975 makes MAD scores comparable to standard z-scores for normal data.
        scores = [0.67448975 * abs(v - baseline.center) / baseline.scale for v in data]
    else:
        raise ValueError("baseline method must be 'zscore' or 'mad'")

    anomalies = [score >= baseline.threshold for score in scores]
    indices = [index for index, flagged in enumerate(anomalies) if flagged]
    return AnomalyDetectionResult(
        baseline=baseline,
        scores=scores,
        anomalies=anomalies,
        anomaly_indices=indices,
    )


def detect_anomalies(
    values: Sequence[float],
    *,
    method: Method = "zscore",
    threshold: float | None = None,
) -> AnomalyDetectionResult:
    baseline = fit_anomaly_baseline(values, method=method, threshold=threshold)
    return score_anomalies(values, baseline)
