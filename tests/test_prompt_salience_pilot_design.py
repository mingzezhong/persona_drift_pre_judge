import hashlib
from pathlib import Path

import yaml

from scripts.analyze_prompt_salience_pilot import THRESHOLDS


def test_full_pilot_design_is_frozen_and_disjoint_from_formal_seeds():
    config = yaml.safe_load(
        Path("configs/olmo_prompt_salience_pilot_v1.yaml").read_text(encoding="utf-8")
    )
    data = config["data"]
    assert data["axes"] == ["independent_sycophantic", "cautious_risk_seeking"]
    assert data["conditions"] == [
        "neutral",
        "gradual_pressure",
        "abrupt_pressure",
        "topic_shift",
    ]
    assert data["topics"] == [
        "municipal_water_reuse",
        "coastal_ferry_ticketing",
        "regional_food_cold_chain",
    ]
    assert data["seeds"] == [631, 632]
    assert (data["expected_trajectories"], data["expected_main_turns"], data["expected_probes"]) == (48, 1200, 288)
    assert not set(data["seeds"]) & set(config["provenance"]["formal_reserved_seeds"])
    assert config["pilot_quality"] == THRESHOLDS


def test_selected_minimal_template_hash_is_frozen():
    config = yaml.safe_load(
        Path("configs/olmo_prompt_salience_pilot_v1.yaml").read_text(encoding="utf-8")
    )
    template_path = Path(config["data"]["template"])
    assert hashlib.sha256(template_path.read_bytes()).hexdigest() == config[
        "prompt_salience"
    ]["template_sha256"]
