import pytest

from app.services.ml.linear_regression import predict_linear, train_linear_regression


def test_linear_regression_learns_simple_line():
    result = train_linear_regression(
        [1, 2, 3, 4, 5, 6, 7, 8],
        [2.9, 3.4, 4.9, 4.7, 6.2, 6.9, 7.3, 8.6],
        learning_rate=0.01,
        epochs=1000,
    )

    assert result.mse < 0.2
    assert result.r2 is not None and result.r2 > 0.95
    assert 0.7 < result.weight < 0.9
    assert 1.5 < result.bias < 2.5


def test_prediction_uses_trained_parameters():
    assert predict_linear([1, 2, 3], weight=2.0, bias=1.0) == [3.0, 5.0, 7.0]


def test_training_rejects_mismatched_data():
    with pytest.raises(ValueError, match="same number"):
        train_linear_regression([1, 2], [1])
