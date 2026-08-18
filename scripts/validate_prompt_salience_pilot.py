#!/usr/bin/env python3
"""Validate the frozen full OLMo prompt-salience pilot configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from scripts.analyze_prompt_salience_pilot import THRESHOLDS
from scripts.create_prompt_salience_templates import SOURCE_SHA256, SUFFIXES


TEMPLATE_SHA256 = "bfa1391c51d020872852eb824e2a98a557357d60e0d31f8f238fce43334d5415"
SMOKE_SUMMARY_SHA256 = "fc5186acd277a8d4d30a78da0c86a0fea98988e9a7acd452fff4adb902c6ee8d"
FORMAL_SEEDS = list(range(701, 711))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_suffixed_prompts(template: dict, suffix: str) -> int:
    values = [axis["probe"]["user"] for axis in template["axes"].values()]
    for turns in template["turn_sequences"]["common"].values():
        values.extend(turns)
    for axis_sequences in template["turn_sequences"]["axes"].values():
        for turns in axis_sequences.values():
            values.extend(turns)
    return sum(str(value).endswith(suffix) for value in values)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data = config["data"]
    if config["experiment"] != "olmo_prompt_salience_pilot_v1":
        raise ValueError("unexpected experiment")
    if config["mode"] != "engineering_prompt_salience_full_pilot":
        raise ValueError("unexpected pilot mode")
    if data != {
        "template": "data/templates/persona_cross_model_olmo_prompt_minimal_v1.yaml",
        "output_dir": "outputs/cross_model_replication/olmo_prompt_salience_pilot_v1",
        "axes": ["independent_sycophantic", "cautious_risk_seeking"],
        "conditions": ["neutral", "gradual_pressure", "abrupt_pressure", "topic_shift"],
        "topics": ["municipal_water_reuse", "coastal_ferry_ticketing", "regional_food_cold_chain"],
        "seeds": [631, 632],
        "total_turns": 25,
        "abrupt_onset_turn": 7,
        "checkpoint_turns": [0, 5, 10, 15, 20, 25],
        "expected_trajectories": 48,
        "expected_main_turns": 1200,
        "expected_probes": 288,
    }:
        raise ValueError("pilot data design changed")
    if set(data["seeds"]) & set(FORMAL_SEEDS):
        raise ValueError("pilot seeds overlap reserved formal seeds")
    if config["provenance"]["formal_reserved_seeds"] != FORMAL_SEEDS:
        raise ValueError("reserved formal seeds changed")
    generation = config["generation"]
    if generation != {
        "max_new_tokens": 384,
        "min_new_tokens": 24,
        "temperature": 0.7,
        "top_p": 0.9,
        "do_sample": True,
        "generated_only_repetition_penalty": 1.10,
        "generated_only_no_repeat_ngram_size": 4,
    }:
        raise ValueError("frozen decoding controls changed")
    if config["pilot_quality"] != THRESHOLDS:
        raise ValueError("pilot quality thresholds changed")
    if config["prompt_salience"] != {
        "variant": "minimal",
        "template_sha256": TEMPLATE_SHA256,
    }:
        raise ValueError("selected prompt variant changed")
    template_path = Path(data["template"])
    if sha256(template_path) != TEMPLATE_SHA256:
        raise ValueError("minimal template hash changed")
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    if template["prompt_salience"] != {
        "variant": "minimal",
        "suffix": SUFFIXES["minimal"],
        "source_template_sha256": SOURCE_SHA256,
    }:
        raise ValueError("minimal template metadata changed")
    if count_suffixed_prompts(template, SUFFIXES["minimal"]) != 140:
        raise ValueError("not every generated prompt contains the frozen suffix")
    smoke_path = Path(config["provenance"]["prompt_salience_smoke_summary"])
    if sha256(smoke_path) != SMOKE_SUMMARY_SHA256:
        raise ValueError("prompt-salience smoke summary hash changed")
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    if (
        smoke.get("selected_prompt_salience_variant") != "minimal"
        or smoke.get("full_prompt_salience_pilot_authorized") is not True
        or smoke.get("formal_replication_authorized") is not False
    ):
        raise ValueError("smoke decision does not authorize this pilot")
    if config["provenance"]["source_template_sha256"] != SOURCE_SHA256:
        raise ValueError("source template lineage changed")
    if config["analysis"] != {
        "confirmatory": False,
        "outcomes_must_not_be_evaluated": True,
        "manual_response_text_must_not_be_inspected": True,
        "formal_replication_authorized_before_pilot": False,
    }:
        raise ValueError("analysis guardrails changed")
    output_dir = Path(data["output_dir"])
    forbidden_outputs = [
        output_dir / "trajectories.jsonl",
        output_dir / "probes.jsonl",
        output_dir / "generation_quality.json",
        output_dir / "merge_summary.json",
        output_dir / "summary.json",
        output_dir / "shards_v2",
        output_dir / "judges",
        output_dir / "analysis",
    ]
    if any(path.exists() for path in forbidden_outputs):
        raise ValueError("pilot data or outcome output already exists")
    print("OLMo full prompt-salience pilot config validated")


if __name__ == "__main__":
    main()
