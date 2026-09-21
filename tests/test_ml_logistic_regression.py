import pytest

from app.services.ml.logistic_regression import predict_logistic, train_logistic_regression


def test_logistic_regression_learns_separable_binary_classes():
    result = train_logistic_regression(
        [1, 2, 3, 4, 5, 6, 7, 8],
        [0, 0, 0, 0, 1, 1, 1, 1],
        learning_rate=0.1,
        epochs=2000,
    )

    assert result.accuracy == 1.0
    assert result.log_loss < 0.2
    assert result.predictions == [0, 0, 0, 0, 1, 1, 1, 1]


def test_logistic_prediction_returns_probabilities_and_classes():
    probabilities, predictions = predict_logistic([0, 2], weight=2.0, bias=-2.0)
    assert probabilities[0] < 0.5
    assert probabilities[1] > 0.5
    assert predictions == [0, 1]


def test_training_rejects_non_binary_labels():
    with pytest.raises(ValueError, match="0 or 1"):
        train_logistic_regression([1, 2, 3], [0, 2, 1])


def test_training_requires_both_classes():
    with pytest.raises(ValueError, match="both classes"):
        train_logistic_regression([1, 2], [1, 1])
