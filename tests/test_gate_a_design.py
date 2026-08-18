from pathlib import Path

import yaml

from persona_drift.gate_a import build_turn_messages


CONFIG = Path("configs/gate_a_smoke_v1.yaml")
TEMPLATE = Path("data/templates/persona_gate_a.yaml")


def test_gate_a_smoke_design_has_disjoint_calibration_and_test_topics() -> None:
    config = yaml.safe_load(CONFIG.read_text())
    template = yaml.safe_load(TEMPLATE.read_text())
    topics = {topic["id"]: topic for topic in template["topics"]}
    selected = [topics[topic] for topic in config["data"]["topics"]]
    assert sum(topic["split"] == "calibration" for topic in selected) == 2
    assert sum(topic["split"] == "test" for topic in selected) == 1
    assert config["analysis"]["gate_eligible"] is False


def test_every_axis_condition_renders_frozen_turn_count() -> None:
    config = yaml.safe_load(CONFIG.read_text())
    template = yaml.safe_load(TEMPLATE.read_text())
    topic = template["topics"][0]
    for axis in config["data"]["axes"]:
        for condition in config["data"]["conditions"]:
            messages = build_turn_messages(
                template,
                axis=axis,
                condition=condition,
                topic=topic,
                total_turns=config["data"]["total_turns"],
                abrupt_onset_turn=config["data"]["abrupt_onset_turn"],
            )
            assert len(messages) == 12
            assert all("{" not in message and "}" not in message for message in messages)


def test_abrupt_pressure_begins_after_six_neutral_turns() -> None:
    config = yaml.safe_load(CONFIG.read_text())
    template = yaml.safe_load(TEMPLATE.read_text())
    topic = template["topics"][0]
    neutral = build_turn_messages(
        template,
        axis="independent_sycophantic",
        condition="neutral",
        topic=topic,
        total_turns=12,
        abrupt_onset_turn=7,
    )
    abrupt = build_turn_messages(
        template,
        axis="independent_sycophantic",
        condition="abrupt_pressure",
        topic=topic,
        total_turns=12,
        abrupt_onset_turn=7,
    )
    assert abrupt[:6] == neutral[:6]
    assert abrupt[6:] != neutral[6:]
