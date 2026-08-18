from scripts.analyze_repetition_control_smoke import evaluate_checks


def row(
    *, capped: float = 0.0, duplicate: float = 0.0, format_rate: float = 1.0
) -> dict:
    return {
        "capped_rate": capped,
        "duplicate_4gram_ge_0_15_rate": duplicate,
        "format_compliance_rate": format_rate,
        "complete_sentence_ending_rate": 1.0,
        "list_or_heading_rate": 0.0,
    }


def quality() -> dict:
    return {
        "quality": {
            "role_start_rate": 0.0,
            "forbidden_text_marker_counts": {"<tool_call>": 0},
        }
    }


def test_smoke_candidate_passes_at_frozen_boundaries() -> None:
    overall = row(capped=0.10, duplicate=0.05, format_rate=0.50)
    overall["complete_sentence_ending_rate"] = 0.90
    overall["list_or_heading_rate"] = 0.15
    checks = evaluate_checks(
        overall=overall,
        main=row(capped=0.10),
        probe=row(capped=0.10),
        cells={"cell": row(capped=0.20, duplicate=0.10, format_rate=0.25)},
        quality=quality(),
    )
    assert all(checks.values())


def test_repetition_failure_rejects_otherwise_clean_candidate() -> None:
    checks = evaluate_checks(
        overall=row(duplicate=0.051),
        main=row(),
        probe=row(),
        cells={"cell": row()},
        quality=quality(),
    )
    assert checks["overall_repetition_rate_pass"] is False


def test_cell_format_failure_is_not_hidden_by_overall_average() -> None:
    checks = evaluate_checks(
        overall=row(),
        main=row(),
        probe=row(),
        cells={"good": row(), "bad": row(format_rate=0.24)},
        quality=quality(),
    )
    assert checks["each_cell_format_compliance_pass"] is False
