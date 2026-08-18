from pathlib import Path

import yaml

from persona_drift.gate_a import build_turn_messages


CONFIG = Path("configs/gate_a_smoke_v3.yaml")
TEMPLATE = Path("data/templates/persona_gate_a_v3.yaml")


def load_design():
    return (
        yaml.safe_load(CONFIG.read_text(encoding="utf-8")),
        yaml.safe_load(TEMPLATE.read_text(encoding="utf-8")),
    )


def test_gate_a_v3_is_a_non_gate_eligible_signal_smoke() -> None:
    config, template = load_design()
    topics = {topic["id"]: topic for topic in template["topics"]}
    selected = [topics[topic] for topic in config["data"]["topics"]]
    assert config["version"] == 3
    assert config["mode"] == "engineering_and_signal_smoke"
    assert config["analysis"]["gate_eligible"] is False
    assert sum(topic["split"] == "calibration" for topic in selected) == 2
    assert sum(topic["split"] == "test" for topic in selected) == 1
    assert config["data"]["output_dir"] == "outputs/gate_a/smoke_v3"


def test_gate_a_v3_extends_only_the_late_horizon() -> None:
    config, template = load_design()
    topic = template["topics"][0]
    assert config["data"]["total_turns"] == 15
    assert config["data"]["checkpoint_turns"] == [0, 3, 6, 9, 12, 15]
    for axis in config["data"]["axes"]:
        for condition in config["data"]["conditions"]:
            messages = build_turn_messages(
                template,
                axis=axis,
                condition=condition,
                topic=topic,
                total_turns=15,
                abrupt_onset_turn=7,
            )
            assert len(messages) == 15
            assert all("{" not in message and "}" not in message for message in messages)


def test_gate_a_v3_abrupt_prefix_remains_exactly_neutral() -> None:
    config, template = load_design()
    topic = template["topics"][0]
    for axis in config["data"]["axes"]:
        neutral = build_turn_messages(
            template,
            axis=axis,
            condition="neutral",
            topic=topic,
            total_turns=15,
            abrupt_onset_turn=7,
        )
        abrupt = build_turn_messages(
            template,
            axis=axis,
            condition="abrupt_pressure",
            topic=topic,
            total_turns=15,
            abrupt_onset_turn=7,
        )
        assert abrupt[:6] == neutral[:6]
        assert abrupt[6:] != neutral[6:]


def test_gate_a_v3_probes_do_not_semantically_reset_the_history() -> None:
    _config, template = load_design()
    for axis in template["axes"].values():
        probe = axis["probe"]
        prompt = probe["user"].lower()
        assert probe["id"].endswith("_v2")
        assert probe["target_choice"] == "B"
        assert "separate decision" not in prompt
        assert "obviously correct" not in prompt
        assert "skip safeguards" not in prompt
        assert "choice: a" in prompt
        assert "choice: b" in prompt


def test_gate_a_v3_keeps_v2_candidate_gate_thresholds() -> None:
    v3 = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    v2 = yaml.safe_load(
        Path("configs/gate_a_smoke_v2.yaml").read_text(encoding="utf-8")
    )
    assert v3["analysis"]["candidate_pilot_gate"] == v2["analysis"][
        "candidate_pilot_gate"
    ]
    assert v3["analysis"]["sustain_checkpoints"] == 2

