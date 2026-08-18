#!/usr/bin/env python3
"""Validate the frozen QC-remediated OLMo formal replication amendment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


EXPECTED_SEEDS = list(range(701, 711))
EXPECTED_GENERATION = {
    "max_new_tokens": 384,
    "min_new_tokens": 24,
    "temperature": 0.7,
    "top_p": 0.9,
    "do_sample": True,
    "generated_only_repetition_penalty": 1.10,
    "generated_only_no_repeat_ngram_size": 4,
}
EXPECTED_THRESHOLDS = {
    "combined_max_length_rate": 0.10,
    "main_max_length_rate": 0.10,
    "probe_max_length_rate": 0.10,
    "max_topic_cell_max_length_rate": 0.20,
    "overall_duplicate_4gram_ge_0_15_rate": 0.05,
    "max_topic_cell_duplicate_4gram_ge_0_15_rate": 0.10,
    "overall_format_compliance_rate": 0.85,
    "min_topic_cell_format_compliance_rate": 0.75,
    "complete_sentence_ending_rate": 0.95,
    "list_or_heading_rate": 0.05,
    "role_start_rate": 0.02,
}
ROOT = Path("outputs/cross_model_replication/olmo_qc_v1")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"non-object YAML file: {path}")
    return payload


def validate_scientific_invariants(
    config: dict[str, Any], source: dict[str, Any]
) -> None:
    data_keys = (
        "axes",
        "conditions",
        "topics",
        "total_turns",
        "abrupt_onset_turn",
        "checkpoint_turns",
        "expected_trajectories",
        "expected_main_turns",
        "expected_probes",
    )
    for key in data_keys:
        if config["data"][key] != source["data"][key]:
            raise ValueError(f"scientific data field changed: {key}")
    for key in ("hardware", "model", "vectors", "analysis"):
        if config[key] != source[key]:
            raise ValueError(f"frozen scientific section changed: {key}")
    measurement = dict(config["measurement"])
    source_measurement = dict(source["measurement"])
    for key in ("judges_config", "judges_config_sha256"):
        measurement.pop(key)
        source_measurement.pop(key)
    if measurement != source_measurement:
        raise ValueError("frozen measurement protocol changed")


def validate_judges(config: dict[str, Any], source: dict[str, Any]) -> None:
    if config["input"]["rubric"] != source["input"]["rubric"]:
        raise ValueError("judge rubric changed")
    if config["inference"] != source["inference"]:
        raise ValueError("judge inference protocol changed")
    if config["input"]["manifest"] != str(ROOT / "probes.jsonl"):
        raise ValueError("judge manifest is outside the new formal root")
    expected_outputs = {
        "measurement_a": ROOT / "judges/mistral.jsonl",
        "measurement_b": ROOT / "judges/phi4.jsonl",
        "measurement_c": ROOT / "judges/granite.jsonl",
    }
    for judge_id, expected_output in expected_outputs.items():
        judge = dict(config["judges"][judge_id])
        source_judge = dict(source["judges"][judge_id])
        for key in ("review_sheet", "output"):
            judge.pop(key)
            source_judge.pop(key)
        if judge != source_judge:
            raise ValueError(f"judge identity or settings changed: {judge_id}")
        row = config["judges"][judge_id]
        if row["review_sheet"] != str(ROOT / f"review/{judge_id}.csv"):
            raise ValueError(f"judge review path is outside new root: {judge_id}")
        if row["output"] != str(expected_output):
            raise ValueError(f"judge output path is outside new root: {judge_id}")


def validate_amendment(config_path: Path) -> dict[str, Any]:
    config = load_yaml(config_path)
    provenance = config["provenance"]
    if config.get("experiment") != "cross_model_replication_olmo_qc_v1":
        raise ValueError("unexpected formal experiment ID")
    if config.get("mode") != "preregistered_qc_remediated_cross_model_replication":
        raise ValueError("unexpected formal experiment mode")
    if Path(config["data"]["output_dir"]) != ROOT:
        raise ValueError("formal output root differs from the frozen new root")
    if list(config["data"]["seeds"]) != EXPECTED_SEEDS:
        raise ValueError("formal seeds differ from the pilot-reserved seeds")
    if list(provenance["formal_reserved_seeds"]) != EXPECTED_SEEDS:
        raise ValueError("provenance does not reserve the formal seeds")
    if set(config["data"]["seeds"]) & set(provenance["pilot_seeds"]):
        raise ValueError("formal and pilot seeds overlap")
    if set(config["data"]["seeds"]) & set(provenance["prior_failed_formal_seeds"]):
        raise ValueError("formal and prior failed-run seeds overlap")
    if config["generation"] != EXPECTED_GENERATION:
        raise ValueError("generation remediation differs from the passed pilot")
    if config["formal_generation_quality"] != EXPECTED_THRESHOLDS:
        raise ValueError("formal generation-quality thresholds changed")
    if config["prompt_salience"].get("variant") != "minimal":
        raise ValueError("prompt-salience variant is not the selected minimum")

    template = Path(config["data"]["template"])
    if sha256(template) != str(config["prompt_salience"]["template_sha256"]):
        raise ValueError("selected prompt template hash mismatch")
    if sha256(template) != str(provenance["template_sha256"]):
        raise ValueError("provenance template hash mismatch")

    source_path = Path(provenance["source_formal_config"])
    if sha256(source_path) != str(provenance["source_formal_config_sha256"]):
        raise ValueError("source formal config hash mismatch")
    validate_scientific_invariants(config, load_yaml(source_path))

    judges_path = Path(config["measurement"]["judges_config"])
    if sha256(judges_path) != str(config["measurement"]["judges_config_sha256"]):
        raise ValueError("new judges config hash mismatch")
    source_judges_path = Path(provenance["source_judges_config"])
    if sha256(source_judges_path) != str(provenance["source_judges_config_sha256"]):
        raise ValueError("source judges config hash mismatch")
    validate_judges(load_yaml(judges_path), load_yaml(source_judges_path))

    pilot_path = Path(provenance["prompt_salience_pilot_summary"])
    if sha256(pilot_path) != str(provenance["prompt_salience_pilot_summary_sha256"]):
        raise ValueError("prompt-salience pilot summary hash mismatch")
    pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
    if pilot.get("pilot_pass") is not True:
        raise ValueError("prompt-salience pilot did not pass")
    if pilot.get("qc_remediated_formal_replication_authorized") is not True:
        raise ValueError("pilot did not authorize the remediated formal run")
    if pilot.get("prompt_salience_variant") != "minimal":
        raise ValueError("pilot selected a different prompt variant")
    if list(pilot.get("formal_reserved_seeds", [])) != EXPECTED_SEEDS:
        raise ValueError("pilot reserved a different formal seed set")

    forbidden = [
        ROOT / "shards_v2",
        ROOT / "trajectories.jsonl",
        ROOT / "probes.jsonl",
        ROOT / "generation_quality.json",
        ROOT / "formal_generation_qc.json",
        ROOT / "merge_summary.json",
        ROOT / "review",
        ROOT / "judges",
        ROOT / "analysis",
        ROOT / "downstream_job_ids.txt",
    ]
    existing = [str(path) for path in forbidden if path.exists()]
    if existing:
        raise FileExistsError(f"formal outcome path already exists: {existing}")
    return {
        "protocol": "cross_model_replication_olmo_qc_v1_preflight",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "pilot_summary_sha256": sha256(pilot_path),
        "template_sha256": sha256(template),
        "formal_seeds": EXPECTED_SEEDS,
        "scientific_invariants_unchanged": True,
        "judge_identities_unchanged": True,
        "pilot_authorization_verified": True,
        "no_formal_outcome_exists": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate_amendment(args.config), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
