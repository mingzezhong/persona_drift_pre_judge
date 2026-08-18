#!/usr/bin/env python3
"""Validate and merge immutable Gate A axis-topic shards."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import yaml


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"non-object JSON at {path}:{line_number}")
            records.append(record)
    if not records:
        raise ValueError(f"empty JSONL file: {path}")
    return records


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"non-object JSON file: {path}")
    return payload


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    partial = path.with_suffix(path.suffix + ".partial")
    if partial.exists():
        raise FileExistsError(f"partial output exists: {partial}")
    with partial.open("x", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    partial.replace(path)


def response_quality(
    responses: list[dict[str, Any]],
    *,
    max_new_tokens: int,
    forbidden_markers: list[str],
) -> dict[str, Any]:
    token_counts = [int(item["response_token_count"]) for item in responses]
    stop_counts = Counter(
        "none" if item.get("stop_token_id") is None else str(item["stop_token_id"])
        for item in responses
    )
    max_length = sum(count >= max_new_tokens for count in token_counts)
    role_start = stop_counts.get("151644", 0)
    marker_counts = {
        marker: sum(marker in str(item["response"]) for item in responses)
        for marker in forbidden_markers
    }
    ordered = sorted(token_counts)
    return {
        "responses": len(responses),
        "token_count_min": ordered[0],
        "token_count_median": ordered[len(ordered) // 2],
        "token_count_max": ordered[-1],
        "stop_token_counts": dict(sorted(stop_counts.items())),
        "role_start_examples": role_start,
        "role_start_rate": role_start / len(responses),
        "max_length_examples": max_length,
        "max_length_rate": max_length / len(responses),
        "forbidden_text_marker_counts": marker_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data = config["data"]
    output_dir = Path(data["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    axes = list(data["axes"])
    topics = list(data["topics"])
    expected_per_partition = len(data["conditions"]) * len(data["seeds"])
    checkpoints = [int(turn) for turn in data["checkpoint_turns"]]
    total_turns = int(data["total_turns"])
    all_trajectories: list[dict[str, Any]] = []
    all_probes: list[dict[str, Any]] = []
    shard_hashes: dict[str, Any] = {}

    config_hash = sha256(args.config)
    for axis in axes:
        shard_hashes[axis] = {}
        for topic_id in topics:
            shard_dir = output_dir / "shards_v2" / axis / topic_id
            trajectories_path = shard_dir / "trajectories.jsonl"
            probes_path = shard_dir / "probes.jsonl"
            summary_path = shard_dir / "run_summary.json"
            trajectories = load_jsonl(trajectories_path)
            probes = load_jsonl(probes_path)
            summary = load_json(summary_path)
            label = f"{axis}/{topic_id}"
            if len(trajectories) != expected_per_partition:
                raise ValueError(
                    f"{label} has {len(trajectories)} trajectories, "
                    f"expected {expected_per_partition}"
                )
            if len(probes) != expected_per_partition * len(checkpoints):
                raise ValueError(f"{label} has an unexpected number of probes")
            if any(record["axis"] != axis for record in trajectories + probes):
                raise ValueError(f"axis mismatch in shard {label}")
            if any(record["topic"] != topic_id for record in trajectories + probes):
                raise ValueError(f"topic mismatch in shard {label}")
            if any(len(record["turns"]) != total_turns for record in trajectories):
                raise ValueError(f"trajectory length mismatch in shard {label}")
            if any(record.get("config_sha256") != config_hash for record in trajectories):
                raise ValueError(f"config hash mismatch in shard {label}")
            if summary.get("axis") != axis or summary.get("topics") != [topic_id]:
                raise ValueError(f"run summary identity mismatch in shard {label}")
            if summary.get("config_sha256") != config_hash:
                raise ValueError(f"run summary config hash mismatch in shard {label}")
            if summary.get("trajectories") != expected_per_partition:
                raise ValueError(f"run summary trajectory count mismatch in {label}")
            if summary.get("probes") != expected_per_partition * len(checkpoints):
                raise ValueError(f"run summary probe count mismatch in {label}")
            if summary.get("trajectories_sha256") != sha256(trajectories_path):
                raise ValueError(f"run summary trajectory hash mismatch in {label}")
            if summary.get("probes_sha256") != sha256(probes_path):
                raise ValueError(f"run summary probe hash mismatch in {label}")
            shard_hashes[axis][topic_id] = {
                "trajectories_sha256": sha256(trajectories_path),
                "probes_sha256": sha256(probes_path),
                "run_summary_sha256": sha256(summary_path),
            }
            all_trajectories.extend(trajectories)
            all_probes.extend(probes)

    trajectory_ids = [record["trajectory_id"] for record in all_trajectories]
    probe_ids = [record["example_id"] for record in all_probes]
    if len(trajectory_ids) != len(set(trajectory_ids)):
        raise ValueError("duplicate merged trajectory ID")
    if len(probe_ids) != len(set(probe_ids)):
        raise ValueError("duplicate merged probe ID")
    probes_by_trajectory = Counter(record["trajectory_id"] for record in all_probes)
    if set(probes_by_trajectory) != set(trajectory_ids) or any(
        count != len(checkpoints) for count in probes_by_trajectory.values()
    ):
        raise ValueError("merged probe coverage does not match trajectories")

    trajectories_path = output_dir / "trajectories.jsonl"
    probes_path = output_dir / "probes.jsonl"
    write_jsonl(trajectories_path, all_trajectories)
    write_jsonl(probes_path, all_probes)

    main_responses = [
        turn
        for trajectory in all_trajectories
        for turn in trajectory["turns"]
    ]
    probe_responses = [
        {
            "response": probe["response"],
            "response_token_count": probe["response_token_count"],
            "stop_token_id": probe.get("stop_token_id"),
        }
        for probe in all_probes
    ]
    quality_config = config["generation_quality"]
    forbidden_markers = list(quality_config["forbidden_text_markers"])
    max_new_tokens = int(config["generation"]["max_new_tokens"])
    combined_quality = response_quality(
        main_responses + probe_responses,
        max_new_tokens=max_new_tokens,
        forbidden_markers=forbidden_markers,
    )
    role_pass = (
        combined_quality["role_start_rate"]
        <= float(quality_config["max_role_start_rate"])
    )
    length_pass = (
        combined_quality["max_length_rate"]
        <= float(quality_config["max_length_rate"])
    )
    marker_pass = not any(
        combined_quality["forbidden_text_marker_counts"].values()
    )
    quality = {
        "quality": combined_quality,
        "thresholds": quality_config,
        "checks": {
            "role_start_rate_pass": role_pass,
            "max_length_rate_pass": length_pass,
            "forbidden_text_markers_pass": marker_pass,
        },
        "gate_pass": role_pass and length_pass and marker_pass,
    }
    quality_path = output_dir / "generation_quality.json"
    quality_path.write_text(
        json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {
        "mode": config["mode"],
        "axes": axes,
        "conditions": list(data["conditions"]),
        "topics": topics,
        "seeds": list(data["seeds"]),
        "trajectories": len(all_trajectories),
        "main_turns": len(main_responses),
        "probes": len(all_probes),
        "checkpoint_turns": checkpoints,
        "shard_hashes": shard_hashes,
        "trajectories_sha256": sha256(trajectories_path),
        "probes_sha256": sha256(probes_path),
        "generation_quality_sha256": sha256(quality_path),
        "generation_gate_pass": quality["gate_pass"],
        "config": str(args.config),
        "config_sha256": config_hash,
        "execution_partition": "axis_topic",
    }
    summary_path = output_dir / "merge_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(quality, indent=2, sort_keys=True))
    if not quality["gate_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
