import pytest

from app.services.ml.calibration import apply_platt_calibration, fit_platt_calibration
from app.services.ml.human_review import assess_human_review
from app.services.ml.multifeature import predict_multifeature, serialize_multifeature_model, train_multifeature


def test_final_ml_acceptance_path():
    x = [[1,2],[2,1],[3,4],[4,3],[5,6],[6,5],[7,8],[8,7]]
    y = [2*a + 3*b + 1 for a, b in x]
    model, metrics = train_multifeature(
        x,
        y,
        algorithm="multivariate_linear_regression",
        learning_rate=0.05,
        epochs=2500,
    )
    artifact = serialize_multifeature_model(model)
    prediction = predict_multifeature(artifact, [[9,10]])["outputs"][0]
    assert metrics["r2"] > 0.99
    assert prediction == pytest.approx(49, rel=0.05)

    probabilities = [0.1,0.2,0.3,0.4,0.6,0.7,0.8,0.9]
    labels = [0,0,0,0,1,1,1,1]
    calibration = fit_platt_calibration(probabilities, labels, epochs=500)
    calibrated = apply_platt_calibration(0.8, calibration)
    assert 0 <= calibrated <= 1

    review = assess_human_review(
        selected_low_confidence=False,
        fallback_used=False,
        ensemble_agreement=0.95,
        shadow_difference=0.05,
        canary_difference=0.05,
    )
    assert review.required is False
