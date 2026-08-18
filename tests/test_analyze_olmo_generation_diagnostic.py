from scripts.analyze_olmo_generation_diagnostic import choose_remediation


def choose(**overrides: float | bool) -> str:
    values: dict[str, float | bool] = {
        "termination_pass": True,
        "capped_duplicate_rate": 0.0,
        "reviewed_capped_repetition_rate": 0.0,
        "format_compliance_rate": 1.0,
        "reviewed_capped_noncompliance_rate": 0.0,
    }
    values.update(overrides)
    selected, _ = choose_remediation(**values)  # type: ignore[arg-type]
    return selected


def test_termination_failure_has_highest_priority() -> None:
    assert choose(termination_pass=False, capped_duplicate_rate=1.0) == "repair_termination"


def test_repetition_threshold_selects_decoding_remediation() -> None:
    assert choose(capped_duplicate_rate=0.25) == "repetition_control_pilot"
    assert choose(reviewed_capped_repetition_rate=0.25) == "repetition_control_pilot"


def test_format_failure_is_checked_after_repetition() -> None:
    assert choose(format_compliance_rate=0.79) == "prompt_salience_pilot"
    assert choose(reviewed_capped_noncompliance_rate=0.25) == "prompt_salience_pilot"


def test_clean_format_failure_diagnostic_selects_larger_cap() -> None:
    assert choose() == "cap_512_768_pilot"
