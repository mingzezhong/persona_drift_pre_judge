import numpy as np
import pytest

from persona_drift.gate_c import (
    build_text_prefix,
    future_drift_label,
    projection_features,
    stratified_cluster_bootstrap_indices,
)


def test_future_drift_label_is_strictly_prospective() -> None:
    assert future_drift_label(5, 10, horizon=5, total_turns=25) == (True, True)
    assert future_drift_label(4, 10, horizon=5, total_turns=25) == (True, False)
    assert future_drift_label(9, 10, horizon=5, total_turns=25) == (True, True)
    assert future_drift_label(10, 10, horizon=5, total_turns=25) == (False, False)
    assert future_drift_label(20, None, horizon=5, total_turns=25) == (True, False)
    assert future_drift_label(21, None, horizon=5, total_turns=25) == (False, False)


def test_future_drift_label_rejects_invalid_arguments() -> None:
    with pytest.raises(ValueError):
        future_drift_label(0, None, horizon=5, total_turns=25)
    with pytest.raises(ValueError):
        future_drift_label(1, None, horizon=0, total_turns=25)
    with pytest.raises(ValueError):
        future_drift_label(1, 30, horizon=5, total_turns=25)


def make_turn(turn: int, projection: float, response: str) -> dict:
    projections = [0.0] * 28
    norms = [1.0] * 28
    projections[20] = projection
    norms[20] = 100.0 + turn
    return {
        "turn": turn,
        "user": f"question {turn}",
        "response": response,
        "pre_response_projection": projections,
        "pre_response_projection_layer20": projection,
        "pre_response_norm": norms,
        "pre_response_norm_layer20": 100.0 + turn,
    }


def test_projection_features_use_only_current_and_prior_turns() -> None:
    turns = [
        make_turn(1, 0.1, "answer one"),
        make_turn(2, 0.2, "answer two"),
        make_turn(3, 0.4, "future answer"),
    ]
    features = projection_features(turns, 1, reference_layer=20, slope_window=3)
    assert features == {
        "projection_layer20": 0.2,
        "projection_delta_turn1": 0.1,
        "projection_slope_last3": pytest.approx(0.1),
        "norm_layer20": 102.0,
        "turn": 2.0,
    }
    turns[2]["pre_response_projection_layer20"] = 999.0
    assert projection_features(turns, 1, reference_layer=20) == features


def test_text_prefix_excludes_current_response_and_system() -> None:
    turns = [
        make_turn(1, 0.1, "answer one"),
        make_turn(2, 0.2, "secret current response"),
    ]
    prefix = build_text_prefix(turns, 1)
    assert prefix == "User: question 1\nAssistant: answer one\nUser: question 2"
    assert "secret current response" not in prefix


def test_cluster_bootstrap_keeps_group_rows_together() -> None:
    draws = list(
        stratified_cluster_bootstrap_indices(
            ["a", "a", "b", "b"],
            ["pressure", "pressure", "control", "control"],
            samples=5,
            seed=7,
        )
    )
    assert len(draws) == 5
    for draw in draws:
        assert len(draw) == 4
        assert np.sum(draw == 0) == np.sum(draw == 1)
        assert np.sum(draw == 2) == np.sum(draw == 3)
