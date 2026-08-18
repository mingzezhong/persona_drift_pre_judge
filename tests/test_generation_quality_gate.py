from scripts.check_generation_quality_gate import evaluate_generation_gate


def test_generation_gate_uses_inclusive_thresholds() -> None:
    summary = evaluate_generation_gate(
        {
            "available": True,
            "role_start_rate": 0.02,
            "max_length_rate": 0.10,
        },
        {"max_role_start_rate": 0.02, "max_length_rate": 0.10},
    )
    assert summary["gate_pass"] is True


def test_generation_gate_fails_either_violation() -> None:
    summary = evaluate_generation_gate(
        {
            "available": True,
            "role_start_rate": 0.021,
            "max_length_rate": 0.0,
        },
        {"max_role_start_rate": 0.02, "max_length_rate": 0.10},
    )
    assert summary["gate_pass"] is False
