from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from persona_drift.g1_manifest import canonical_json_bytes
from persona_drift.g1_local_reviewer import (
    LEDGER_SCHEMA_VERSION,
    OUTPUT_NORMALIZATION_CONTRACT,
    REVIEW_CONTRACT_SCHEMA_VERSION,
)
from persona_drift.g1_persona_stages import (
    CANDIDATE_COUNT,
    ITEMS_PER_CANDIDATE,
    PAIR_COUNT,
    PRIMARY_SLOTS,
    REPEATS_PER_PRIMARY,
    SOURCE_PACKET_PATH,
    PersonaStagePacketError,
    build_pair_stage_packet_from_ledgers,
    build_scalar_stage_packets,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_BYTES = (PROJECT_ROOT / SOURCE_PACKET_PATH).read_bytes()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ledger(stage, slot: str) -> bytes:
    packet_sha = _sha(stage.packet_bytes[slot])
    reviewer = {
        "base_model_family": f"family-{slot}",
        "model_id": f"example/{slot}",
        "model_revision": hashlib.sha1(slot.encode()).hexdigest(),
        "reviewer_role": "independent_primary_rater",
        "reviewer_slot_id": slot,
    }
    contract = {
        "schema_version": REVIEW_CONTRACT_SCHEMA_VERSION,
        "mode": "PRODUCTION",
        "packet_file_sha256": packet_sha,
        "reviewer": reviewer,
        "output_normalization": dict(OUTPUT_NORMALIZATION_CONTRACT),
    }
    contract_sha = _sha(canonical_json_bytes(contract))
    base_ids = {row["input_id"] for row in stage.base_inputs}
    previous = None
    records = []
    for line_number, row in enumerate(stage.packets[slot], start=1):
        is_original = row["input_id"] in base_ids
        response = {
            "candidate_anonymous_id": row["candidate_anonymous_id"],
            "definition": (
                f"{slot} definition for {row['candidate_anonymous_id']}"
                if is_original
                else "REPEAT-ONLY SENTINEL THAT MUST NOT ENTER PAIRS"
            ),
            "rationale": "Independent scalar review.",
            "scores": {
                "behavioral_observability": 2 if is_original else 1,
                "construct_consistency": 2,
                "distinctness": 2,
                "item_quality_diversity": 2,
                "pressure_opposability": 2,
                "safety_hhh_confound_separation": 2,
                "subject_frame_transfer": 2,
            },
        }
        row_bytes = canonical_json_bytes(row)
        raw_output = canonical_json_bytes(response).decode("utf-8")
        body = {
            "item": {
                "canonical_sha256": _sha(row_bytes),
                "item_id": row["input_id"],
                "line_number": line_number,
                "row_sha256": _sha(row_bytes),
                "task_id": "persona_scalar",
            },
            "mode": "PRODUCTION",
            "packet": {"file_sha256": packet_sha, "path": f"/{slot}.jsonl"},
            "previous_record_sha256": previous,
            "response": response,
            "response_canonical_sha256": _sha(canonical_json_bytes(response)),
            "raw_output": raw_output,
            "raw_output_sha256": _sha(raw_output.encode("utf-8")),
            "normalization": "none",
            "normalized_output_sha256": _sha(raw_output.encode("utf-8")),
            "review_contract": contract,
            "review_contract_sha256": contract_sha,
            "reviewer": reviewer,
            "schema_version": LEDGER_SCHEMA_VERSION,
            "status": "accepted",
        }
        record_hash = _sha(canonical_json_bytes(body))
        record = {**body, "record_sha256": record_hash}
        records.append(record)
        previous = record_hash
    return b"".join(canonical_json_bytes(row) + b"\n" for row in records)


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _all_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_keys(nested)


def test_scalar_packets_are_24_plus_three_blind_independent_repeats() -> None:
    first = build_scalar_stage_packets(SOURCE_BYTES)
    second = build_scalar_stage_packets(SOURCE_BYTES)
    assert first.manifest_bytes == second.manifest_bytes
    assert first.packet_bytes == second.packet_bytes
    assert len(first.base_inputs) == CANDIDATE_COUNT
    base_input_ids = {row["input_id"] for row in first.base_inputs}
    base_candidate_ids = {row["candidate_anonymous_id"] for row in first.base_inputs}
    repeat_input_ids = set()
    repeat_candidate_ids = set()

    for slot in PRIMARY_SLOTS:
        rows = first.packets[slot]
        assert len(rows) == CANDIDATE_COUNT + REPEATS_PER_PRIMARY == 27
        assert len({row["input_id"] for row in rows}) == 27
        originals = [row for row in rows if row["input_id"] in base_input_ids]
        assert len(originals) == CANDIDATE_COUNT
        assert {row["candidate_anonymous_id"] for row in originals} == base_candidate_ids
        repeats = [row for row in rows if row["input_id"] not in base_input_ids]
        assert len(repeats) == REPEATS_PER_PRIMARY == 3
        repeat_input_ids.update(row["input_id"] for row in repeats)
        repeat_candidate_ids.update(row["candidate_anonymous_id"] for row in repeats)
        assert first.packet_bytes[slot].endswith(b"\n")
        for row in rows:
            assert set(row) == {"candidate_anonymous_id", "input_id", "statements"}
            assert len(row["statements"]) == ITEMS_PER_CANDIDATE
            assert Counter(item["direction"] for item in row["statements"]) == {
                "Yes": 48,
                "No": 48,
            }
            assert set(_all_keys(row)).isdisjoint(
                {
                    "primary_slot",
                    "repeat_of",
                    "source_path",
                    "stable_source_item_id",
                    "candidate_trait_id",
                }
            )
    assert len(repeat_input_ids) == len(repeat_candidate_ids) == 9
    assert repeat_input_ids.isdisjoint(base_input_ids)
    assert repeat_candidate_ids.isdisjoint(base_candidate_ids)
    assert len(first.repeat_schedule) == 9
    for repeat in first.repeat_schedule:
        packet = first.packets[repeat["primary_slot"]]
        base_position = next(
            index
            for index, row in enumerate(packet, start=1)
            if row["input_id"] == repeat["base_input_id"]
        )
        assert abs(base_position - repeat["queue_position"]) > 1


def test_source_byte_lock_and_strict_rows_fail_closed() -> None:
    mutated = SOURCE_BYTES.replace(b'"statement": "', b'"statement": "mutated ', 1)
    with pytest.raises(PersonaStagePacketError, match="SHA256 mismatch"):
        build_scalar_stage_packets(mutated)
    with pytest.raises(PersonaStagePacketError, match="ending in one LF"):
        build_scalar_stage_packets(SOURCE_BYTES[:-1], expected_source_sha256=_sha(SOURCE_BYTES[:-1]))


def test_three_complete_ledgers_build_all_pairs_without_repeat_overwrite() -> None:
    scalar = build_scalar_stage_packets(SOURCE_BYTES)
    ledgers = {slot: _ledger(scalar, slot) for slot in PRIMARY_SLOTS}
    pair = build_pair_stage_packet_from_ledgers(
        SOURCE_BYTES,
        scalar_packet_bytes_by_slot=scalar.packet_bytes,
        scalar_ledger_bytes_by_slot=ledgers,
    )
    again = build_pair_stage_packet_from_ledgers(
        SOURCE_BYTES,
        scalar_packet_bytes_by_slot=scalar.packet_bytes,
        scalar_ledger_bytes_by_slot=ledgers,
    )
    assert pair.packet_bytes == again.packet_bytes
    assert pair.manifest_bytes == again.manifest_bytes
    assert len(pair.rows) == PAIR_COUNT == 276
    assert len({row["input_id"] for row in pair.rows}) == PAIR_COUNT
    unordered = {
        frozenset((row["candidate_a"]["id"], row["candidate_b"]["id"]))
        for row in pair.rows
    }
    assert len(unordered) == PAIR_COUNT
    for row in pair.rows:
        assert set(row) == {"candidate_a", "candidate_b", "input_id"}
        for candidate in (row["candidate_a"], row["candidate_b"]):
            assert set(candidate) == {"definition_evidence", "id"}
            assert len(candidate["definition_evidence"]) == 3
            assert all(
                definition.startswith("primary_0")
                for definition in candidate["definition_evidence"]
            )
            assert all("REPEAT-ONLY" not in definition for definition in candidate["definition_evidence"])
        assert "scores" not in set(_all_keys(row))
        assert "rationale" not in set(_all_keys(row))
    assert pair.manifest["blind_repeat_results"]["responses_kept_separate"] is True
    assert pair.manifest["blind_repeat_results"]["repeat_count"] == 9


def test_pair_builder_rejects_tampered_chain_and_incomplete_acceptance() -> None:
    scalar = build_scalar_stage_packets(SOURCE_BYTES)
    ledgers = {slot: _ledger(scalar, slot) for slot in PRIMARY_SLOTS}
    tampered = bytearray(ledgers["primary_01"])
    position = tampered.find(b'"status":"accepted"')
    tampered[position : position + len(b'"status":"accepted"')] = b'"status":"rejected"'
    ledgers["primary_01"] = bytes(tampered)
    with pytest.raises(PersonaStagePacketError, match="record hash mismatch"):
        build_pair_stage_packet_from_ledgers(
            SOURCE_BYTES,
            scalar_packet_bytes_by_slot=scalar.packet_bytes,
            scalar_ledger_bytes_by_slot=ledgers,
        )


def test_cli_scalar_and_pair_subcommands_write_exact_packets() -> None:
    scalar = build_scalar_stage_packets(SOURCE_BYTES)
    script = PROJECT_ROOT / "scripts/build_g1_persona_stage_packets.py"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        packet_paths = {
            slot: root / f"{slot}.jsonl" for slot in PRIMARY_SLOTS
        }
        manifest_path = root / "stage.yaml"
        common = [
            "--project-root",
            str(PROJECT_ROOT),
            "--manifest-output",
            str(manifest_path),
        ]
        for slot in PRIMARY_SLOTS:
            common.extend(
                [f"--{slot.replace('_', '-')}-packet", str(packet_paths[slot])]
            )
        completed = subprocess.run(
            [sys.executable, str(script), "scalar", *common],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        for slot in PRIMARY_SLOTS:
            assert packet_paths[slot].read_bytes() == scalar.packet_bytes[slot]

        ledger_paths = {}
        for slot in PRIMARY_SLOTS:
            ledger_paths[slot] = root / f"{slot}.ledger.jsonl"
            ledger_paths[slot].write_bytes(_ledger(scalar, slot))
        pair_path = root / "pairs.jsonl"
        pair_args = [sys.executable, str(script), "pair", *common]
        for slot in PRIMARY_SLOTS:
            pair_args.extend(
                [f"--{slot.replace('_', '-')}-ledger", str(ledger_paths[slot])]
            )
        pair_args.extend(["--pair-output", str(pair_path)])
        completed = subprocess.run(
            pair_args,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert len(pair_path.read_text(encoding="utf-8").splitlines()) == 276
