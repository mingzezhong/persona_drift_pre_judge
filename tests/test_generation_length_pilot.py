import ast
from pathlib import Path

from scripts.analyze_generation_length_pilot import (
    evaluate_checks,
    length_summary,
)


def quality(role_start_rate: float = 0.0, marker_count: int = 0) -> dict:
    return {
        "quality": {
            "role_start_rate": role_start_rate,
            "forbidden_text_marker_counts": {"<tool_call>": marker_count},
        }
    }


def group(rate: float) -> dict:
    return {"max_length_rate": rate}


def test_length_summary_counts_cap_hits() -> None:
    assert length_summary([10, 255, 256, 300], 256) == {
        "responses": 4,
        "max_length_examples": 2,
        "max_length_rate": 0.5,
        "token_count_min": 10,
        "token_count_max": 300,
    }


def test_candidate_passes_at_all_frozen_boundaries() -> None:
    checks = evaluate_checks(
        combined=group(0.10),
        main=group(0.10),
        probe=group(0.10),
        main_groups={"a": group(0.15), "b": group(0.0)},
        probe_groups={"a": group(0.20), "b": group(0.0)},
        quality=quality(role_start_rate=0.02),
    )
    assert all(checks.values())


def test_group_imbalance_fails_even_when_combined_rate_passes() -> None:
    checks = evaluate_checks(
        combined=group(0.05),
        main=group(0.05),
        probe=group(0.05),
        main_groups={"a": group(0.16), "b": group(0.0)},
        probe_groups={"a": group(0.0), "b": group(0.0)},
        quality=quality(),
    )
    assert checks["combined_max_length_rate_pass"] is True
    assert checks["each_axis_condition_main_rate_pass"] is False


def test_marker_leakage_fails_candidate() -> None:
    checks = evaluate_checks(
        combined=group(0.0),
        main=group(0.0),
        probe=group(0.0),
        main_groups={"a": group(0.0)},
        probe_groups={"a": group(0.0)},
        quality=quality(marker_count=1),
    )
    assert checks["forbidden_text_markers_pass"] is False


def test_analysis_never_reads_response_text_field() -> None:
    path = Path("scripts/analyze_generation_length_pilot.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    response_subscripts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and node.slice.value == "response"
    ]
    assert response_subscripts == []
