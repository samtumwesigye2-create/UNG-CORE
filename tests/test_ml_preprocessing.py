import pytest

from app.services.ml.preprocessing import (
    fit_preprocessor,
    serialize_preprocessor,
    transform_value,
    transform_values,
)


def test_standardize_fit_and_transform():
    pre = fit_preprocessor([1, 2, 3, 4, 5], method="standardize")
    transformed = transform_values([1, 2, 3, 4, 5], pre)
    assert sum(transformed) / len(transformed) == pytest.approx(0.0)
    assert pre.std is not None and pre.std > 0


def test_minmax_fit_and_transform():
    pre = fit_preprocessor([10, 20, 30], method="minmax")
    assert transform_values([10, 20, 30], pre) == pytest.approx([0.0, 0.5, 1.0])


def test_none_is_identity():
    pre = fit_preprocessor([1, 2, 3], method="none")
    assert transform_value(7, pre) == 7.0


def test_serialized_preprocessor_can_be_reused():
    pre = serialize_preprocessor(fit_preprocessor([1, 2, 3], method="standardize"))
    assert transform_value(2, pre) == pytest.approx(0.0)


def test_zero_variance_is_rejected():
    with pytest.raises(ValueError, match="zero-variance"):
        fit_preprocessor([2, 2, 2], method="standardize")
