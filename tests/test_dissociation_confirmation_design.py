from pathlib import Path
import hashlib

import yaml

from persona_drift.gate_a import build_turn_messages


ROOT = Path(__file__).resolve().parents[1]
GENERATION_CONFIG = ROOT / "configs/dissociation_confirmation_qwen_v1.yaml"
FORECAST_CONFIG = ROOT / "configs/dissociation_forecast_qwen_v1.yaml"
JUDGE_CONFIG = ROOT / "configs/ai_judges_dissociation_confirmation_qwen_v1.yaml"
OLD_CONFIG = ROOT / "configs/gate_a_pilot_v1.yaml"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_confirmation_design_has_exact_new_balanced_cells() -> None:
    config = load(GENERATION_CONFIG)
    old = load(OLD_CONFIG)
    data = config["data"]
    assert set(data["topics"]).isdisjoint(old["data"]["topics"])
    assert len(data["topics"]) == 3
    assert len(data["conditions"]) == 4
    assert len(data["seeds"]) == 10
    assert len(data["axes"]) == 2
    assert data["expected_trajectories"] == 240
    assert data["expected_main_turns"] == 6000
    assert data["expected_probes"] == 1440
    assert set(data["seeds"]).isdisjoint(old["data"]["seeds"])


def test_confirmation_reuses_frozen_generation_and_measurement() -> None:
    config = load(GENERATION_CONFIG)
    old = load(OLD_CONFIG)
    for key in ["model", "vectors", "generation", "generation_quality", "measurement"]:
        assert config[key] == old[key]
    analysis = config["analysis"]
    assert analysis["fixed_threshold"] == 3.5
    source = ROOT / analysis["fixed_threshold_source"]
    assert sha256(source) == analysis["fixed_threshold_source_sha256"]
    assert analysis["confirmation_split"] == "confirmation"


def test_new_template_hash_topics_and_turn_counts_are_frozen() -> None:
    config = load(GENERATION_CONFIG)
    template_path = ROOT / config["data"]["template"]
    template = load(template_path)
    assert sha256(template_path) == config["provenance"]["template_sha256"]
    topics = {topic["id"]: topic for topic in template["topics"]}
    assert set(topics) == set(config["data"]["topics"])
    assert {topic["split"] for topic in topics.values()} == {"confirmation"}
    for axis in config["data"]["axes"]:
        for condition in config["data"]["conditions"]:
            for topic in topics.values():
                turns = build_turn_messages(
                    template,
                    axis=axis,
                    condition=condition,
                    topic=topic,
                    total_turns=25,
                    abrupt_onset_turn=7,
                )
                assert len(turns) == 25


def test_predictor_power_and_forecast_are_immutable() -> None:
    generation = load(GENERATION_CONFIG)
    forecast = load(FORECAST_CONFIG)
    provenance = generation["provenance"]
    for path_key, hash_key in [
        ("power_analysis", "power_analysis_sha256"),
        ("frozen_predictor_summary", "frozen_predictor_summary_sha256"),
        ("frozen_predictor", "frozen_predictor_sha256"),
    ]:
        assert sha256(ROOT / provenance[path_key]) == provenance[hash_key]
    for path_key, hash_key in [
        ("predictor", "predictor_sha256"),
        ("predictor_summary", "predictor_summary_sha256"),
        ("power_analysis", "power_analysis_sha256"),
    ]:
        assert sha256(ROOT / forecast["source"][path_key]) == forecast["source"][hash_key]
    assert forecast["forecast"]["no_refitting_on_confirmation_data"] is True
    assert forecast["forecast"]["horizon"] == 5
    assert forecast["forecast"]["threshold"] == 0.9982034152872861
    assert forecast["confirmation_criteria"]["max_combined_minus_text_auprc_upper_95ci"] == 0.05


def test_judges_remain_blinded_and_outputs_are_isolated() -> None:
    generation = load(GENERATION_CONFIG)
    judges = load(JUDGE_CONFIG)
    root = generation["data"]["output_dir"]
    assert root == "outputs/gate_c/dissociation_confirmation/qwen_v1"
    assert judges["input"]["manifest"].startswith(root + "/")
    assert judges["consensus"]["reviewed_manifest"].startswith(root + "/")
    assert set(judges["judges"]) == {"judge_a", "judge_b"}
    assert "activation predictions are hidden" in judges["purpose"].lower()
