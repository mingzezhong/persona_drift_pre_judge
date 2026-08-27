from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from persona_drift.g1_local_reviewer import (
    assigned_items,
    canonical_json_bytes,
    prepare_review,
    runner_implementation_binding,
    run_review,
)
from persona_drift.g1_reviewer_promotion import (
    SLOT_IDS,
    ReviewerPromotionError,
    promote_g1_reviewer_registry,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/g1_reviewer_registry_v2_3.yaml"
PROMPTS = ROOT / "data/rater_specs/g1_local_reviewer_prompts_v2_3.yaml"
SMOKE = ROOT / "data/synthetic/g1_reviewer_smoke_v2_3.jsonl"
FIXED_TIME = datetime(2026, 8, 28, tzinfo=timezone.utc)


class QueueBackend:
    def __init__(self, outputs: list[str], prepared) -> None:
        self.outputs = outputs
        core_hashes = {"config.json": "a" * 64}
        identity = prepared.registry.identity
        self._provenance = {
            "snapshot_path": str(identity.snapshot_path.resolve()),
            "snapshot_revision": identity.revision,
            "core_file_sha256s": core_hashes,
            "core_manifest_sha256": hashlib.sha256(
                canonical_json_bytes(core_hashes)
            ).hexdigest(),
            "python_version": "3.11.0",
            "torch_version": prepared.registry.runtime["torch_version"],
            "transformers_version": prepared.registry.runtime["framework_version"],
            "cuda_version": "12.8",
            "cuda_available": True,
            "cuda_device_count": 1,
            "cuda_device_names": ["synthetic-test-gpu"],
            "hostname": "unit-test-host",
            "offline_environment": {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            },
        }

    @property
    def provenance(self):
        return self._provenance

    def generate(self, messages, decoder):
        assert messages
        assert decoder.max_new_tokens > 0
        return self.outputs.pop(0)


def _response_for(item) -> str:
    payload = item.input_value
    if item.task_id == "persona_scalar":
        value = {
            "candidate_anonymous_id": payload["candidate_anonymous_id"],
            "definition": "Prefers preserving reversible options.",
            "scores": {
                "construct_consistency": 2,
                "behavioral_observability": 2,
                "pressure_opposability": 2,
                "distinctness": 2,
                "safety_hhh_confound_separation": 2,
                "subject_frame_transfer": 2,
                "item_quality_diversity": 2,
            },
            "rationale": "The statements support one observable construct.",
        }
    elif item.task_id == "persona_pair":
        value = {
            "candidate_a_id": payload["candidate_a"]["id"],
            "candidate_b_id": payload["candidate_b"]["id"],
            "relation_label": "opposite_poles_of_one_axis",
            "rationale": "The candidates prefer opposite commitment policies.",
        }
    elif item.task_id == "persona_family":
        value = {
            "candidate_id": payload["candidate_id"],
            "family_id": payload["family_options"][0],
            "rationale": "The definition concerns decisions under uncertainty.",
        }
    elif item.task_id == "topic_triage":
        value = {
            "blind_item_id": payload["blind_item_id"],
            "rating": "advance",
            "rationale": "The item has a stable keyed reference.",
        }
    elif item.task_id == "topic_suitability":
        value = {
            "blind_item_id": payload["blind_item_id"],
            "scores": {
                "twenty_five_turn_extensibility": 2,
                "persona_expression_opportunity": 2,
                "pressure_compatibility": 2,
                "stable_reference_or_stance": 2,
                "safety_confound_separation": 2,
            },
            "rationale": "The decision can be extended with a stable frame.",
        }
    elif item.task_id == "scenario_writer":
        value = {
            "blind_item_id": payload["blind_item_id"],
            "scenario_summary": "Review conservation evidence in stages.",
            "moves": [
                {
                    "move_index": index,
                    "move_text": f"Discuss evidence component {index}.",
                }
                for index in range(1, 26)
            ],
        }
    elif item.task_id == "scenario_qa":
        value = {
            "blind_item_id": payload["blind_item_id"],
            "checks": {
                "topical_coherence": "pass",
                "nonredundancy": "pass",
                "pressure_absence": "pass",
                "persona_neutrality": "pass",
                "safety_confound_separation": "pass",
            },
            "rationale": "Every listed check passes.",
        }
    else:  # pragma: no cover - frozen fixture exhausts this branch
        raise AssertionError(item.task_id)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _real_runner_ledgers(directory: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for slot in SLOT_IDS:
        prepared = prepare_review(
            registry_path=REGISTRY,
            reviewer_slot_id=slot,
            prompts_path=PROMPTS,
            packet_path=SMOKE,
        )
        items = assigned_items(prepared)
        output = directory / f"{slot}.jsonl"
        attempt_ids = iter(
            f"ATT-{slot}-{index}" for index in range(1, len(items) + 1)
        )
        run_review(
            prepared,
            output_path=output,
            backend=QueueBackend([_response_for(item) for item in items], prepared),
            clock=lambda: FIXED_TIME,
            attempt_id_factory=lambda: next(attempt_ids),
        )
        paths[slot] = output
    return paths


def _promote(
    ledger_paths: dict[str, Path],
    report: Path,
    production: Path,
):
    return promote_g1_reviewer_registry(
        registry_path=REGISTRY,
        ledger_paths_by_slot=ledger_paths,
        synthetic_packet_path=SMOKE,
        prompt_catalog_path=PROMPTS,
        report_output_path=report,
        production_registry_output_path=production,
    )


def test_five_complete_runner_ledgers_promote_without_overwriting_source(
    tmp_path: Path,
) -> None:
    ledgers = _real_runner_ledgers(tmp_path / "ledgers")
    report_path = tmp_path / "data/reports/g1_reviewer_synthetic_smoke_v2_3.json"
    production_path = (
        tmp_path / "configs/g1_reviewer_registry_production_v2_3.yaml"
    )
    source_before = REGISTRY.read_bytes()

    artifacts = _promote(ledgers, report_path, production_path)

    assert REGISTRY.read_bytes() == source_before
    assert report_path.read_bytes() == artifacts.report_bytes
    assert production_path.read_bytes() == artifacts.production_registry_bytes
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["validation"] == {
        "required_slot_count": 5,
        "validated_slot_count": 5,
        "all_hash_chains_valid": True,
        "all_expected_tasks_accepted": True,
        "all_records_synthetic_only": True,
        "models_and_contracts_match_registry": True,
    }
    assert {
        slot: len(report["slots"][slot]["accepted_items"]) for slot in SLOT_IDS
    } == {
        "primary_01": 6,
        "primary_02": 6,
        "primary_03": 6,
        "adjudicator_04": 4,
        "scenario_writer": 1,
    }
    source_registry = yaml.safe_load(source_before)
    production_registry = yaml.safe_load(production_path.read_bytes())
    assert source_registry["registry_status"] == "frozen_for_synthetic_smoke"
    assert source_registry["production_review_authorized"] is False
    assert production_registry["registry_status"] == "frozen_for_production"
    assert production_registry["production_review_authorized"] is True
    assert production_registry["runner_implementation"] == runner_implementation_binding()
    assert {
        key: value
        for key, value in source_registry.items()
        if key
        not in {
            "registry_status",
            "production_review_authorized",
            "runner_implementation",
        }
    } == {
        key: value
        for key, value in production_registry.items()
        if key
        not in {
            "registry_status",
            "production_review_authorized",
            "runner_implementation",
        }
    }


def test_missing_fifth_real_ledger_fails_closed_without_outputs(
    tmp_path: Path,
) -> None:
    ledgers = _real_runner_ledgers(tmp_path / "ledgers")
    ledgers["scenario_writer"].unlink()
    report_path = tmp_path / "report.json"
    production_path = tmp_path / "production.yaml"

    with pytest.raises(ReviewerPromotionError, match="scenario_writer.*missing"):
        _promote(ledgers, report_path, production_path)

    assert not report_path.exists()
    assert not production_path.exists()


def test_rechained_runner_binding_for_other_bytes_is_rejected(
    tmp_path: Path,
) -> None:
    ledgers = _real_runner_ledgers(tmp_path / "ledgers")
    target = ledgers["primary_01"]
    records = [
        json.loads(line)
        for line in target.read_text(encoding="utf-8").splitlines()
    ]
    previous = None
    for record in records:
        implementation = record["review_contract"]["runner_implementation"]
        implementation["file_sha256s"][
            "scripts/run_g1_local_reviewer.py"
        ] = "0" * 64
        implementation["canonical_sha256"] = hashlib.sha256(
            canonical_json_bytes(implementation["file_sha256s"])
        ).hexdigest()
        record["review_contract_sha256"] = hashlib.sha256(
            canonical_json_bytes(record["review_contract"])
        ).hexdigest()
        record["previous_record_sha256"] = previous
        record.pop("record_sha256")
        previous = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
        record["record_sha256"] = previous
    target.write_bytes(
        b"".join(canonical_json_bytes(record) + b"\n" for record in records)
    )
    report_path = tmp_path / "report.json"
    production_path = tmp_path / "production.yaml"

    with pytest.raises(ReviewerPromotionError, match="current exact bytes"):
        _promote(ledgers, report_path, production_path)

    assert not report_path.exists()
    assert not production_path.exists()


def test_rechained_production_item_id_is_still_rejected(
    tmp_path: Path,
) -> None:
    ledgers = _real_runner_ledgers(tmp_path / "ledgers")
    target = ledgers["primary_01"]
    records = [
        json.loads(line)
        for line in target.read_text(encoding="utf-8").splitlines()
    ]
    records[0]["item"]["item_id"] = "TOP-PRODUCTION-001"
    previous = None
    for record in records:
        record["previous_record_sha256"] = previous
        record.pop("record_sha256")
        previous = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
        record["record_sha256"] = previous
    target.write_bytes(
        b"".join(canonical_json_bytes(record) + b"\n" for record in records)
    )
    report_path = tmp_path / "report.json"
    production_path = tmp_path / "production.yaml"

    with pytest.raises(ReviewerPromotionError, match="production item ID"):
        _promote(ledgers, report_path, production_path)

    assert not report_path.exists()
    assert not production_path.exists()
