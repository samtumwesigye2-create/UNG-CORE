from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Literal, Sequence

Method = Literal["none", "standardize", "minmax"]


@dataclass(frozen=True)
class Preprocessor:
    method: Method
    mean: float | None = None
    std: float | None = None
    minimum: float | None = None
    maximum: float | None = None


def _finite(values: Sequence[float]) -> list[float]:
    if not values:
        raise ValueError("at least one value is required")
    data = [float(v) for v in values]
    if not all(isfinite(v) for v in data):
        raise ValueError("preprocessing values must contain only finite numbers")
    return data


def fit_preprocessor(values: Sequence[float], *, method: Method = "standardize") -> Preprocessor:
    data = _finite(values)
    if method == "none":
        return Preprocessor(method="none")
    if method == "standardize":
        center = sum(data) / len(data)
        variance = sum((value - center) ** 2 for value in data) / len(data)
        std = sqrt(variance)
        if std <= 1e-12:
            raise ValueError("cannot standardize a zero-variance feature")
        return Preprocessor(method="standardize", mean=center, std=std)
    if method == "minmax":
        minimum = min(data)
        maximum = max(data)
        if maximum - minimum <= 1e-12:
            raise ValueError("cannot min-max scale a zero-range feature")
        return Preprocessor(method="minmax", minimum=minimum, maximum=maximum)
    raise ValueError("preprocessing method must be 'none', 'standardize', or 'minmax'")


def transform_value(value: float, preprocessor: Preprocessor | dict | None) -> float:
    x = float(value)
    if not isfinite(x):
        raise ValueError("input value must be finite")
    if preprocessor is None:
        return x
    if isinstance(preprocessor, dict):
        preprocessor = Preprocessor(**preprocessor)

    if preprocessor.method == "none":
        return x
    if preprocessor.method == "standardize":
        if preprocessor.mean is None or preprocessor.std is None or preprocessor.std <= 0:
            raise ValueError("standardize preprocessor requires valid mean and std")
        return (x - preprocessor.mean) / preprocessor.std
    if preprocessor.method == "minmax":
        if preprocessor.minimum is None or preprocessor.maximum is None:
            raise ValueError("minmax preprocessor requires minimum and maximum")
        span = preprocessor.maximum - preprocessor.minimum
        if span <= 0:
            raise ValueError("minmax preprocessor requires maximum greater than minimum")
        return (x - preprocessor.minimum) / span
    raise ValueError("unknown preprocessing method")


def transform_values(values: Sequence[float], preprocessor: Preprocessor | dict | None) -> list[float]:
    return [transform_value(value, preprocessor) for value in values]


def serialize_preprocessor(preprocessor: Preprocessor) -> dict:
    return {
        "method": preprocessor.method,
        "mean": preprocessor.mean,
        "std": preprocessor.std,
        "minimum": preprocessor.minimum,
        "maximum": preprocessor.maximum,
    }
