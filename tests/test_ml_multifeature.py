import pytest

from app.services.ml.multifeature import predict_multifeature, serialize_multifeature_model, train_multifeature


def test_multivariate_linear_regression_learns_two_features():
    x = [[1, 2], [2, 1], [3, 4], [4, 3], [5, 6], [6, 5], [7, 8], [8, 7]]
    y = [2*a + 3*b + 1 for a, b in x]
    model, metrics = train_multifeature(
        x, y,
        algorithm="multivariate_linear_regression",
        learning_rate=0.05,
        epochs=3000,
    )
    pred = predict_multifeature(serialize_multifeature_model(model), [[9, 10]])["outputs"][0]
    assert pred == pytest.approx(49, rel=0.05)
    assert metrics["r2"] > 0.99


def test_multivariate_logistic_regression_returns_probability():
    x = [[0,0],[0,1],[1,0],[1,1],[2,1],[1,2],[2,2],[3,2]]
    y = [0,0,0,0,1,1,1,1]
    model, metrics = train_multifeature(
        x, y,
        algorithm="multivariate_logistic_regression",
        learning_rate=0.1,
        epochs=3000,
    )
    result = predict_multifeature(serialize_multifeature_model(model), [[3,3]])
    assert 0 <= result["outputs"][0] <= 1
    assert result["classifications"][0] == 1
    assert metrics["accuracy"] >= 0.75
