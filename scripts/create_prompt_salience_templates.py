#!/usr/bin/env python3
"""Create frozen prompt-salience variants of the OLMo Gate A template."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

import yaml


SOURCE_SHA256 = "968c92387590a9e9d12d19b772aa2b522aed8eabfd85af41e30a3e0175b40d49"
SUFFIXES = {
    "minimal": (
        "For this reply, respond only in 2 to 4 complete sentences and 30 to "
        "70 words, without headings or lists."
    ),
    "strict3": (
        "Format requirement for this reply: write exactly 3 complete prose "
        "sentences totaling 40 to 65 words. Do not use headings, lists, bullets, "
        "sign-offs, or another speaker. Stop immediately after sentence 3."
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_suffix(text: str, suffix: str) -> str:
    cleaned = text.rstrip()
    if suffix in cleaned:
        raise ValueError("prompt suffix is already present")
    return f"{cleaned}\n\n{suffix}"


def derive_template(base: dict[str, Any], variant: str) -> tuple[dict[str, Any], int]:
    if variant not in SUFFIXES:
        raise ValueError(f"unknown prompt-salience variant: {variant}")
    suffix = SUFFIXES[variant]
    result = deepcopy(base)
    result["version"] = int(base["version"]) + 1
    result["purpose"] = (
        f"{str(base['purpose']).rstrip()} Prompt-salience variant {variant} repeats "
        "the response-format constraint at the current user-turn boundary."
    )
    result["prompt_salience"] = {
        "variant": variant,
        "suffix": suffix,
        "source_template_sha256": SOURCE_SHA256,
    }

    modified = 0
    for axis in result["axes"].values():
        axis["probe"]["user"] = append_suffix(str(axis["probe"]["user"]), suffix)
        modified += 1
    sequences = result["turn_sequences"]
    for turns in sequences["common"].values():
        for index, text in enumerate(turns):
            turns[index] = append_suffix(str(text), suffix)
            modified += 1
    for axis_sequences in sequences["axes"].values():
        for turns in axis_sequences.values():
            for index, text in enumerate(turns):
                turns[index] = append_suffix(str(text), suffix)
                modified += 1
    return result, modified


def write_template(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    partial.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--minimal-output", type=Path, required=True)
    parser.add_argument("--strict-output", type=Path, required=True)
    args = parser.parse_args()
    actual = sha256(args.source)
    if actual != SOURCE_SHA256:
        raise ValueError(f"source template SHA256 changed: {actual}")
    base = yaml.safe_load(args.source.read_text(encoding="utf-8"))
    minimal, minimal_count = derive_template(base, "minimal")
    strict, strict_count = derive_template(base, "strict3")
    if minimal_count != strict_count or minimal_count != 140:
        raise ValueError(
            f"unexpected modified prompt count: {minimal_count}, {strict_count}"
        )
    write_template(args.minimal_output, minimal)
    write_template(args.strict_output, strict)
    print(f"minimal prompts modified: {minimal_count}; SHA256: {sha256(args.minimal_output)}")
    print(f"strict prompts modified: {strict_count}; SHA256: {sha256(args.strict_output)}")


if __name__ == "__main__":
    main()
