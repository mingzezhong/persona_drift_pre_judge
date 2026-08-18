import pytest

from scripts.build_persona_vectors import select_complete_pairs


def record(prompt: str, axis: str, polarity: str, accepted: bool | None) -> dict:
    return {
        "example_id": f"{prompt}-{axis}-{polarity}",
        "prompt_id": prompt,
        "axis": axis,
        "polarity": polarity,
        "seed": 0,
        "accepted": accepted,
    }


def test_one_sided_acceptance_excludes_the_whole_pair() -> None:
    records = [
        record("p1", "axis", "target", True),
        record("p1", "axis", "contrast", False),
        record("p2", "axis", "target", True),
        record("p2", "axis", "contrast", True),
    ]
    selected, stats = select_complete_pairs(records)
    assert {item["prompt_id"] for item in selected} == {"p2"}
    assert stats["included_pairs"] == 1
    assert stats["excluded_pairs"] == 1


def test_allow_unjudged_keeps_complete_raw_pair() -> None:
    records = [
        record("p1", "axis", "target", None),
        record("p1", "axis", "contrast", None),
    ]
    selected, stats = select_complete_pairs(records, allow_unjudged=True)
    assert len(selected) == 2
    assert stats["eligibility"] == "complete_raw_pairs"


def test_incomplete_or_duplicate_raw_pair_is_rejected() -> None:
    with pytest.raises(ValueError, match="incomplete raw"):
        select_complete_pairs([record("p1", "axis", "target", True)])
    duplicate = [
        record("p1", "axis", "target", True),
        record("p1", "axis", "target", True),
    ]
    with pytest.raises(ValueError, match="duplicate polarity"):
        select_complete_pairs(duplicate)
