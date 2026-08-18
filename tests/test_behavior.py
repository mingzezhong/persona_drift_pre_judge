import numpy as np
import pytest

from persona_drift.behavior import (
    average_ranks,
    bootstrap_clustered_correlations,
    pearson_correlation,
    spearman_correlation,
)


def test_average_ranks_handles_ties() -> None:
    assert np.array_equal(average_ranks([3, 1, 1, 2]), [4.0, 1.5, 1.5, 3.0])


def test_correlations_recover_monotonic_relation() -> None:
    assert pearson_correlation([1, 2, 3], [3, 5, 7]) == pytest.approx(1.0)
    assert spearman_correlation([1, 2, 3, 4], [1, 4, 9, 16]) == pytest.approx(1.0)


def test_constant_correlation_input_is_rejected() -> None:
    with pytest.raises(ValueError, match="nonzero variance"):
        spearman_correlation([1, 1, 1], [1, 2, 3])


def test_cluster_bootstrap_is_deterministic() -> None:
    result_a = bootstrap_clustered_correlations(
        [0.8, -0.8, 0.7, -0.7, 0.9, -0.9],
        [1.0, -1.0, 0.75, -0.75, 1.0, -1.0],
        ["a", "a", "b", "b", "c", "c"],
        samples=50,
        seed=7,
    )
    result_b = bootstrap_clustered_correlations(
        [0.8, -0.8, 0.7, -0.7, 0.9, -0.9],
        [1.0, -1.0, 0.75, -0.75, 1.0, -1.0],
        ["a", "a", "b", "b", "c", "c"],
        samples=50,
        seed=7,
    )
    assert result_a == result_b
    assert result_a["spearman_rho_95ci"][0] > 0.9
