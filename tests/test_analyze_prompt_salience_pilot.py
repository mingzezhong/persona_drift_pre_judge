from scripts.analyze_prompt_salience_pilot import evaluate_checks, grouped_aggregates


def aggregate_row(**overrides):
    row = {
        "capped_rate": 0.0,
        "duplicate_4gram_ge_0_15_rate": 0.0,
        "format_compliance_rate": 1.0,
        "complete_sentence_ending_rate": 1.0,
        "list_or_heading_rate": 0.0,
    }
    row.update(overrides)
    return row


def quality_row():
    return {
        "quality": {
            "role_start_rate": 0.0,
            "forbidden_text_marker_counts": {
                "<|im_start|>": 0,
                "<tool_call>": 0,
                "</tool_call>": 0,
            },
        }
    }


def test_all_frozen_pilot_checks_pass_for_clean_metrics():
    clean = aggregate_row()
    checks = evaluate_checks(
        overall=clean,
        main=clean,
        probe=clean,
        topic_cells={"probe/axis/condition/topic": clean},
        topics={"topic": clean},
        quality=quality_row(),
    )
    assert checks
    assert all(checks.values())


def test_topic_cell_format_failure_blocks_pilot():
    clean = aggregate_row()
    checks = evaluate_checks(
        overall=clean,
        main=clean,
        probe=clean,
        topic_cells={
            "main/axis/condition/topic": aggregate_row(
                format_compliance_rate=0.74
            )
        },
        topics={"topic": clean},
        quality=quality_row(),
    )
    assert checks["each_topic_cell_format_compliance_pass"] is False


def test_grouping_keeps_topic_as_a_frozen_stratum(monkeypatch):
    rows = [
        {
            "response_type": "main",
            "axis": "axis",
            "condition": "neutral",
            "topic": topic,
        }
        for topic in ("one", "two")
    ]
    monkeypatch.setattr(
        "scripts.analyze_prompt_salience_pilot.aggregate",
        lambda group: {"responses": len(group)},
    )
    result = grouped_aggregates(
        rows, ("response_type", "axis", "condition", "topic")
    )
    assert result == {
        "main/axis/neutral/one": {"responses": 1},
        "main/axis/neutral/two": {"responses": 1},
    }
