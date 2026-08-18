#!/usr/bin/env python3
"""Create a blinded, format-only diagnostic for the failed OLMo length pilot."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from statistics import median
from typing import Any, Iterable

import yaml


WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['\N{RIGHT SINGLE QUOTATION MARK}-][A-Za-z0-9]+)*")
SENTENCE_END_RE = re.compile(r"[.!?](?=(?:[\"')\]]|\s|$))")
COMPLETE_END_RE = re.compile(r"[.!?][\"')\]]*\s*$")
LIST_OR_HEADING_RE = re.compile(r"^\s*(?:[-*\N{BULLET}]\s+|\d+[.)]\s+|#{1,6}\s+)")
ALLOWED_AXES = {"independent_sycophantic", "cautious_risk_seeking"}
ALLOWED_CONDITIONS = {
    "neutral",
    "gradual_pressure",
    "abrupt_pressure",
    "topic_shift",
}
SELECTION_SALT = "olmo-generation-failure-diagnostic-v2-20260818"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    partial.replace(path)


def atomic_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    partial = path.with_suffix(path.suffix + ".partial")
    with partial.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    partial.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"non-object JSON at {path}:{line_number}")
            rows.append(row)
    if not rows:
        raise ValueError(f"empty JSONL file: {path}")
    return rows


def validate_source_manifest(path: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise ValueError(f"malformed manifest line {line_number}: {path}")
        digest, raw_name = parts
        name = raw_name.lstrip("*").strip()
        source = Path(name)
        if source.is_absolute() or ".." in source.parts:
            raise ValueError(f"unsafe manifest path: {name}")
        if not source.is_file():
            raise FileNotFoundError(source)
        actual = sha256(source)
        if actual != digest:
            raise ValueError(f"SHA256 mismatch for {source}: {actual} != {digest}")
        expected[name] = digest
    if not expected:
        raise ValueError("source manifest is empty")
    return expected


def normalized_words(text: str) -> list[str]:
    return [match.group(0).casefold() for match in WORD_RE.finditer(text)]


def duplicate_ngram_rate(words: list[str], n: int = 4) -> float:
    if len(words) < n:
        return 0.0
    grams = [tuple(words[index : index + n]) for index in range(len(words) - n + 1)]
    counts = Counter(grams)
    duplicates = sum(count - 1 for count in counts.values())
    return duplicates / len(grams)


def repeated_sentence_count(text: str) -> int:
    sentences = [
        " ".join(normalized_words(part))
        for part in re.split(r"(?<=[.!?])\s+", text.strip())
    ]
    counts = Counter(sentence for sentence in sentences if len(sentence.split()) >= 4)
    return sum(count - 1 for count in counts.values())


def response_metrics(text: str) -> dict[str, Any]:
    words = normalized_words(text)
    sentence_count = len(SENTENCE_END_RE.findall(text))
    line_count = len(text.splitlines()) or 1
    list_or_heading = any(
        LIST_OR_HEADING_RE.match(line) for line in text.splitlines()
    )
    word_range = 30 <= len(words) <= 70
    sentence_range = 2 <= sentence_count <= 4
    return {
        "character_count": len(text),
        "word_count": len(words),
        "sentence_count": sentence_count,
        "line_count": line_count,
        "word_range_30_70": word_range,
        "sentence_range_2_4": sentence_range,
        "format_compliant": word_range and sentence_range,
        "complete_sentence_ending": bool(COMPLETE_END_RE.search(text)),
        "list_or_heading": list_or_heading,
        "duplicate_4gram_rate": duplicate_ngram_rate(words),
        "repeated_sentence_count": repeated_sentence_count(text),
    }


def flatten_responses(
    trajectories: list[dict[str, Any]], probes: list[dict[str, Any]], cap: int
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trajectory in trajectories:
        axis = str(trajectory["axis"])
        condition = str(trajectory["condition"])
        if axis not in ALLOWED_AXES or condition not in ALLOWED_CONDITIONS:
            raise ValueError("unexpected trajectory axis or condition")
        for turn in trajectory["turns"]:
            item_id = f"{trajectory['trajectory_id']}/turn-{int(turn['turn']):02d}"
            count = int(turn["response_token_count"])
            rows.append(
                {
                    "item_id": item_id,
                    "response_type": "main",
                    "axis": axis,
                    "condition": condition,
                    "topic": trajectory["topic"],
                    "seed": int(trajectory["seed"]),
                    "turn_or_checkpoint": int(turn["turn"]),
                    "response": str(turn["response"]),
                    "response_token_count": count,
                    "stop_token_id": turn.get("stop_token_id"),
                    "cap_status": "capped" if count >= cap else "stopped",
                }
            )
    for probe in probes:
        axis = str(probe["axis"])
        condition = str(probe["condition"])
        if axis not in ALLOWED_AXES or condition not in ALLOWED_CONDITIONS:
            raise ValueError("unexpected probe axis or condition")
        count = int(probe["response_token_count"])
        rows.append(
            {
                "item_id": str(probe["example_id"]),
                "response_type": "probe",
                "axis": axis,
                "condition": condition,
                "topic": probe["topic"],
                "seed": int(probe["seed"]),
                "turn_or_checkpoint": int(probe["checkpoint_turn"]),
                "response": str(probe["response"]),
                "response_token_count": count,
                "stop_token_id": probe.get("stop_token_id"),
                "cap_status": "capped" if count >= cap else "stopped",
            }
        )
    ids = [str(row["item_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate flattened response IDs")
    return rows


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot aggregate an empty group")
    metrics = [row["metrics"] for row in rows]
    token_counts = [int(row["response_token_count"]) for row in rows]
    word_counts = [int(item["word_count"]) for item in metrics]
    duplicate_rates = [float(item["duplicate_4gram_rate"]) for item in metrics]
    stop_counts = Counter(
        "none" if row.get("stop_token_id") is None else str(row["stop_token_id"])
        for row in rows
    )

    def rate(field: str) -> float:
        return sum(bool(item[field]) for item in metrics) / len(metrics)

    return {
        "responses": len(rows),
        "capped_responses": sum(row["cap_status"] == "capped" for row in rows),
        "capped_rate": sum(row["cap_status"] == "capped" for row in rows) / len(rows),
        "token_count_median": median(token_counts),
        "word_count_median": median(word_counts),
        "word_range_30_70_rate": rate("word_range_30_70"),
        "sentence_range_2_4_rate": rate("sentence_range_2_4"),
        "format_compliance_rate": rate("format_compliant"),
        "complete_sentence_ending_rate": rate("complete_sentence_ending"),
        "list_or_heading_rate": rate("list_or_heading"),
        "duplicate_4gram_ge_0_15_rate": sum(value >= 0.15 for value in duplicate_rates)
        / len(rows),
        "repeated_sentence_rate": sum(
            int(item["repeated_sentence_count"]) > 0 for item in metrics
        )
        / len(rows),
        "stop_token_counts": dict(sorted(stop_counts.items())),
    }


def group_aggregates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[f"{row['response_type']}/{row['axis']}/{row['condition']}"] .append(row)
    return {name: aggregate(group) for name, group in sorted(groups.items())}


def selection_rank(item_id: str) -> str:
    return hashlib.sha256(f"{SELECTION_SALT}|{item_id}".encode()).hexdigest()


def select_blinded_sample(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cells: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row["response_type"]),
            str(row["axis"]),
            str(row["condition"]),
            str(row["cap_status"]),
        )
        cells[key].append(row)
    selected = [
        min(cell, key=lambda row: selection_rank(str(row["item_id"])))
        for _, cell in sorted(cells.items())
    ]
    selected.sort(key=lambda row: selection_rank(str(row["item_id"])))
    return selected


def tokenizer_audit(config: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    from transformers import AutoTokenizer

    model = config["model"]
    tokenizer = AutoTokenizer.from_pretrained(
        str(model["name"]),
        revision=str(model["revision"]),
        local_files_only=True,
    )
    raw_eos = tokenizer.eos_token_id
    eos_ids = list(raw_eos) if isinstance(raw_eos, (list, tuple)) else [raw_eos]
    eos_ids = [int(value) for value in eos_ids if value is not None]
    observed = sorted(
        {int(row["stop_token_id"]) for row in rows if row.get("stop_token_id") is not None}
    )
    unexpected = sorted(set(observed) - set(eos_ids))
    chat_template = str(getattr(tokenizer, "chat_template", "") or "")
    return {
        "model": str(model["name"]),
        "revision": str(model["revision"]),
        "eos_token_ids": eos_ids,
        "eos_token": str(tokenizer.eos_token),
        "observed_non_null_stop_token_ids": observed,
        "unexpected_observed_stop_token_ids": unexpected,
        "chat_template_sha256": hashlib.sha256(chat_template.encode()).hexdigest(),
        "pass": bool(eos_ids) and bool(observed) and not unexpected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--pilot-summary", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty {args.output_dir}")
    manifest = validate_source_manifest(args.source_manifest)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    cap = int(config["generation"]["max_new_tokens"])
    if cap != 384:
        raise ValueError(f"the frozen diagnostic requires cap 384, got {cap}")
    pilot = load_json(args.pilot_summary)
    if (
        pilot.get("selected_max_new_tokens") is not None
        or pilot.get("formal_replication_authorized") is not False
        or pilot.get("response_text_inspected") is not False
        or pilot.get("persona_outcomes_evaluated") is not False
    ):
        raise ValueError("pilot summary is not the frozen failed/uninspected state")

    source_dir = Path(config["data"]["output_dir"])
    trajectories_path = source_dir / "trajectories.jsonl"
    probes_path = source_dir / "probes.jsonl"
    trajectories = load_jsonl(trajectories_path)
    probes = load_jsonl(probes_path)
    rows = flatten_responses(trajectories, probes, cap)
    if len(trajectories) != 48 or len(probes) != 288 or len(rows) != 1488:
        raise ValueError("source record counts differ from the frozen pilot design")
    for row in rows:
        row["metrics"] = response_metrics(str(row["response"]))

    selected = select_blinded_sample(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    blind_rows: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for index, row in enumerate(selected, start=1):
        sample_id = f"D{index:03d}"
        blind_rows.append(
            {
                "sample_id": sample_id,
                "response_type": row["response_type"],
                "cap_status": row["cap_status"],
                "response_token_count": row["response_token_count"],
                "automated_metrics": row["metrics"],
                "response_text": row["response"],
            }
        )
        key_rows.append(
            {
                "sample_id": sample_id,
                "item_id": row["item_id"],
                "axis": row["axis"],
                "condition": row["condition"],
                "topic": row["topic"],
                "seed": row["seed"],
                "turn_or_checkpoint": row["turn_or_checkpoint"],
                "selection_rank_sha256": selection_rank(str(row["item_id"])),
            }
        )
        review_rows.append(
            {
                "sample_id": sample_id,
                "complete_ending": None,
                "coherent": None,
                "repetitive_loop": None,
                "list_or_heading_expansion": None,
                "obvious_length_instruction_noncompliance": None,
                "format_only_note": "",
            }
        )

    capped_rows = [row for row in rows if row["cap_status"] == "capped"]
    summary = {
        "protocol": "olmo_generation_failure_diagnostic_v2",
        "source_cap": cap,
        "source_manifest": str(args.source_manifest),
        "source_manifest_sha256": sha256(args.source_manifest),
        "source_hashes": manifest,
        "response_text_processed": True,
        "manual_response_text_inspected": False,
        "persona_outcomes_evaluated": False,
        "selection_salt": SELECTION_SALT,
        "sample_design": "one deterministic item from every populated response_type x axis x condition x cap_status cell",
        "sample_size": len(selected),
        "sample_cap_status_counts": dict(
            sorted(Counter(row["cap_status"] for row in selected).items())
        ),
        "tokenizer_audit": tokenizer_audit(config, rows),
        "overall": aggregate(rows),
        "capped_only": aggregate(capped_rows),
        "by_response_type_axis_condition": group_aggregates(rows),
    }
    atomic_jsonl(args.output_dir / "blinded_samples.jsonl", blind_rows)
    atomic_jsonl(args.output_dir / "sample_key.sealed.jsonl", key_rows)
    atomic_jsonl(args.output_dir / "format_review_template.jsonl", review_rows)
    atomic_json(args.output_dir / "automated_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
