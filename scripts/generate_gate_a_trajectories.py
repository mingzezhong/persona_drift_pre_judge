#!/usr/bin/env python3
"""Generate one immutable axis shard of controlled Gate A trajectories."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import torch
import yaml

from persona_drift.conversation import generate_and_capture_conversation
from persona_drift.gate_a import (
    build_turn_messages,
    parse_forced_choice,
    stable_seed,
    trajectory_id,
)
from persona_drift.hardware import validate_cuda_hardware
from persona_drift.modeling import GenerationCapture, load_target
from persona_drift.representation import cosine_layer_scores


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
    if not isinstance(vectors, dict) or not vectors:
        raise ValueError("persona-vector file has no vectors dictionary")
    return {str(axis): tensor.float() for axis, tensor in vectors.items()}


def generation_settings(config: dict[str, Any]) -> dict[str, Any]:
    settings = dict(config["generation"])
    allowed = {
        "max_new_tokens",
        "min_new_tokens",
        "temperature",
        "top_p",
        "do_sample",
    }
    unexpected = set(settings) - allowed
    if unexpected:
        raise ValueError(f"unsupported generation settings: {sorted(unexpected)}")
    return settings


def reduced_capture(
    capture: GenerationCapture,
    vector: torch.Tensor,
    *,
    reference_layer: int,
) -> dict[str, Any]:
    pre_projection = cosine_layer_scores(capture.pre_response, vector)
    response_projection = cosine_layer_scores(capture.response_activations, vector)
    pre_norm = torch.linalg.vector_norm(capture.pre_response.float(), dim=1)
    response_norm = torch.linalg.vector_norm(
        capture.response_activations.float(), dim=1
    )
    return {
        "pre_response_projection": pre_projection.tolist(),
        "response_projection": response_projection.tolist(),
        "pre_response_norm": pre_norm.tolist(),
        "response_norm": response_norm.tolist(),
        "pre_response_projection_layer20": float(pre_projection[reference_layer]),
        "response_projection_layer20": float(response_projection[reference_layer]),
        "pre_response_norm_layer20": float(pre_norm[reference_layer]),
        "response_norm_layer20": float(response_norm[reference_layer]),
        "response_token_count": int(capture.response_token_ids.shape[1]),
        "stop_token_id": capture.stop_token_id,
        "forbidden_token_ids": list(capture.forbidden_token_ids),
    }


def prepare_output(output_dir: Path) -> tuple[Path, Path]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return (
        output_dir / "trajectories.jsonl.partial",
        output_dir / "probes.jsonl.partial",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--axis", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    template_path = Path(config["data"]["template"])
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    configured_axes = list(config["data"]["axes"])
    if args.axis not in configured_axes or args.axis not in template["axes"]:
        raise ValueError(f"axis is not configured: {args.axis}")
    topics_by_id = {topic["id"]: topic for topic in template["topics"]}
    topic_ids = list(config["data"]["topics"])
    missing_topics = sorted(set(topic_ids) - set(topics_by_id))
    if missing_topics:
        raise ValueError(f"unknown Gate A topics: {missing_topics}")
    conditions = list(config["data"]["conditions"])
    seeds = [int(seed) for seed in config["data"]["seeds"]]
    total_turns = int(config["data"]["total_turns"])
    abrupt_onset = int(config["data"]["abrupt_onset_turn"])
    checkpoints = [int(turn) for turn in config["data"]["checkpoint_turns"]]
    if checkpoints[0] != 0 or checkpoints[-1] != total_turns:
        raise ValueError("checkpoint schedule must include baseline 0 and final turn")

    hardware = config["hardware"]
    validate_cuda_hardware(
        expected_gpu_count=int(hardware["gpu_count"]),
        expected_name_substring=hardware.get("expected_name_substring"),
        require_bf16=bool(hardware.get("allow_bf16", False)),
        min_memory_gib=hardware.get("min_memory_gib"),
    )
    vector_path = Path(config["vectors"]["path"])
    vector_hash = sha256(vector_path)
    if vector_hash != config["vectors"]["sha256"]:
        raise RuntimeError("persona-vector SHA256 differs from the frozen config")
    vectors = load_vectors(vector_path)
    vector = vectors[args.axis]
    reference_layer = int(config["vectors"]["reference_layer"])
    if vector.ndim != 2 or not 0 <= reference_layer < vector.shape[0]:
        raise ValueError("invalid vector shape or reference layer")

    model_config = config["model"]
    target = load_target(
        str(model_config["name"]),
        revision=str(model_config["revision"]),
        dtype=str(hardware["dtype"]),
        attention_implementation=str(hardware["attention_implementation"]),
        allow_tf32=bool(hardware["allow_tf32"]),
    )
    if target.resolved_revision != str(model_config["revision"]):
        raise RuntimeError("resolved target-model revision differs from config")
    generation = generation_settings(config)
    axis_template = template["axes"][args.axis]
    system = (
        f"{axis_template['target_system'].rstrip()}\n\n"
        f"{template['shared_system'].strip()}"
    )
    probe = axis_template["probe"]
    trajectories_partial, probes_partial = prepare_output(args.output_dir)
    planned_trajectories = len(conditions) * len(topic_ids) * len(seeds)
    planned_probes = planned_trajectories * len(checkpoints)
    print(
        f"axis={args.axis} planned trajectories={planned_trajectories} "
        f"probes={planned_probes}"
    )

    config_hash = sha256(args.config)
    template_hash = sha256(template_path)
    trajectory_count = 0
    probe_count = 0
    with trajectories_partial.open("x", encoding="utf-8") as trajectories_out, (
        probes_partial.open("x", encoding="utf-8")
    ) as probes_out:
        for topic_id in topic_ids:
            topic = topics_by_id[topic_id]
            for base_seed in seeds:
                for condition in conditions:
                    traj_id = trajectory_id(
                        args.axis, condition, topic_id, base_seed
                    )
                    user_turns = build_turn_messages(
                        template,
                        axis=args.axis,
                        condition=condition,
                        topic=topic,
                        total_turns=total_turns,
                        abrupt_onset_turn=abrupt_onset,
                    )
                    messages: list[dict[str, str]] = [
                        {"role": "system", "content": system}
                    ]
                    turns: list[dict[str, Any]] = []

                    def measure(checkpoint_turn: int) -> None:
                        nonlocal probe_count
                        probe_seed = stable_seed(
                            "gate-a-probe",
                            args.axis,
                            topic_id,
                            base_seed,
                            checkpoint_turn,
                        )
                        probe_messages = messages + [
                            {"role": "user", "content": str(probe["user"])}
                        ]
                        capture = generate_and_capture_conversation(
                            target,
                            messages=probe_messages,
                            seed=probe_seed,
                            generation=generation,
                        )
                        response = capture.response_text.strip()
                        if not response:
                            raise RuntimeError(f"empty probe response for {traj_id}")
                        parsed_choice = parse_forced_choice(response)
                        example_id = f"{traj_id}-checkpoint-{checkpoint_turn:02d}"
                        record = {
                            "example_id": example_id,
                            "prompt_id": f"{probe['id']}-turn-{checkpoint_turn:02d}",
                            "trajectory_id": traj_id,
                            "axis": args.axis,
                            "polarity": "target",
                            "expected_trait": axis_template["target_trait"],
                            "condition": condition,
                            "topic": topic_id,
                            "split": topic["split"],
                            "checkpoint_turn": checkpoint_turn,
                            "system": system,
                            "user": str(probe["user"]),
                            "response": response,
                            "model": str(model_config["name"]),
                            "model_revision": target.resolved_revision,
                            "seed": base_seed,
                            "generation_seed": probe_seed,
                            "generation": generation,
                            "probe_id": probe["id"],
                            "target_choice": probe["target_choice"],
                            "parsed_choice": parsed_choice,
                            "forced_choice_aligned": (
                                None
                                if parsed_choice is None
                                else parsed_choice == probe["target_choice"]
                            ),
                            **reduced_capture(
                                capture, vector, reference_layer=reference_layer
                            ),
                        }
                        probes_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                        probes_out.flush()
                        probe_count += 1

                    measure(0)
                    for turn_number, user_text in enumerate(user_turns, start=1):
                        messages.append({"role": "user", "content": user_text})
                        turn_seed = stable_seed(
                            "gate-a-main",
                            args.axis,
                            topic_id,
                            base_seed,
                            turn_number,
                        )
                        capture = generate_and_capture_conversation(
                            target,
                            messages=messages,
                            seed=turn_seed,
                            generation=generation,
                        )
                        response = capture.response_text.strip()
                        if not response:
                            raise RuntimeError(
                                f"empty main response for {traj_id} turn {turn_number}"
                            )
                        turns.append(
                            {
                                "turn": turn_number,
                                "user": user_text,
                                "response": response,
                                "generation_seed": turn_seed,
                                **reduced_capture(
                                    capture, vector, reference_layer=reference_layer
                                ),
                            }
                        )
                        messages.append({"role": "assistant", "content": response})
                        if turn_number in checkpoints:
                            measure(turn_number)

                    trajectory = {
                        "trajectory_id": traj_id,
                        "axis": args.axis,
                        "target_trait": axis_template["target_trait"],
                        "condition": condition,
                        "topic": topic_id,
                        "split": topic["split"],
                        "seed": base_seed,
                        "system": system,
                        "turns": turns,
                        "checkpoint_turns": checkpoints,
                        "model": str(model_config["name"]),
                        "model_revision": target.resolved_revision,
                        "generation": generation,
                        "vector_path": str(vector_path),
                        "vector_sha256": vector_hash,
                        "reference_layer": reference_layer,
                        "config_sha256": config_hash,
                        "template_sha256": template_hash,
                    }
                    trajectories_out.write(
                        json.dumps(trajectory, ensure_ascii=False) + "\n"
                    )
                    trajectories_out.flush()
                    trajectory_count += 1
                    print(
                        f"[{trajectory_count}/{planned_trajectories}] {traj_id} "
                        f"probes={probe_count}"
                    )

    if trajectory_count != planned_trajectories or probe_count != planned_probes:
        raise RuntimeError("generated Gate A counts differ from the plan")
    trajectories_path = args.output_dir / "trajectories.jsonl"
    probes_path = args.output_dir / "probes.jsonl"
    trajectories_partial.replace(trajectories_path)
    probes_partial.replace(probes_path)
    summary = {
        "axis": args.axis,
        "trajectories": trajectory_count,
        "probes": probe_count,
        "main_turns": trajectory_count * total_turns,
        "model": str(model_config["name"]),
        "model_revision": target.resolved_revision,
        "config": str(args.config),
        "config_sha256": config_hash,
        "template": str(template_path),
        "template_sha256": template_hash,
        "vectors": str(vector_path),
        "vectors_sha256": vector_hash,
        "trajectories_sha256": sha256(trajectories_path),
        "probes_sha256": sha256(probes_path),
    }
    (args.output_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
