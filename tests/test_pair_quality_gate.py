from scripts.check_pair_quality_gate import summarize_pair_quality


def record(prompt: str, axis: str, polarity: str, accepted: bool) -> dict:
    return {
        "prompt_id": prompt,
        "axis": axis,
        "polarity": polarity,
        "seed": 0,
        "accepted": accepted,
        "judge_score": {"decision_disagreement": False},
    }


def test_pair_gate_counts_only_double_acceptance() -> None:
    records = [
        record("p1", "axis", "target", True),
        record("p1", "axis", "contrast", True),
        record("p2", "axis", "target", True),
        record("p2", "axis", "contrast", False),
    ]
    summary = summarize_pair_quality(
        records, min_pair_rate=0.5, max_disagreement_rate=0.2
    )
    assert summary["axes"]["axis"]["complete_accepted_pairs"] == 1
    assert summary["axes"]["axis"]["complete_pair_rate"] == 0.5
    assert summary["gate_pass"] is True


def test_pair_gate_fails_excess_judge_disagreement() -> None:
    records = [
        record("p1", "axis", "target", True),
        record("p1", "axis", "contrast", True),
    ]
    records[0]["judge_score"]["decision_disagreement"] = True
    summary = summarize_pair_quality(
        records, min_pair_rate=1.0, max_disagreement_rate=0.2
    )
    assert summary["judge_decision_disagreement_rate"] == 0.5
    assert summary["gate_pass"] is False
