import json
import hashlib
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs" / "g1_reviewer_registry_v2_3.yaml"
AMENDMENT_1 = ROOT / "docs" / "gates" / "G1_reviewer_amendment_1.md"
AMENDMENT_2 = ROOT / "docs" / "gates" / "G1_reviewer_amendment_2.md"
AMENDMENT_3 = ROOT / "docs" / "gates" / "G1_reviewer_amendment_3.md"
AMENDMENT_4 = ROOT / "docs" / "gates" / "G1_reviewer_amendment_4.md"
AMENDMENT_5 = ROOT / "docs" / "gates" / "G1_reviewer_amendment_5.md"
AMENDMENT_6 = ROOT / "docs" / "gates" / "G1_reviewer_amendment_6.md"
AMENDED_REGISTRY = ROOT / "configs" / "g1_reviewer_registry_amendment_3_v2_3.yaml"
AMENDMENT_4_REGISTRY = ROOT / "configs/g1_reviewer_registry_amendment_4_v2_3.yaml"
AMENDMENT_5_REGISTRY = ROOT / "configs/g1_reviewer_registry_amendment_5_v2_3.yaml"
AMENDMENT_6_REGISTRY = ROOT / "configs/g1_reviewer_registry_amendment_6_v2_3.yaml"
FAILURE_REPORT = ROOT / "data" / "reports" / "g1_reviewer_production_failure_amendment_3_v2_3.json"
SMOKE_FAILURE_REPORT = ROOT / "data/reports/g1_reviewer_smoke_failure_amendment_4_v2_3.json"
AMENDMENT_5_FAILURE_REPORT = ROOT / "data/reports/g1_reviewer_smoke_failure_amendment_5_v2_3.json"
SCALAR_FAILURE_REPORT = ROOT / "data/reports/g1_persona_scalar_blind_repeat_failure_v2_3.json"
SMOKE = ROOT / "data" / "synthetic" / "g1_reviewer_smoke_v2_3.jsonl"
HEX40 = re.compile(r"[0-9a-f]{40}")


def test_registry_is_smoke_only_and_uses_five_distinct_families():
    payload = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    assert payload["registry_status"] == "frozen_for_synthetic_smoke"
    assert payload["synthetic_smoke_authorized"] is True
    assert payload["production_review_authorized"] is False
    assert payload["target_model_use"] == "forbidden"
    assert payload["runtime"]["local_files_only"] is True
    assert payload["runtime"]["trust_remote_code"] is False

    slots = payload["slots"]
    assert set(slots) == {
        "primary_01",
        "primary_02",
        "primary_03",
        "adjudicator_04",
        "scenario_writer",
    }
    assert len({entry["model_id"] for entry in slots.values()}) == 5
    assert len({entry["base_model_family"] for entry in slots.values()}) == 5
    for entry in slots.values():
        assert HEX40.fullmatch(entry["model_revision"])
        assert entry["local_snapshot"].endswith(entry["model_revision"])
        assert entry["license_spdx"] in {
            "Apache-2.0",
            "LicenseRef-TII-Falcon-LLM-2.0",
            "MIT",
        }
        assert entry["license_evidence_url"].startswith("https://huggingface.co/")


def test_reviewer_amendment_2_replaces_primary_03_without_authorizing_production():
    payload = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    primary_03 = payload["slots"]["primary_03"]
    assert primary_03 == {
        "role": "independent_primary_rater",
        "model_id": "tiiuae/Falcon3-10B-Instruct",
        "model_revision": "8799bc6aec0152757221dc6b272d824642db6202",
        "base_model_family": "falcon3",
        "local_snapshot": (
            "/home/minzhong/Data/huggingface/hub/"
            "models--tiiuae--Falcon3-10B-Instruct/snapshots/"
            "8799bc6aec0152757221dc6b272d824642db6202"
        ),
        "license_spdx": "LicenseRef-TII-Falcon-LLM-2.0",
        "license_evidence_url": (
            "https://huggingface.co/tiiuae/Falcon3-10B-Instruct/blob/"
            "8799bc6aec0152757221dc6b272d824642db6202/README.md"
        ),
    }
    primary_families = {
        payload["slots"][slot]["base_model_family"]
        for slot in ("primary_01", "primary_02", "primary_03")
    }
    assert primary_families == {"qwen2", "granite", "falcon3"}
    assert payload["production_review_authorized"] is False


def test_reviewer_amendment_1_records_failure_and_forbidden_workarounds():
    amendment = AMENDMENT_1.read_text(encoding="utf-8")
    assert "3 of 6" in amendment
    assert "doubly escaped enum value" in amendment
    assert "omitted required field" in amendment
    assert "unquoted JSON enum value" in amendment
    for forbidden in ("Parser relaxation", "output repair", "retry-until-valid"):
        assert forbidden in amendment
    assert "production_review_authorized: false" in amendment


