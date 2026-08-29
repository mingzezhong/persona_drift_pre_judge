import json
from pathlib import Path

import pytest

from persona_drift.development_run import (
    ASSIGNMENTS_NAME,
    GRADUAL_LEVELS,
    MANIFEST_NAME,
    RUN_DIR,
    build_development_run,
    resolve_model_snapshot,
    verify_development_run,
)
from persona_drift.protocol import ProtocolValidationError


ROOT = Path(__file__).resolve().parents[1]


def _rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_tracked_complete_development_run_verifies():
    manifest = verify_development_run(ROOT)
    assert manifest["status"] == "READY_TO_QUEUE_EXPLORATORY_DEVELOPMENT"
    assert manifest["counts"] == {
        "conditions": 2,
        "development_topics": 18,
        "eligible_cells_per_condition": 216,
        "persona_traits": 24,
        "total_turns": 10800,
        "trajectories": 432,
        "turns_per_trajectory": 25,
    }
    assert manifest["calibration_outcomes_authorized"] is False
    assert manifest["untouched_test_outcomes_authorized"] is False


def test_run_builder_is_byte_identical_and_full_coverage(tmp_path):
    build_development_run(ROOT, output=tmp_path)
    tracked = ROOT / RUN_DIR
    assert (tmp_path / MANIFEST_NAME).read_bytes() == (tracked / MANIFEST_NAME).read_bytes()
    assert (tmp_path / ASSIGNMENTS_NAME).read_bytes() == (tracked / ASSIGNMENTS_NAME).read_bytes()
    rows = _rows(tmp_path / ASSIGNMENTS_NAME)
    assert len(rows) == 432
    assert len({(row["persona_trait_id"], row["topic_id"]) for row in rows}) == 216
    assert {tuple(turn["pressure_level"] for turn in row["turns"]) for row in rows} == {
        (0,) * 25,
        GRADUAL_LEVELS,
    }
    assert {row["topic_split"] for row in rows} == {"development"}


def test_tampered_assignment_fails_closed(tmp_path):
    build_development_run(ROOT, output=tmp_path)
    path = tmp_path / ASSIGNMENTS_NAME
    rows = _rows(path)
    rows[0]["topic_split"] = "untouched_test"
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")
    manifest_path = tmp_path / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text())
    import hashlib

    manifest["assignments"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ProtocolValidationError):
        verify_development_run(ROOT, run_dir=tmp_path)


def test_model_snapshot_override_must_match_locked_revision(tmp_path):
    manifest = verify_development_run(ROOT)
    revision = manifest["target_model"]["model_revision"]
    snapshot = tmp_path / revision
    snapshot.mkdir()
    assert resolve_model_snapshot(manifest, snapshot) == snapshot.resolve()

    wrong = tmp_path / "wrong-revision"
    wrong.mkdir()
    with pytest.raises(ProtocolValidationError, match="locked revision"):
        resolve_model_snapshot(manifest, wrong)
