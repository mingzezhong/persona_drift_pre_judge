#!/usr/bin/env python3
"""Validate the frozen OLMo repetition-control smoke configs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml


EXPECTED_DECISION_HASH = "c999b2eaf1f3afebe6b6c805e9c3dd0b0ddf267248ae7955ccea0149b9a2b9e8"
EXPECTED_TEMPLATE_HASH = "968c92387590a9e9d12d19b772aa2b522aed8eabfd85af41e30a3e0175b40d49"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs=2, type=Path, required=True)
    args = parser.parse_args()
    configs = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in args.configs]
    penalties = []
    for config in configs:
        data = config["data"]
        generation = config["generation"]
        if config["mode"] != "engineering_repetition_control_smoke":
            raise ValueError("unexpected smoke mode")
        if data["axes"] != ["independent_sycophantic", "cautious_risk_seeking"]:
            raise ValueError("unexpected axes")
        if data["conditions"] != [
            "neutral",
            "gradual_pressure",
            "abrupt_pressure",
            "topic_shift",
        ]:
            raise ValueError("unexpected conditions")
        if data["topics"] != ["municipal_water_reuse"] or data["seeds"] != [611]:
            raise ValueError("unexpected topic or engineering seed")
        if (data["expected_trajectories"], data["expected_main_turns"], data["expected_probes"]) != (8, 200, 48):
            raise ValueError("unexpected design counts")
        if generation["max_new_tokens"] != 384 or generation["temperature"] != 0.7:
            raise ValueError("unexpected frozen decoding baseline")
        if generation["generated_only_no_repeat_ngram_size"] != 4:
            raise ValueError("unexpected generated-only n-gram control")
        penalties.append(float(generation["generated_only_repetition_penalty"]))
        if config["analysis"] != {
            "confirmatory": False,
            "outcomes_must_not_be_evaluated": True,
            "formal_replication_authorized": False,
        }:
            raise ValueError("smoke analysis isolation changed")
        if config["provenance"]["diagnostic_decision_sha256"] != EXPECTED_DECISION_HASH:
            raise ValueError("diagnostic decision lineage changed")
        template = Path(data["template"])
        if sha256(template) != EXPECTED_TEMPLATE_HASH:
            raise ValueError("template hash changed")
    if penalties != [1.05, 1.10]:
        raise ValueError(f"unexpected candidate penalties: {penalties}")

    left = json.loads(json.dumps(configs[0]))
    right = json.loads(json.dumps(configs[1]))
    for config in (left, right):
        config["experiment"] = "<candidate>"
        config["data"]["output_dir"] = "<candidate>"
        config["generation"]["generated_only_repetition_penalty"] = "<candidate>"
    if left != right:
        raise ValueError("candidate configs differ outside frozen candidate fields")
    print("OLMo repetition-control smoke configs validated")


if __name__ == "__main__":
    main()
