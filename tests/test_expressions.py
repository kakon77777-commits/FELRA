import numpy as np
import pytest

from felra.expressions import UnsafeExpressionError, evaluate_expression


def test_vector_expression_and_boolean_composition() -> None:
    x = np.asarray([-2.0, 0.0, 3.0])
    result = evaluate_expression("x ** 2 >= 0 and isfinite(x)", {"x": x})
    assert np.asarray(result).all()


def test_unsafe_attribute_access_is_rejected() -> None:
    with pytest.raises(UnsafeExpressionError):
        evaluate_expression("x.__class__", {"x": 1.0})
