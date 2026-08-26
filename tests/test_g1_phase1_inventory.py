import json
from pathlib import Path
import subprocess
import sys

import yaml

from persona_drift.g1_manifest import (
    CANONICALIZATION_VERSION,
    ReadinessStatus,
    canonical_structured_file_sha256,
    evaluate_g1_readiness,
    file_bytes_sha256,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY_ROOT / "configs" / "g1_v2_3.yaml"

EXPECTED_ARTIFACT_HASHES = {
    "public-persona-sources": (
        "4a037e001a7041613ac6742bebba6c85cc0ee2bce436840396781521395ab3d5",
        "8dc497a1f59f2ccd5893286c2f57d0dc0f41b9a654a99bdccbc42212720b3965",
    ),
    "persona-candidate-pool": (
        "7e74b4189ceb2a462fe0651b82be2b16f113aa4133a6dc5dd14f49ba4d635334",
        "7d245b824849b487ee83464167725dcb472d97312014d3ed271fcb76fe0276a9",
    ),
    "persona-sampling-frame-draft": (
        "490d9cfc5bd78079c4e990ce9e520ab2b8a5d74af5d96b204a25256cd1346be5",
        "9f6652f2b28e208c1fa69a05346427e6d3e1b4d79dd294b79f4caf29b047a1b3",
    ),
    "persona-dedup-report": (
        "aca23c38b3ae8b0444d9b3cc6c44a47936b132e4a2706f2dbdf4237a93ecc177",
        "ffa3038a0771cd9db790d527d12c71c58d5cf6fa66622c11b5f9ab15545ccf21",
    ),
    "public-topic-sources": (
        "23a5c5657a69c1acf80cbf685ef0998e9729953fdb9ec5968460ac16a3fc5199",
        "30bdfaad7f4f953fd0345ec04257de708f1486114aed4bcbfae459e0a0d01933",
    ),
    "topic-candidate-pools": (
        "be6f66e9befd0da08346b4e8a8dbe857f61f06c1c0d3d756f12936eca2f40bc4",
        "2200974a858330d7acd38ae031046cb2e2d1451bce0427a9539cc07816575d6c",
    ),
    "topic-source-audit": (
        "1fa8df41186533a83316a0128af5abea5de9bbab3c2dc234c095befdfee30760",
        "9e29af2fc88ec8f3bc20826c5141ae2355c1003fb8f8e56169b17b15dc0d0a65",
    ),
}

EXPECTED_PLANNED_ARTIFACT_IDS = {
    "persona-adjudication-rubric",
    "persona-blinded-reviews",
    "persona-final-catalog",
    "topic-suitability-rubric",
    "topic-blinded-reviews",
    "topic-exclusion-log",
    "topic-final-36",
    "topic-25-turn-scenarios",
    "topic-split-plan",
    "topic-split-balance-diagnostics",
    "topic-static-access-policy",
    "g1-freeze-attestation",
}


def _load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_phase1_inventory_locks_exact_files_and_canonical_content() -> None:
    config = _load_config()
    assert config["implementation_status"] == "preparation"
    assert config["execution_authorized"] is False
    assert config["contains_target_model_data"] is False
    assert set(config["required_artifact_ids"]) == set(EXPECTED_ARTIFACT_HASHES)

    specifications = {item["artifact_id"]: item for item in config["artifacts"]}
    assert set(specifications) == set(EXPECTED_ARTIFACT_HASHES)
    for artifact_id, (expected_file_hash, expected_canonical_hash) in (
        EXPECTED_ARTIFACT_HASHES.items()
    ):
        specification = specifications[artifact_id]
        path = REPOSITORY_ROOT / specification["path"]
        assert specification["canonicalization_version"] == CANONICALIZATION_VERSION
        assert specification["file_sha256"] == expected_file_hash
        assert specification["canonical_sha256"] == expected_canonical_hash
        assert file_bytes_sha256(path) == expected_file_hash
        assert canonical_structured_file_sha256(path) == expected_canonical_hash


def test_phase1_inventory_is_preparation_with_only_intent_check_failing() -> None:
    report = evaluate_g1_readiness(CONFIG_PATH)
    assert report.status is ReadinessStatus.PREPARATION
    assert report.ready is False
    assert {check.code for check in report.failed_checks} == {"PREPARATION_STATUS"}

    artifact_checks = [
        check for check in report.checks if check.artifact_id is not None
    ]
    assert len(artifact_checks) == 4 * len(EXPECTED_ARTIFACT_HASHES)
    assert all(check.passed for check in artifact_checks)
    assert not {
        "ARTIFACT_MISSING",
        "FILE_SHA256_MISMATCH",
        "CANONICAL_MANIFEST_INVALID",
        "ARTIFACT_CONTENT_INCOMPLETE",
    }.intersection(check.code for check in report.checks)


def test_phase1_status_flip_alone_cannot_forge_ready(tmp_path: Path) -> None:
    config = _load_config()
    config["implementation_status"] = "ready_for_validation"
    config["artifact_root"] = str(REPOSITORY_ROOT)
    forged_path = tmp_path / "forged-ready.yaml"
    forged_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    report = evaluate_g1_readiness(forged_path)
    assert report.status is ReadinessStatus.NOT_READY
    assert report.ready is False
    assert "READINESS_CONTRACT_INCOMPLETE" in {
        check.code for check in report.failed_checks
    }


def test_planned_freeze_products_are_not_misrepresented_as_present() -> None:
    config = _load_config()
    planned = config["planned_g1_freeze_artifacts"]
    assert {item["artifact_id"] for item in planned} == EXPECTED_PLANNED_ARTIFACT_IDS
    assert not EXPECTED_PLANNED_ARTIFACT_IDS.intersection(
        config["required_artifact_ids"]
    )
    assert all(
        not (REPOSITORY_ROOT / item["planned_path"]).exists() for item in planned
    )
    assert config["readiness_statement"] == {
        "gate_passed": False,
        "phase_1_artifacts_hash_verified": True,
        "target_model_execution_authorized": False,
        "remaining_work_recorded_in": "docs/gates/G1_source_candidate_phase1.md",
    }


def test_validator_cli_reports_preparation_and_exit_two() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "validate_g1_assets.py"),
            "--config",
            str(CONFIG_PATH),
            "--compact",
        ],
        cwd=REPOSITORY_ROOT,
        env={"PYTHONPATH": str(REPOSITORY_ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["status"] == "PREPARATION"
    assert payload["ready"] is False
    assert payload["summary"] == {"checks": 31, "failed": 1, "passed": 30}
    assert [
        check["code"] for check in payload["checks"] if not check["passed"]
    ] == ["PREPARATION_STATUS"]
