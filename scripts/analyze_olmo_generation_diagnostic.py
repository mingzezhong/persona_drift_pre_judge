#!/usr/bin/env python3
"""Apply the frozen remediation rule to the OLMo format diagnostic."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any


BOOLEAN_LABELS = (
    "complete_ending",
    "coherent",
    "repetitive_loop",
    "list_or_heading_expansion",
    "obvious_length_instruction_noncompliance",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    return rows


def choose_remediation(
    *,
    termination_pass: bool,
    capped_duplicate_rate: float,
    reviewed_capped_repetition_rate: float,
    format_compliance_rate: float,
    reviewed_capped_noncompliance_rate: float,
) -> tuple[str, dict[str, bool]]:
    checks = {
        "termination_failure": not termination_pass,
        "repetition_failure": (
            capped_duplicate_rate >= 0.25
            or reviewed_capped_repetition_rate >= 0.25
        ),
        "format_instruction_failure": (
            format_compliance_rate < 0.80
            or reviewed_capped_noncompliance_rate >= 0.25
        ),
    }
    if checks["termination_failure"]:
        selected = "repair_termination"
    elif checks["repetition_failure"]:
        selected = "repetition_control_pilot"
    elif checks["format_instruction_failure"]:
        selected = "prompt_salience_pilot"
    else:
        selected = "cap_512_768_pilot"
    return selected, checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--automated-summary", type=Path, required=True)
    parser.add_argument("--blinded-samples", type=Path, required=True)
    parser.add_argument("--format-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")

    summary = load_json(args.automated_summary)
    samples = load_jsonl(args.blinded_samples)
    reviews = load_jsonl(args.format_review)
    sample_status = {str(row["sample_id"]): str(row["cap_status"]) for row in samples}
    review_by_id = {str(row["sample_id"]): row for row in reviews}
    if len(sample_status) != len(samples) or len(review_by_id) != len(reviews):
        raise ValueError("duplicate sample or review ID")
    if set(sample_status) != set(review_by_id):
        raise ValueError("review coverage does not match blinded samples")
    for sample_id, row in review_by_id.items():
        for label in BOOLEAN_LABELS:
            if not isinstance(row.get(label), bool):
                raise ValueError(f"{sample_id} has non-Boolean label {label}")
        note = row.get("format_only_note")
        if not isinstance(note, str):
            raise ValueError(f"{sample_id} has a non-string note")

    capped = [
        review_by_id[sample_id]
        for sample_id, status in sample_status.items()
        if status == "capped"
    ]
    stopped = [
        review_by_id[sample_id]
        for sample_id, status in sample_status.items()
        if status == "stopped"
    ]
    if not capped or not stopped:
        raise ValueError("review must contain capped and stopped samples")

    def label_rates(rows: list[dict[str, Any]]) -> dict[str, float]:
        return {
            label: sum(bool(row[label]) for row in rows) / len(rows)
            for label in BOOLEAN_LABELS
        }

    capped_rates = label_rates(capped)
    stopped_rates = label_rates(stopped)
    selected, checks = choose_remediation(
        termination_pass=bool(summary["tokenizer_audit"]["pass"]),
        capped_duplicate_rate=float(
            summary["capped_only"]["duplicate_4gram_ge_0_15_rate"]
        ),
        reviewed_capped_repetition_rate=capped_rates["repetitive_loop"],
        format_compliance_rate=float(summary["overall"]["format_compliance_rate"]),
        reviewed_capped_noncompliance_rate=capped_rates[
            "obvious_length_instruction_noncompliance"
        ],
    )
    result = {
        "protocol": "olmo_generation_failure_diagnostic_v2",
        "decision_rule": "termination_then_repetition_then_format_then_larger_cap",
        "selected_remediation": selected,
        "checks": checks,
        "thresholds": {
            "capped_duplicate_4gram_ge_0_15_rate": 0.25,
            "reviewed_capped_repetitive_loop_rate": 0.25,
            "full_corpus_format_compliance_rate": 0.80,
            "reviewed_capped_instruction_noncompliance_rate": 0.25,
        },
        "evidence": {
            "termination_audit_pass": bool(summary["tokenizer_audit"]["pass"]),
            "capped_duplicate_4gram_ge_0_15_rate": summary["capped_only"][
                "duplicate_4gram_ge_0_15_rate"
            ],
            "full_corpus_format_compliance_rate": summary["overall"][
                "format_compliance_rate"
            ],
            "reviewed_samples": len(reviews),
            "reviewed_cap_status_counts": dict(sorted(Counter(sample_status.values()).items())),
            "reviewed_capped_label_rates": capped_rates,
            "reviewed_stopped_label_rates": stopped_rates,
        },
        "manual_response_text_inspected": True,
        "sample_key_opened": False,
        "persona_outcomes_evaluated": False,
        "formal_replication_authorized": False,
        "inputs": {
            "automated_summary_sha256": sha256(args.automated_summary),
            "blinded_samples_sha256": sha256(args.blinded_samples),
            "format_review_sha256": sha256(args.format_review),
        },
    }
    partial = args.output.with_suffix(args.output.suffix + ".partial")
    partial.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    partial.replace(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
