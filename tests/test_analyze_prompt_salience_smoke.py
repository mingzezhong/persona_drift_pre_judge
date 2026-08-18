from scripts.analyze_prompt_salience_smoke import select_variant


def test_minimal_passing_variant_is_selected_first() -> None:
    candidates = [
        {"prompt_salience_variant": "minimal", "candidate_pass": True},
        {"prompt_salience_variant": "strict3", "candidate_pass": True},
    ]
    assert select_variant(candidates) == "minimal"


def test_strict_variant_is_selected_only_if_minimal_fails() -> None:
    candidates = [
        {"prompt_salience_variant": "minimal", "candidate_pass": False},
        {"prompt_salience_variant": "strict3", "candidate_pass": True},
    ]
    assert select_variant(candidates) == "strict3"


def test_no_candidate_returns_none() -> None:
    candidates = [
        {"prompt_salience_variant": "minimal", "candidate_pass": False},
        {"prompt_salience_variant": "strict3", "candidate_pass": False},
    ]
    assert select_variant(candidates) is None
