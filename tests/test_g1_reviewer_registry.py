import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs" / "g1_reviewer_registry_v2_3.yaml"
AMENDMENT_1 = ROOT / "docs" / "gates" / "G1_reviewer_amendment_1.md"
AMENDMENT_2 = ROOT / "docs" / "gates" / "G1_reviewer_amendment_2.md"
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