def test_reviewer_amendment_2_records_failure_and_forbidden_workarounds():
    amendment = AMENDMENT_2.read_text(encoding="utf-8")
    assert "5 of 6" in amendment
    assert "integer score values as JSON" in amendment
    assert "strings instead of JSON integers" in amendment
    for forbidden in ("Parser coercion", "prompt accommodation", "retry"):
        assert forbidden in amendment
    assert "production_review_authorized: false" in amendment


def test_smoke_fixture_is_synthetic_and_covers_all_required_task_shapes():
    rows = [json.loads(line) for line in SMOKE.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 7
    assert {row["task"] for row in rows} == {
        "persona_scalar",
        "persona_pair",
        "persona_family",
        "topic_triage",
        "topic_suitability",
        "scenario_writer",
        "scenario_qa",
    }
    assert len({row["input_id"] for row in rows}) == len(rows)
    assert all(row["input_id"].startswith("SYN-") for row in rows)
    serialized = SMOKE.read_text(encoding="utf-8")
    assert "PC-9fad" not in serialized
    assert "TOP-0003" not in serialized


def test_amendment_3_failure_report_is_status_only_and_quarantines_every_row():
    report = json.loads(FAILURE_REPORT.read_text(encoding="utf-8"))
    assert report["inspection_scope"] == {
        "record_status_inspected": True,
        "error_category_inspected": True,
        "semantic_scores_inspected": False,
        "rationales_inspected": False,
    }
    assert report["ledgers"] == {
        "primary_01": {
            "records": 27,
            "accepted": 26,
            "invalid": 1,
            "ledger_sha256": "08793e75de9da795afa3277b3aa90311443609e72b7ee09028933382588b0910",
            "chain_head": "9ee72f1b63a2ac59c741e629e1e51bd737d6633ef7d9bc561b455092180f3345",
            "error_categories": {"integer_type_violation": 1},
        },
        "primary_02": {
            "records": 27,
            "accepted": 24,
            "invalid": 3,
            "ledger_sha256": "18628acf2a1379250b0fcd30ad0c30c39f5d53d15674c1b4944710c8ac1032da",
            "chain_head": "d9427464ce6bc0d19f13f1777e26c343023b4df52295247c6d7203491cdd7850",
            "error_categories": {
                "integer_type_violation": 2,
                "duplicate_json_key": 1,
            },
        },
    }
    assert report["quarantine"]["all_current_production_ratings"] is True
    assert report["quarantine"]["reuse_accepted_rows"] is False
    assert report["quarantine"]["rerun_only_failed_items"] is False
    assert report["ratings_generated_by_report"] is False
    assert report["all_required_reviews_complete"] is False
    assert report["g1_pass"] is False
    amendment = AMENDMENT_3.read_text(encoding="utf-8")
    for forbidden in ("Retry", "repair", "coercion", "parser relaxation"):
        assert forbidden in amendment


def test_amendment_3_registry_is_schema_stress_only_and_not_production():
    registry = yaml.safe_load(AMENDED_REGISTRY.read_text(encoding="utf-8"))
    prior_registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    assert registry["registry_status"] == "frozen_for_synthetic_smoke"
    assert registry["synthetic_smoke_authorized"] is True
    assert registry["production_review_authorized"] is False
    assert registry["runtime"]["schema_constrained_decoding"] == {
        "required": True,
        "backend": "lm-format-enforcer",
        "version": "0.11.2",
    }
    assert registry["slots"] == prior_registry["slots"]
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"lm-format-enforcer==0.11.2"' in pyproject
    phase2 = yaml.safe_load((ROOT / "configs/g1_phase2_v2_3.yaml").read_text())
    assert phase2["ratings_generated"] is False
    assert phase2["authorization_guard"]["all_required_reviews_complete"] is False
    old_production = ROOT / "configs/g1_reviewer_registry_production_v2_3.yaml"
    assert hashlib.sha256(old_production.read_bytes()).hexdigest() == (
        "93f3c5571057b66afd6134725a56166e303382b22e94dd14bb856413711ac877"
    )


def test_amendment_4_quarantines_failed_smoke_and_freezes_decoder_policy():
    report = json.loads(SMOKE_FAILURE_REPORT.read_text(encoding="utf-8"))
    assert report["source_commit"] == "fe34d1a0e959d95a89b157bae4635e5455444bc4"
    assert report["inspection_scope"]["production_scores_inspected"] is False
    assert report["inspection_scope"]["production_rationales_inspected"] is False
    assert report["ledgers"]["primary_03"]["accepted"] == 4
    assert report["ledgers"]["primary_03"]["invalid"] == 2
    assert {
        row["task_id"]: row["reencoded_token_count"]
        for row in report["ledgers"]["primary_03"]["invalid_records"]
    } == {
        "persona_scalar": 355,
        "topic_suitability": 1024,
    }
    assert report["quarantine"] == {
        "all_amendment_3_smoke_ledgers": True,
        "complete_remaining_slots": False,
        "preserve_ledgers": True,
        "rerun_only_failed_items": False,
        "reuse_accepted_rows": False,
    }
    registry = yaml.safe_load(AMENDMENT_4_REGISTRY.read_text(encoding="utf-8"))
    assert registry["production_review_authorized"] is False
    assert registry["registry_status"] == "frozen_for_synthetic_smoke"
    assert registry["runtime"]["schema_constrained_decoding"] == {
        "required": True,
        "backend": "lm-format-enforcer",
        "version": "0.11.2",
        "tokenizer_decoder_policy": (
            "exact_decode_cleanup_false_no_replacement_strip_v1"
        ),
    }
    assert registry["slots"] == yaml.safe_load(
        AMENDED_REGISTRY.read_text(encoding="utf-8")
    )["slots"]
    amendment = AMENDMENT_4.read_text(encoding="utf-8")
    for forbidden in (
        "repair model output",
        "coerce a value",
        "relax a response schema",
        "add a retry",
    ):
        assert forbidden in amendment
    assert "production_review_authorized: false" in amendment


def test_amendment_5_quarantines_token_limit_failure_and_bounds_rationale():
    report = json.loads(AMENDMENT_5_FAILURE_REPORT.read_text(encoding="utf-8"))
    assert report["source_commit"] == "d84e824b8eeba2c52865655fffa0a8126a10bf52"
    assert report["ledger"]["slot_id"] == "primary_03"
    assert report["ledger"]["accepted"] == 5
    assert report["ledger"]["invalid"] == 1
    assert report["ledger"]["invalid_record"] == {
        "error_class": "unterminated_string",
        "raw_character_count": 1633,
        "raw_output_sha256": (
            "c20fb05e2dafe2abd7afcf13dabb1bf57751c17159666dc099317f8f872120db"
        ),
        "reencoded_token_count": 1024,
        "task_id": "topic_suitability",
    }
    assert report["quarantine"]["all_amendment_4_smoke_rows"] is True
    assert report["quarantine"]["rerun_only_failed_item"] is False
    registry = yaml.safe_load(AMENDMENT_5_REGISTRY.read_text(encoding="utf-8"))
    prior = yaml.safe_load(AMENDMENT_4_REGISTRY.read_text(encoding="utf-8"))
    assert registry["production_review_authorized"] is False
    assert registry["slots"] == prior["slots"]
    assert registry["runtime"] == prior["runtime"]
    amendment = AMENDMENT_5.read_text(encoding="utf-8")
    assert "reduced from 2048" in amendment
    assert "to 1024 characters" in amendment
    for forbidden in ("truncate", "repair", "coerce", "parse-relax", "retry"):
        assert forbidden in amendment
    assert "production_review_authorized: false" in amendment


def test_amendment_6_is_one_prospective_recalibration_without_id_scoring():
    report = json.loads(SCALAR_FAILURE_REPORT.read_text(encoding="utf-8"))
    assert report["status"] == "FAIL_CLOSED_RECALIBRATION_REQUIRED"
    assert report["blind_repeat"]["exact_rating_vector_match_count"] == 6
    assert report["blind_repeat"]["repeat_count"] == 9
    assert report["blind_repeat"]["passed"] is False
    assert report["protocol_actions"]["recalibration_cycles_completed"] == 0
    registry = yaml.safe_load(AMENDMENT_6_REGISTRY.read_text(encoding="utf-8"))
    prior = yaml.safe_load(AMENDMENT_5_REGISTRY.read_text(encoding="utf-8"))
    assert registry["production_review_authorized"] is False
    assert registry["registry_status"] == "frozen_for_synthetic_smoke"
    assert registry["slots"] == prior["slots"]
    assert registry["runtime"] == prior["runtime"]
    prompts = yaml.safe_load(
        (ROOT / "data/rater_specs/g1_local_reviewer_prompts_v2_3.yaml").read_text()
    )
    scalar = prompts["tasks"]["persona_scalar"]
    assert "candidate_anonymous_id" not in scalar["response_schema"]["properties"]
    assert scalar["packet_expected_schema"]["required_keys"] == [
        "definition",
        "scores",
        "rationale",
    ]
    amendment = AMENDMENT_6.read_text(encoding="utf-8")
    for required in (
        "same 24 candidates",
        "0.85",
        "one recalibration cycle",
        "must not start",
    ):
        assert required in amendment
    assert "production_review_authorized: false" in amendment
