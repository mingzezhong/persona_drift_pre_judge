#!/usr/bin/env python3
"""Validate prompt-salience smoke configs and derived-template lineage."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from scripts.create_prompt_salience_templates import SOURCE_SHA256, SUFFIXES


EXPECTED_TEMPLATES = {
    "minimal": "bfa1391c51d020872852eb824e2a98a557357d60e0d31f8f238fce43334d5415",
    "strict3": "4f610aa2e6d1e5d702da88b30b19a40f4212e43b5743defc9a6cd7e989b764ac",
}
REPETITION_SUMMARY_SHA256 = "25544e3a41f7461b181e70ed3bc2f1435d5e70d1b118f3b834f67b8f6a83891d"


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
    parser.add_argument("--configs", nargs=2, type=Path, required=True)
    args = parser.parse_args()
    configs = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in args.configs]
    variants: list[str] = []
    for config in configs:
        variant = str(config["prompt_salience"]["variant"])
        variants.append(variant)
        if variant not in EXPECTED_TEMPLATES:
            raise ValueError("unexpected prompt-salience variant")
        data = config["data"]
        if config["mode"] != "engineering_prompt_salience_smoke":
            raise ValueError("unexpected smoke mode")
        if data["topics"] != ["coastal_ferry_ticketing"] or data["seeds"] != [621]:
            raise ValueError("unexpected topic or engineering seed")
        if (data["expected_trajectories"], data["expected_main_turns"], data["expected_probes"]) != (8, 200, 48):
            raise ValueError("unexpected smoke counts")
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
        template_path = Path(data["template"])
        expected_hash = EXPECTED_TEMPLATES[variant]
        if sha256(template_path) != expected_hash:
            raise ValueError("derived template hash changed")
        if config["prompt_salience"]["template_sha256"] != expected_hash:
            raise ValueError("config template hash changed")
        template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
        if template["prompt_salience"] != {
            "variant": variant,
            "suffix": SUFFIXES[variant],
            "source_template_sha256": SOURCE_SHA256,
        }:
            raise ValueError("derived template metadata changed")
        if count_suffixed_prompts(template, SUFFIXES[variant]) != 140:
            raise ValueError("not every generated prompt contains the frozen suffix")
        if config["provenance"]["repetition_smoke_summary_sha256"] != REPETITION_SUMMARY_SHA256:
            raise ValueError("repetition-smoke lineage changed")
    if variants != ["minimal", "strict3"]:
        raise ValueError(f"unexpected candidate order: {variants}")

    left = json.loads(json.dumps(configs[0]))
    right = json.loads(json.dumps(configs[1]))
    for config in (left, right):
        config["experiment"] = "<candidate>"
        config["data"]["template"] = "<candidate>"
        config["data"]["output_dir"] = "<candidate>"
        config["prompt_salience"] = "<candidate>"
    if left != right:
        raise ValueError("configs differ outside frozen prompt candidate fields")
    print("OLMo prompt-salience smoke configs validated")


if __name__ == "__main__":
    main()
