from copy import deepcopy

from scripts.create_olmo_generation_diagnostic import (
    aggregate,
    response_metrics,
    select_blinded_sample,
)


def test_response_metrics_accepts_required_format() -> None:
    text = (
        "The evidence supports a limited and reversible trial before expansion. "
        "It should retain fallback capacity while the team verifies reliability, "
        "access, staffing, and failure response under contrasting conditions before "
        "any broader and potentially irreversible operational commitment."
    )
    metrics = response_metrics(text)
    assert metrics["word_range_30_70"] is True
    assert metrics["sentence_range_2_4"] is True
    assert metrics["format_compliant"] is True
    assert metrics["complete_sentence_ending"] is True
    assert metrics["list_or_heading"] is False


def test_response_metrics_detects_repetition_and_list() -> None:
    text = "- Verify the fallback before expansion. Verify the fallback before expansion."
    metrics = response_metrics(text)
    assert metrics["list_or_heading"] is True
    assert metrics["duplicate_4gram_rate"] > 0
    assert metrics["repeated_sentence_count"] == 1
    assert metrics["format_compliant"] is False


def make_row(item_id: str, status: str, *, axis: str, condition: str) -> dict:
    return {
        "item_id": item_id,
        "response_type": "main",
        "axis": axis,
        "condition": condition,
        "cap_status": status,
    }


def test_blinded_selection_is_deterministic_and_covers_populated_cells() -> None:
    rows = [
        make_row("a1", "capped", axis="a", condition="x"),
        make_row("a2", "capped", axis="a", condition="x"),
        make_row("a3", "stopped", axis="a", condition="x"),
        make_row("b1", "stopped", axis="b", condition="x"),
    ]
    first = select_blinded_sample(rows)
    second = select_blinded_sample(list(reversed(deepcopy(rows))))
    assert [row["item_id"] for row in first] == [row["item_id"] for row in second]
    assert len(first) == 3
    assert {
        (row["axis"], row["condition"], row["cap_status"]) for row in first
    } == {("a", "x", "capped"), ("a", "x", "stopped"), ("b", "x", "stopped")}


def test_aggregate_reports_frozen_format_and_repetition_rates() -> None:
    rows = [
        {
            "response_token_count": 384,
            "cap_status": "capped",
            "stop_token_id": None,
            "metrics": {
                "word_count": 80,
                "word_range_30_70": False,
                "sentence_range_2_4": True,
                "format_compliant": False,
                "complete_sentence_ending": False,
                "list_or_heading": False,
                "duplicate_4gram_rate": 0.2,
                "repeated_sentence_count": 1,
            },
        },
        {
            "response_token_count": 50,
            "cap_status": "stopped",
            "stop_token_id": 100257,
            "metrics": {
                "word_count": 40,
                "word_range_30_70": True,
                "sentence_range_2_4": True,
                "format_compliant": True,
                "complete_sentence_ending": True,
                "list_or_heading": False,
                "duplicate_4gram_rate": 0.0,
                "repeated_sentence_count": 0,
            },
        },
    ]
    result = aggregate(rows)
    assert result["responses"] == 2
    assert result["capped_rate"] == 0.5
    assert result["format_compliance_rate"] == 0.5
    assert result["duplicate_4gram_ge_0_15_rate"] == 0.5
    assert result["stop_token_counts"] == {"100257": 1, "none": 1}
