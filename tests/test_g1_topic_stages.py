from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from persona_drift.g1_local_reviewer import LEDGER_SCHEMA_VERSION
from persona_drift.g1_topic_screening import RATER_RECORD_SCHEMA_VERSION
from persona_drift.g1_topic_stages import (
    TopicStageError,
    build_topic_stage_packets,
)
from persona_drift.g1_topics import canonical_json_bytes


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_jsonl(path: Path, rows) -> bytes:
    payload = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def packet_row(index: int, *, prefix: int = 0) -> dict:
    blind_id = f"TOP-{prefix + index:024x}"
    return {
        "schema_version": RATER_RECORD_SCHEMA_VERSION,
        "blind_item_id": blind_id,
        "content": {
            "prompt": f"Anonymous question {index}?",
            "options": [
                {"label": "A", "text": "First option"},
                {"label": "B", "text": "Second option"},
            ],
            "stable_reference": {
                "type": "keyed_correct_option",
                "reference_label": "A",
                "reference_text": "First option",
                "reference_rationale_status": "unavailable_in_locked_source",
            },
        },
    }


def make_ledger(
    path: Path,
    *,
    slot: str,
    family: str,
    packet_rows: list[dict],
    packet_payload: bytes,
    ratings: dict[str, str],
) -> None:
    reviewer = {
        "reviewer_slot_id": slot,
        "reviewer_role": "independent_primary_rater",
        "model_id": f"model-{slot}",
        "model_revision": "a" * 40 if slot == "primary_01" else "b" * 40,
        "base_model_family": family,
    }
    contract = {
        "schema_version": "restart-v2.3-g1-local-review-contract-v1",
        "mode": "PRODUCTION",
        "reviewer": reviewer,
        "registry_file_sha256": "1" * 64,
        "registry_canonical_sha256": "2" * 64,
        "prompt_catalog_file_sha256": "3" * 64,
        "prompt_catalog_canonical_sha256": "4" * 64,
        "packet_file_sha256": sha256(packet_payload),
        "decoding_canonical_sha256": "5" * 64,
        "decoding": {
            "do_sample": False,
            "temperature": 0.0,
            "top_p": 1.0,
            "max_new_tokens": 128,
        },
        "batch_size": 1,
    }
    contract_hash = sha256(canonical_json_bytes(contract))
    records = []
    previous = None
    for line_number, packet in enumerate(packet_rows, start=1):
        blind_id = packet["blind_item_id"]
        response = {
            "blind_item_id": blind_id,
            "rating": ratings[blind_id],
            "rationale": "Independent real triage rationale.",
        }
        raw_output = canonical_json_bytes(response).decode("utf-8")
        body = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "attempt_id": f"ATT-{slot}-{line_number:04d}",
            "started_at_utc": "2026-08-28T00:00:00.000000Z",
            "finished_at_utc": "2026-08-28T00:00:01.000000Z",
            "mode": "PRODUCTION",
            "status": "accepted",
            "review_contract_sha256": contract_hash,
            "review_contract": contract,
            "reviewer": {**reviewer, "model_snapshot_path": f"/models/{slot}"},
            "runtime_provenance": {"network_used": False},
            "packet": {"path": "/anonymous/mmlu.jsonl", "file_sha256": sha256(packet_payload)},
            "item": {
                "item_id": blind_id,
                "id_field": "blind_item_id",
                "task_id": "topic_triage",
                "line_number": line_number,
                "row_sha256": sha256(canonical_json_bytes(packet)),
                "canonical_sha256": sha256(canonical_json_bytes(packet)),
            },
            "prompt": {},
            "decoding": {},
            "raw_output": raw_output,
            "raw_output_sha256": sha256(raw_output.encode("utf-8")),
            "response": response,
            "response_canonical_sha256": sha256(canonical_json_bytes(response)),
            "error": None,
            "previous_record_sha256": previous,
        }
        record_hash = sha256(canonical_json_bytes(body))
        records.append({**body, "record_sha256": record_hash})
        previous = record_hash
    write_jsonl(path, records)


def all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_keys(child)


class TopicStagePacketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.mmlu_path = self.root / "mmlu.jsonl"
        self.anthropic_path = self.root / "anthropic.jsonl"
        self.primary_01_path = self.root / "primary_01.jsonl"
        self.primary_02_path = self.root / "primary_02.jsonl"
        self.initial_path = self.root / "initial.jsonl"
        self.remaining_path = self.root / "remaining.jsonl"
        self.manifest_path = self.root / "join.yaml"
        self.mmlu_rows = [packet_row(index) for index in range(10)]
        self.anthropic_rows = [packet_row(index, prefix=10_000) for index in range(2)]
        self.mmlu_payload = write_jsonl(self.mmlu_path, self.mmlu_rows)
        write_jsonl(self.anthropic_path, self.anthropic_rows)
        ids = [row["blind_item_id"] for row in self.mmlu_rows]
        primary_01_ratings = {
            item: ("reject" if index < 3 else "advance")
            for index, item in enumerate(ids)
        }
        primary_02_ratings = {
            item: ("reject" if index < 3 else "uncertain")
            for index, item in enumerate(ids)
        }
        make_ledger(
            self.primary_01_path,
            slot="primary_01",
            family="family-a",
            packet_rows=self.mmlu_rows,
            packet_payload=self.mmlu_payload,
            ratings=primary_01_ratings,
        )
        make_ledger(
            self.primary_02_path,
            slot="primary_02",
            family="family-b",
            packet_rows=self.mmlu_rows,
            packet_payload=self.mmlu_payload,
            ratings=primary_02_ratings,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build(self):
        return build_topic_stage_packets(
            self.root,
            primary_01_results_path=self.primary_01_path,
            primary_02_results_path=self.primary_02_path,
            mmlu_packet_path=self.mmlu_path,
            anthropic_packet_path=self.anthropic_path,
            screening_manifest_path=None,
            initial_writer_output_path=self.initial_path,
            remaining_double_reject_output_path=self.remaining_path,
            join_manifest_output_path=self.manifest_path,
            expected_mmlu_count=10,
            expected_anthropic_count=2,
        )

    def test_exact_join_audit_and_stage_packets(self) -> None:
        manifest = self.build()
        self.assertEqual(manifest["triage_sets"]["U"]["count"], 7)
        self.assertEqual(manifest["triage_sets"]["D"]["count"], 3)
        self.assertEqual(manifest["triage_sets"]["A"]["count"], 1)
        self.assertEqual(manifest["triage_sets"]["R"]["count"], 2)

        initial = [json.loads(line) for line in self.initial_path.read_text().splitlines()]
        remaining = [json.loads(line) for line in self.remaining_path.read_text().splitlines()]
        self.assertEqual(len(initial), 10)  # U + ceil(10% of D) + Anthropic
        self.assertEqual(len(remaining), 2)
        self.assertEqual(
            [row["blind_item_id"] for row in initial],
            sorted(row["blind_item_id"] for row in initial),
        )
        self.assertTrue(
            set(row["blind_item_id"] for row in initial).isdisjoint(
                row["blind_item_id"] for row in remaining
            )
        )
        source_by_id = {
            row["blind_item_id"]: row
            for row in self.mmlu_rows + self.anthropic_rows
        }
        for row in initial + remaining:
            self.assertEqual(row, source_by_id[row["blind_item_id"]])
            self.assertTrue(
                {"rating", "rationale", "model_id", "audit_selected", "scenario_card"}.isdisjoint(
                    all_keys(row)
                )
            )
        self.assertFalse(manifest["scenario_cards_generated"])
        self.assertFalse(manifest["scenario_writer_execution_authorized_by_this_manifest"])

    def test_rebuild_is_byte_deterministic(self) -> None:
        first = self.build()
        payloads = (
            self.initial_path.read_bytes(),
            self.remaining_path.read_bytes(),
            self.manifest_path.read_bytes(),
        )
        second = self.build()
        self.assertEqual(first, second)
        self.assertEqual(
            payloads,
            (
                self.initial_path.read_bytes(),
                self.remaining_path.read_bytes(),
                self.manifest_path.read_bytes(),
            ),
        )

    def test_incomplete_accepted_join_fails_closed(self) -> None:
        rows = self.primary_02_path.read_text().splitlines()
        self.primary_02_path.write_text("\n".join(rows[:-1]) + "\n")
        with self.assertRaisesRegex(TopicStageError, "incomplete"):
            self.build()

    def test_tampered_hash_chain_fails_closed(self) -> None:
        records = [json.loads(line) for line in self.primary_01_path.read_text().splitlines()]
        records[0]["response"]["rating"] = "advance"
        write_jsonl(self.primary_01_path, records)
        with self.assertRaisesRegex(TopicStageError, "record_sha256 mismatch"):
            self.build()


if __name__ == "__main__":
    unittest.main()
