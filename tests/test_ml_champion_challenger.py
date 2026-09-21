import pytest

from app.models.ml_model_registry import MLModelVersion
from app.services.ml.champion_challenger import collect_canary_evidence


def test_canary_evidence_counts_comparisons_and_selections():
    events = [
        {
            "action": "ml.serving_policy_prediction",
            "payload": {
                "primary": {"output": 1.0},
                "canary": {"model_key": "demo", "model_version": 2, "output": 1.1},
                "canary_selected": True,
            },
        },
        {
            "action": "ml.serving_policy_prediction",
            "payload": {
                "primary": {"output": 2.0},
                "canary": {"model_key": "demo", "model_version": 2, "output": 2.2},
                "canary_selected": False,
            },
        },
    ]
    result = collect_canary_evidence(events, model_key="demo", model_version=2)
    assert result.comparison_count == 2
    assert result.selected_count == 1
    assert result.average_absolute_difference == pytest.approx(0.15)
