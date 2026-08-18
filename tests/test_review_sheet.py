from scripts.create_extraction_review_sheet import build_review_rows


def test_review_rows_hide_system_and_map_expected_trait() -> None:
    records = [
        {
            "example_id": "e1",
            "prompt_id": "p1",
            "axis": "axis",
            "polarity": "contrast",
            "seed": 0,
            "system": "hidden instruction",
            "user": "question",
            "response": "answer",
        }
    ]
    axes = {
        "axis": {
            "target_trait": "independent",
            "contrast_trait": "sycophantic",
        }
    }
    rows = build_review_rows(records, axes, reviewer_id="r1", shuffle_seed=0)
    assert rows[0]["expected_trait"] == "sycophantic"
    assert "system" not in rows[0]
    assert rows[0]["trait_alignment"] == ""


def test_review_order_is_deterministic() -> None:
    records = [
        {
            "example_id": f"e{index}",
            "prompt_id": "p1",
            "axis": "axis",
            "polarity": "target",
            "seed": index,
            "user": "question",
            "response": "answer",
        }
        for index in range(5)
    ]
    axes = {"axis": {"target_trait": "target", "contrast_trait": "contrast"}}
    first = build_review_rows(records, axes, reviewer_id="r1", shuffle_seed=7)
    second = build_review_rows(records, axes, reviewer_id="r1", shuffle_seed=7)
    assert [row["example_id"] for row in first] == [
        row["example_id"] for row in second
    ]
