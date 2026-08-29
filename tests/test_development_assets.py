import json
from pathlib import Path

import pytest

from persona_drift.development_assets import (
    ASSET_DIR,
    RAW_PERSONA_ROOT,
    build_development_assets,
    verify_development_assets,
)


ROOT = Path(__file__).resolve().parents[1]


def test_tracked_complete_development_assets_verify():
    index = verify_development_assets(ROOT)
    assert index["status"] == "READY_FOR_DEVELOPMENT_ONLY"
    assert index["development_execution_authorized"] is True
    assert index["confirmatory_execution_authorized"] is False
    assert index["counts"] == {
        "calibration_topics": 6,
        "development_persona_topic_cells_per_condition": 216,
        "development_topics": 18,
        "eligible_persona_topic_cells": 432,
        "persona_evaluation_items": 2304,
        "persona_families": 4,
        "persona_prompt_variants": 48,
        "persona_traits": 24,
        "qa_pilot_persona_topic_cells_per_condition": 72,
        "qa_pilot_topics": 6,
        "topic_moves": 900,
        "topics": 36,
        "untouched_test_topics": 12,
    }


def test_catalog_structure_and_access_policy():
    persona = json.loads((ROOT / ASSET_DIR / "persona_catalog_v0.json").read_text())
    topic = json.loads((ROOT / ASSET_DIR / "topic_catalog_v0.json").read_text())
    access = [json.loads(line) for line in (ROOT / ASSET_DIR / "persona_topic_access_matrix_v0.jsonl").read_text().splitlines()]
    assert [len([t for t in persona["traits"] if t["family_id"] == f["family_id"]]) for f in persona["families"]] == [6, 6, 6, 6]
    assert sum(row["topic_scope"] == "shared_core" for row in topic["topics"]) == 12
    assert sum(row["topic_scope"] == "family_specific" for row in topic["topics"]) == 24
    assert all(
        row["topic_scope"] == "shared_core" or row["topic_group_id"] == row["family_id"]
        for row in access
    )


def test_locked_raw_rebuild_is_byte_identical_when_sources_are_present(tmp_path):
    raw_root = ROOT / RAW_PERSONA_ROOT
    if not raw_root.is_dir():
        pytest.skip("ignored locked raw source checkout is not present")
    output = tmp_path / "development"
    build_development_assets(ROOT, output=output, raw_persona_root=raw_root)
    tracked = ROOT / ASSET_DIR
    for path in tracked.iterdir():
        if path.is_file() and path.name != "README.md":
            assert (output / path.name).read_bytes() == path.read_bytes()
