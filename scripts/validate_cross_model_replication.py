#!/usr/bin/env python3
"""Validate frozen cross-model replication design before target generation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import torch
import yaml

from persona_drift.gate_a import build_turn_messages


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_vectors(path: Path) -> dict[str, torch.Tensor]:
    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        if "weights_only" not in str(exc):
            raise
        payload = torch.load(path, map_location="cpu")
    vectors = payload.get("vectors") if isinstance(payload, dict) else None
    if not isinstance(vectors, dict):
        raise ValueError("invalid cross-model vector payload")
    return vectors


def validate_design(config: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    data = config["data"]
    axes = [str(value) for value in data["axes"]]
    conditions = [str(value) for value in data["conditions"]]
    topics = [str(value) for value in data["topics"]]
    seeds = [int(value) for value in data["seeds"]]
    checkpoints = [int(value) for value in data["checkpoint_turns"]]
    if len(set(axes)) != len(axes) or set(axes) != set(template["axes"]):
        raise ValueError("axis design mismatch")
    if conditions != ["neutral", "gradual_pressure", "abrupt_pressure", "topic_shift"]:
        raise ValueError("condition order differs from the frozen design")
    topic_rows = {str(row["id"]): row for row in template["topics"]}
    if set(topics) != set(topic_rows) or any(topic_rows[topic]["split"] != "cross_model_replication" for topic in topics):
        raise ValueError("cross-model topic design mismatch")
    if len(seeds) != 10 or len(set(seeds)) != 10:
        raise ValueError("expected ten unique replication seeds")
    if checkpoints != [0, 5, 10, 15, 20, 25]:
        raise ValueError("checkpoint schedule differs from the frozen design")
    total_turns = int(data["total_turns"])
    for axis in axes:
        for condition in conditions:
            for topic in topics:
                turns = build_turn_messages(
                    template,
                    axis=axis,
                    condition=condition,
                    topic=topic_rows[topic],
                    total_turns=total_turns,
                    abrupt_onset_turn=int(data["abrupt_onset_turn"]),
                )
                if len(turns) != total_turns or any(not value.strip() for value in turns):
                    raise ValueError("invalid rendered turn sequence")
    trajectories = len(axes) * len(conditions) * len(topics) * len(seeds)
    probes = trajectories * len(checkpoints)
    if trajectories != int(data["expected_trajectories"]):
        raise ValueError("expected trajectory count mismatch")
    if trajectories * total_turns != int(data["expected_main_turns"]):
        raise ValueError("expected main-turn count mismatch")
    if probes != int(data["expected_probes"]):
        raise ValueError("expected probe count mismatch")
    return {"axes": axes, "conditions": conditions, "topics": topics, "seeds": seeds, "trajectories": trajectories, "probes": probes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--qwen-config",
        type=Path,
        default=Path("configs/dissociation_confirmation_qwen_v1.yaml"),
    )
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data = config["data"]
    template_path = Path(data["template"])
    if sha256(template_path) != str(config["provenance"]["template_sha256"]):
        raise ValueError("template hash mismatch")
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    design = validate_design(config, template)

    qwen = yaml.safe_load(args.qwen_config.read_text(encoding="utf-8"))
    if set(design["topics"]) & set(qwen["data"]["topics"]):
        raise ValueError("replication topics overlap Qwen confirmation")
    if set(design["seeds"]) & {int(value) for value in qwen["data"]["seeds"]}:
        raise ValueError("replication seeds overlap Qwen confirmation")

    model = config["model"]
    if model != {
        "name": "allenai/OLMo-2-1124-7B-Instruct",
        "revision": "470b1fba1ae01581f270116362ee4aa1b97f4c84",
    }:
        raise ValueError("target model differs from the technical amendment")
    vectors_config = config["vectors"]
    vector_path = Path(vectors_config["path"])
    summary_path = Path(vectors_config["summary"])
    if sha256(vector_path) != str(vectors_config["sha256"]):
        raise ValueError("vector hash mismatch")
    if sha256(summary_path) != str(vectors_config["summary_sha256"]):
        raise ValueError("vector-summary hash mismatch")
    vector_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if vector_summary["target_model"] != model["name"] or vector_summary["target_model_revision"] != model["revision"]:
        raise ValueError("vector target lineage mismatch")
    vectors = load_vectors(vector_path)
    if set(vectors) != set(data["axes"]):
        raise ValueError("vector axes mismatch")
    for axis, vector in vectors.items():
        if list(vector.shape) != [32, 4096] or not bool(torch.isfinite(vector).all()):
            raise ValueError(f"invalid vector tensor: {axis}")
        reference_layer = int(vectors_config["reference_layer"])
        if float(torch.linalg.vector_norm(vector[reference_layer].float())) <= 1e-12:
            raise ValueError(f"zero reference-layer vector: {axis}")

    measurement = config["measurement"]
    for key, hash_key in [
        ("scoring_model", "scoring_model_sha256"),
        ("development_summary", "development_summary_sha256"),
        ("judges_config", "judges_config_sha256"),
    ]:
        path = Path(measurement[key])
        if sha256(path) != str(measurement[hash_key]):
            raise ValueError(f"measurement artifact hash mismatch: {path}")
    development = json.loads(Path(measurement["development_summary"]).read_text(encoding="utf-8"))
    if development.get("measurement_gate_pass") is not True or development.get("future_llama_replication_authorized") is not True:
        raise ValueError("frozen measurement did not authorize replication")
    scoring = json.loads(Path(measurement["scoring_model"]).read_text(encoding="utf-8"))
    judges = yaml.safe_load(Path(measurement["judges_config"]).read_text(encoding="utf-8"))
    if list(judges["judges"]) != ["measurement_a", "measurement_b", "measurement_c"]:
        raise ValueError("judge IDs differ from frozen measurement")
    for judge_id, judge in judges["judges"].items():
        frozen = scoring["judges"][judge_id]
        if judge["model"] != frozen["model"] or judge["revision"] != frozen["revision"]:
            raise ValueError(f"judge lineage mismatch: {judge_id}")
    if int(measurement["stable_min_score"]) != int(scoring["stable_min_score"]):
        raise ValueError("stable score threshold mismatch")
    if float(measurement["stable_probability_threshold"]) != float(scoring["stable_probability_threshold"]):
        raise ValueError("stable probability threshold mismatch")
    if int(measurement["sustain_checkpoints"]) != int(scoring["sustain_checkpoints"]):
        raise ValueError("sustain rule mismatch")

    root = Path(data["output_dir"])
    forbidden = [root / "trajectories.jsonl", root / "probes.jsonl", root / "shards", root / "judges", root / "analysis"]
    if any(path.exists() for path in forbidden):
        raise FileExistsError("cross-model trajectory or outcome output already exists")
    result = {
        "protocol": "cross_model_replication_olmo_v1_preflight",
        "config_sha256": sha256(args.config),
        "template_sha256": sha256(template_path),
        "vector_sha256": sha256(vector_path),
        "scoring_model_sha256": sha256(Path(measurement["scoring_model"])),
        "design": design,
        "target_model": model,
        "measurement_gate_pass": True,
        "no_qwen_topic_or_seed_overlap": True,
        "no_cross_model_outcome_exists": True,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

