from pathlib import Path
import hashlib

import yaml

from scripts.create_measurement_anchors import build_records
from persona_drift.judging import build_judge_messages


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/persona_measurement_development_v1.yaml"
JUDGES_PATH = ROOT / "configs/ai_judges_measurement_development_v1.yaml"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_anchor_design_is_balanced_and_split_by_scenario() -> None:
    config = load(CONFIG_PATH)
    rows = build_records(config)
    assert len(rows) == 60
    assert len({row["example_id"] for row in rows}) == 60
    assert len({row["anchor_scenario"] for row in rows if row["anchor_split"] == "calibration"}) == 4
    assert len({row["anchor_scenario"] for row in rows if row["anchor_split"] == "validation"}) == 2
    for axis in config["design"]["axes"]:
        for split, count in config["design"]["scenarios_per_split"].items():
            for score in range(5):
                assert sum(
                    row["axis"] == axis
                    and row["anchor_split"] == split
                    and row["gold_score"] == score
                    for row in rows
                ) == count


def test_qwen_sources_are_frozen_and_llama_is_untouched() -> None:
    config = load(CONFIG_PATH)
    source = config["source"]
    for path_key, hash_key in [
        ("qwen_probe_manifest", "qwen_probe_manifest_sha256"),
        ("persona_template", "persona_template_sha256"),
        ("original_confirmation_summary", "original_confirmation_summary_sha256"),
    ]:
        assert sha256(ROOT / source[path_key]) == source[hash_key]
    assert config["design"]["qwen_role"] == "development_only"
    assert config["design"]["llama_role"] == "untouched_future_replication"
    assert config["analysis"]["scientific_outcomes_are_not_measurement_selection_criteria"] is True


def test_three_judge_families_and_internal_id_blinding() -> None:
    judges = load(JUDGES_PATH)
    models = [judge["model"] for judge in judges["judges"].values()]
    assert models == [
        "mistralai/Mistral-Small-24B-Instruct-2501",
        "microsoft/phi-4",
        "ibm-granite/granite-3.3-8b-instruct",
    ]
    rubric = load(ROOT / judges["input"]["rubric"])
    row = {
        "example_id": "secret-gradual_pressure-checkpoint-25",
        "expected_trait": "cautious",
        "user": "A decision prompt",
        "response": "A response",
    }
    messages = build_judge_messages(row, rubric)
    assert row["example_id"] not in messages[1]["content"]
    assert "gradual_pressure" not in messages[1]["content"]

