from __future__ import annotations

import json
from dataclasses import dataclass
from math import exp, isfinite, log
from statistics import mean
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ml.model_registry import serialize_model


_EPSILON = 1e-6


@dataclass(frozen=True)
class CalibrationResult:
    model_key: str
    model_version: int
    sample_count: int
    slope: float
    intercept: float
    brier_before: float
    brier_after: float
    ece_before: float
    ece_after: float


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = exp(-value)
        return 1.0 / (1.0 + z)
    z = exp(value)
    return z / (1.0 + z)


def apply_platt_calibration(probability: float, calibration: dict | None) -> float:
    p = float(probability)
    if not 0.0 <= p <= 1.0:
        raise ValueError("probability must be between 0 and 1")
    if not calibration or calibration.get("method") != "platt":
        return p
    slope = float(calibration["slope"])
    intercept = float(calibration["intercept"])
    clipped = min(max(p, _EPSILON), 1.0 - _EPSILON)
    logit = log(clipped / (1.0 - clipped))
    return _sigmoid(slope * logit + intercept)


def expected_calibration_error(probabilities: Sequence[float], labels: Sequence[int], bins: int = 10) -> float:
    if len(probabilities) != len(labels) or not probabilities:
        raise ValueError("probabilities and labels must be non-empty and equally sized")
    if bins < 2:
        raise ValueError("bins must be at least 2")
    total = len(probabilities)
    error = 0.0
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        members = [
            (float(p), int(y))
            for p, y in zip(probabilities, labels)
            if (low <= float(p) < high) or (index == bins - 1 and float(p) == 1.0)
        ]
        if not members:
            continue
        confidence = mean(p for p, _ in members)
        accuracy = mean(y for _, y in members)
        error += (len(members) / total) * abs(accuracy - confidence)
    return error


def fit_platt_calibration(
    probabilities: Sequence[float],
    labels: Sequence[int],
    *,
    learning_rate: float = 0.05,
    epochs: int = 1000,
) -> dict:
    if len(probabilities) != len(labels) or len(probabilities) < 5:
        raise ValueError("at least five probability/label pairs are required")
    probs = [float(value) for value in probabilities]
    ys = [int(value) for value in labels]
    if not all(isfinite(value) and 0.0 <= value <= 1.0 for value in probs):
        raise ValueError("probabilities must be finite and between 0 and 1")
    if any(value not in (0, 1) for value in ys) or len(set(ys)) < 2:
        raise ValueError("calibration labels must contain both classes 0 and 1")
    if not isfinite(learning_rate) or learning_rate <= 0:
        raise ValueError("learning_rate must be positive and finite")
    if epochs < 1 or epochs > 100000:
        raise ValueError("epochs must be between 1 and 100000")

    logits = []
    for probability in probs:
        clipped = min(max(probability, _EPSILON), 1.0 - _EPSILON)
        logits.append(log(clipped / (1.0 - clipped)))

    slope = 1.0
    intercept = 0.0
    n = float(len(logits))
    for _ in range(epochs):
        ds = 0.0
        di = 0.0
        for logit_value, label in zip(logits, ys):
            calibrated = _sigmoid(slope * logit_value + intercept)
            error = calibrated - label
            ds += error * logit_value / n
            di += error / n
        slope -= learning_rate * ds
        intercept -= learning_rate * di
        if not (isfinite(slope) and isfinite(intercept)):
            raise ValueError("calibration training diverged")

    calibrated = [
        apply_platt_calibration(p, {"method": "platt", "slope": slope, "intercept": intercept})
        for p in probs
    ]
    return {
        "method": "platt",
        "slope": slope,
        "intercept": intercept,
        "sample_count": len(probs),
        "brier_before": mean((p - y) ** 2 for p, y in zip(probs, ys)),
        "brier_after": mean((p - y) ** 2 for p, y in zip(calibrated, ys)),
        "ece_before": expected_calibration_error(probs, ys),
        "ece_after": expected_calibration_error(calibrated, ys),
    }


def feedback_pairs(rows: Sequence, *, model_key: str, model_version: int) -> tuple[list[float], list[int]]:
    probabilities: list[float] = []
    labels: list[int] = []
    for row in rows:
        action = row.get("action") if isinstance(row, dict) else getattr(row, "action", "")
        if action != "ml.prediction_feedback":
            continue
        payload = row.get("payload", {}) if isinstance(row, dict) else json.loads(row.payload_json or "{}")
        if str(payload.get("model_key", "")) != model_key or int(payload.get("model_version", -1)) != model_version:
            continue
        if payload.get("algorithm") != "logistic_regression":
            continue
        predicted = (payload.get("predicted") or {}).get("value")
        observed = (payload.get("observed") or {}).get("value")
        if isinstance(predicted, (int, float)) and observed in (0, 1, 0.0, 1.0):
            probabilities.append(float(predicted))
            labels.append(int(observed))
    return probabilities, labels


async def store_calibration(db: AsyncSession, model_row, calibration: dict):
    model = serialize_model(model_row)
    metadata = dict(model.get("metadata") or {})
    metadata["probability_calibration"] = calibration
    model_row.metadata_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    if not hasattr(db, "ml_models"):
        await db.commit()
        await db.refresh(model_row)
    return model_row
