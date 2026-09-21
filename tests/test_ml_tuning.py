import pytest

from app.services.ml.tuning import kfold_indices, tune_hyperparameters


def test_kfold_indices_cover_every_sample_once_as_validation():
    splits = kfold_indices(10, folds=5, seed=7)
    validation = [index for _, fold in splits for index in fold]
    assert sorted(validation) == list(range(10))


def test_linear_tuning_selects_candidate():
    result = tune_hyperparameters(
        algorithm="linear_regression",
        x=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        y=[3, 5, 7, 9, 11, 13, 15, 17, 19, 21],
        learning_rates=[0.01, 0.05],
        epochs_options=[500, 1500],
        preprocessing_options=["standardize", "minmax"],
        folds=5,
    )
    assert result.primary_metric == "rmse"
    assert result.best_params["preprocessing"] in {"standardize", "minmax"}
    assert len(result.trials) == 8


def test_logistic_tuning_searches_thresholds():
    result = tune_hyperparameters(
        algorithm="logistic_regression",
        x=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        y=[0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
        learning_rates=[0.05],
        epochs_options=[1000],
        thresholds=[0.4, 0.5, 0.6],
        preprocessing_options=["standardize"],
        folds=5,
    )
    assert result.primary_metric == "f1"
    assert result.best_params["threshold"] in {0.4, 0.5, 0.6}
    assert len(result.trials) == 3


def test_tuning_rejects_more_folds_than_samples():
    with pytest.raises(ValueError, match="samples"):
        tune_hyperparameters(
            algorithm="linear_regression",
            x=[1, 2, 3],
            y=[1, 2, 3],
            folds=5,
        )
