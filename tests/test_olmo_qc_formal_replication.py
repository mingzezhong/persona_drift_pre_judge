from pathlib import Path

import yaml

from scripts.validate_olmo_qc_formal_replication import (
    EXPECTED_GENERATION,
    EXPECTED_SEEDS,
    EXPECTED_THRESHOLDS,
)


def load(path: str):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def test_formal_qc_config_preserves_scientific_sections():
    source = load("configs/cross_model_replication_olmo_v1.yaml")
    formal = load("configs/cross_model_replication_olmo_qc_v1.yaml")
    for section in ("hardware", "model", "vectors", "analysis"):
        assert formal[section] == source[section]
    for field in (
        "axes",
        "conditions",
        "topics",
        "total_turns",
        "abrupt_onset_turn",
        "checkpoint_turns",
        "expected_trajectories",
        "expected_main_turns",
        "expected_probes",
    ):
        assert formal["data"][field] == source["data"][field]


def test_formal_qc_config_uses_frozen_remediation_and_fresh_seeds():
    formal = load("configs/cross_model_replication_olmo_qc_v1.yaml")
    assert formal["data"]["seeds"] == EXPECTED_SEEDS
    assert formal["generation"] == EXPECTED_GENERATION
    assert formal["formal_generation_quality"] == EXPECTED_THRESHOLDS
    assert formal["prompt_salience"]["variant"] == "minimal"
    assert set(formal["data"]["seeds"]).isdisjoint(
        formal["provenance"]["pilot_seeds"]
    )
    assert set(formal["data"]["seeds"]).isdisjoint(
        formal["provenance"]["prior_failed_formal_seeds"]
    )


def test_new_judge_config_only_changes_artifact_paths():
    source = load("configs/ai_judges_cross_model_olmo_v1.yaml")
    formal = load("configs/ai_judges_cross_model_olmo_qc_v1.yaml")
    assert formal["input"]["rubric"] == source["input"]["rubric"]
    assert formal["inference"] == source["inference"]
    for judge_id in source["judges"]:
        source_judge = dict(source["judges"][judge_id])
        formal_judge = dict(formal["judges"][judge_id])
        for field in ("review_sheet", "output"):
            source_judge.pop(field)
            formal_judge.pop(field)
        assert formal_judge == source_judge
        assert "outputs/cross_model_replication/olmo_qc_v1/" in formal["judges"][
            judge_id
        ]["review_sheet"]
        assert "outputs/cross_model_replication/olmo_qc_v1/" in formal["judges"][
            judge_id
        ]["output"]
