from pathlib import Path

import yaml

from persona_drift.gate_a import build_turn_messages


V3_CONFIG = Path("configs/gate_a_smoke_v3.yaml")
V3_TEMPLATE = Path("data/templates/persona_gate_a_v3.yaml")
V4_CONFIG = Path("configs/gate_a_smoke_v4.yaml")
V4_TEMPLATE = Path("data/templates/persona_gate_a_v4.yaml")


def render(config, template, axis, condition, topic):
    return build_turn_messages(
        template,
        axis=axis,
        condition=condition,
        topic=topic,
        total_turns=config["data"]["total_turns"],
        abrupt_onset_turn=config["data"]["abrupt_onset_turn"],
    )


def test_v4_matches_the_research_specification_horizon() -> None:
    config = yaml.safe_load(V4_CONFIG.read_text(encoding="utf-8"))
    assert config["version"] == 4
    assert config["data"]["total_turns"] == 25
    assert config["data"]["checkpoint_turns"] == [0, 5, 10, 15, 20, 25]
    assert config["data"]["output_dir"] == "outputs/gate_a/smoke_v4"
    assert config["analysis"]["gate_eligible"] is False


def test_v4_preserves_every_v3_turn_through_turn_15() -> None:
    v3_config = yaml.safe_load(V3_CONFIG.read_text(encoding="utf-8"))
    v3_template = yaml.safe_load(V3_TEMPLATE.read_text(encoding="utf-8"))
    v4_config = yaml.safe_load(V4_CONFIG.read_text(encoding="utf-8"))
    v4_template = yaml.safe_load(V4_TEMPLATE.read_text(encoding="utf-8"))
    for topic_index, v4_topic in enumerate(v4_template["topics"]):
        v3_topic = v3_template["topics"][topic_index]
        for axis in v4_config["data"]["axes"]:
            for condition in v4_config["data"]["conditions"]:
                v3_messages = render(
                    v3_config, v3_template, axis, condition, v3_topic
                )
                v4_messages = render(
                    v4_config, v4_template, axis, condition, v4_topic
                )
                assert len(v4_messages) == 25
                assert v4_messages[:15] == v3_messages


def test_v4_abrupt_pressure_still_starts_at_turn_7() -> None:
    config = yaml.safe_load(V4_CONFIG.read_text(encoding="utf-8"))
    template = yaml.safe_load(V4_TEMPLATE.read_text(encoding="utf-8"))
    topic = template["topics"][0]
    assert config["data"]["abrupt_onset_turn"] == 7
    for axis in config["data"]["axes"]:
        neutral = render(config, template, axis, "neutral", topic)
        abrupt = render(config, template, axis, "abrupt_pressure", topic)
        assert abrupt[:6] == neutral[:6]
        assert abrupt[6:] != neutral[6:]


def test_v4_keeps_v3_probe_and_candidate_gate() -> None:
    v3_config = yaml.safe_load(V3_CONFIG.read_text(encoding="utf-8"))
    v3_template = yaml.safe_load(V3_TEMPLATE.read_text(encoding="utf-8"))
    v4_config = yaml.safe_load(V4_CONFIG.read_text(encoding="utf-8"))
    v4_template = yaml.safe_load(V4_TEMPLATE.read_text(encoding="utf-8"))
    assert v4_config["analysis"]["candidate_pilot_gate"] == v3_config[
        "analysis"
    ]["candidate_pilot_gate"]
    for axis in v4_config["data"]["axes"]:
        assert v4_template["axes"][axis]["probe"] == v3_template["axes"][axis][
            "probe"
        ]

