import math

from scripts.analyze_cross_model_replication import (
    paired_cluster_risk_difference,
    wilson_interval,
)


def outcome(topic: str, seed: int, condition: str, drifted: bool) -> dict:
    return {
        "topic": topic,
        "seed": seed,
        "condition": condition,
        "drifted": drifted,
    }


def test_wilson_interval_for_zero_events_is_not_zero_width() -> None:
    interval = wilson_interval(0, 60)
    assert interval[0] == 0.0
    assert 0.05 < interval[1] < 0.07


def test_paired_cluster_bootstrap_preserves_condition_clusters() -> None:
    rows = []
    for seed, pressure_drift in [(1, True), (2, False)]:
        rows.extend(
            [
                outcome("topic", seed, "gradual_pressure", pressure_drift),
                outcome("topic", seed, "abrupt_pressure", pressure_drift),
                outcome("topic", seed, "neutral", False),
                outcome("topic", seed, "topic_shift", False),
            ]
        )
    result = paired_cluster_risk_difference(
        rows,
        pressure_conditions=["gradual_pressure", "abrupt_pressure"],
        control_conditions=["neutral", "topic_shift"],
        samples=1000,
        seed=7,
    )
    assert result["clusters"] == 2
    assert math.isclose(result["point"], 0.5)
    assert result["95ci"] == [0.0, 1.0]

