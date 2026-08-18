from scripts.create_prompt_salience_templates import SUFFIXES, derive_template


def fixture() -> dict:
    return {
        "version": 4,
        "purpose": "base",
        "axes": {
            "axis_a": {"probe": {"user": "Choose A or B."}},
            "axis_b": {"probe": {"user": "Choose A or B."}},
        },
        "turn_sequences": {
            "common": {"neutral": ["First {project} turn."], "topic_shift": ["Shift."]},
            "axes": {
                "axis_a": {"pressure": ["Pressure {proposal}."]},
                "axis_b": {"pressure": ["Other pressure."]},
            },
        },
    }


def test_minimal_variant_appends_suffix_to_every_generated_user_prompt() -> None:
    result, count = derive_template(fixture(), "minimal")
    assert count == 6
    assert result["version"] == 5
    suffix = SUFFIXES["minimal"]
    assert result["axes"]["axis_a"]["probe"]["user"].endswith(suffix)
    assert result["turn_sequences"]["common"]["neutral"][0].endswith(suffix)
    assert "{project}" in result["turn_sequences"]["common"]["neutral"][0]
    assert "{proposal}" in result["turn_sequences"]["axes"]["axis_a"]["pressure"][0]


def test_variants_are_distinct_and_source_is_not_mutated() -> None:
    base = fixture()
    minimal, _ = derive_template(base, "minimal")
    strict, _ = derive_template(base, "strict3")
    assert minimal["prompt_salience"]["suffix"] != strict["prompt_salience"]["suffix"]
    assert base["axes"]["axis_a"]["probe"]["user"] == "Choose A or B."
