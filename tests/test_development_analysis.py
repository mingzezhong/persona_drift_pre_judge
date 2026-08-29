import numpy as np
import pytest

from scripts.analyze_development_run import cosine_distance


def test_cosine_distance_identical_and_orthogonal():
    left = np.asarray([[[1.0, 0.0], [1.0, 1.0]]])
    right = np.asarray([[[1.0, 0.0], [-1.0, 1.0]]])
    observed = cosine_distance(left, right)
    assert observed[0, 0] == pytest.approx(0.0)
    assert observed[0, 1] == pytest.approx(1.0)


def test_cosine_distance_rejects_shape_and_zero_norm():
    with pytest.raises(ValueError, match="same shape"):
        cosine_distance(np.ones((2, 2)), np.ones((3, 2)))
    with pytest.raises(ValueError, match="zero-norm"):
        cosine_distance(np.zeros((1, 2)), np.ones((1, 2)))
