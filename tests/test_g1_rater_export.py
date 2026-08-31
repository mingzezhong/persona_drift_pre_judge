from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from persona_drift.g1_manifest import canonical_json_bytes
from persona_drift.g1_rater_export import (
    ALLOWED_EXPORT_ASSETS,
    ATTESTATION_FILENAME,
    MANIFEST_FILENAME,
    ExportAsset,
    RaterExportError,
    build_attestation,
    build_manifest,
    build_rater_facing_export,
    canonical_sha256,
    validate_boundary_hashes,
    validate_packet_manifest_bindings,
)


ROOT = Path(__file__).resolve().parents[1]


def test_export_is_sorted_hash_bound_and_data_only(tmp_path: Path) -> None:
    output = tmp_path / "rater-export"
    manifest, attestation = build_rater_facing_export(ROOT, output)
    paths = [entry["path"] for entry in manifest["files"]]
    assert paths == sorted(paths)
    assert paths == sorted(asset.path for asset in ALLOWED_EXPORT_ASSETS)
    for entry in manifest["files"]:
        exported = output / entry["path"]
        assert exported.is_file()
        assert hashlib.sha256(exported.read_bytes()).hexdigest() == entry["sha256"]
    assert (output / MANIFEST_FILENAME).read_bytes() == canonical_json_bytes(manifest)
    assert (output / ATTESTATION_FILENAME).read_bytes() == canonical_json_bytes(attestation)
    assert manifest["contains_ratings"] is False
    assert manifest["contains_target_model_data"] is False


def test_attestation_is_messages_only_offline_and_has_no_tools() -> None:
    attestation = build_attestation()
    assert attestation["backend"] == "local_transformers"
    assert attestation["model_receives_only"] == ["messages"]
    assert attestation["model_access"] == {
        "repository_filesystem": False,
        "web_or_network": False,
        "tools": False,
    }
    assert attestation["offline_environment"] == {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    assert attestation["ratings_generated_by_attestation"] is False


def test_extra_or_forbidden_asset_fails_closed() -> None:
    forbidden = ExportAsset(
        "data/reviews/topic_mmlu_triage_admin_map_v2_3.jsonl",
        "anonymous_review_packet",
    )
    with pytest.raises(RaterExportError, match="exact allowlist"):
        build_manifest(ROOT, assets=(*ALLOWED_EXPORT_ASSETS, forbidden))


def test_missing_allowlisted_asset_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    with pytest.raises(RaterExportError, match="unavailable"):
        build_manifest(root)


def test_symlinked_allowlisted_asset_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "project"
    for asset in ALLOWED_EXPORT_ASSETS:
        path = root / asset.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"safe")
    target = root / ALLOWED_EXPORT_ASSETS[0].path
    target.unlink()
    target.symlink_to(root / ALLOWED_EXPORT_ASSETS[1].path)
    with pytest.raises(RaterExportError, match="non-symlink"):
        build_manifest(root)


def test_export_inside_repository_checkout_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RaterExportError, match="outside repository checkout"):
        build_rater_facing_export(ROOT, ROOT / "outputs/test-rater-export")


def test_real_hashes_are_bound_to_boundary_and_packet_manifests() -> None:
    config = yaml.safe_load((ROOT / "configs/g1_phase2_v2_3.yaml").read_text())
    manifest = json.loads(
        (ROOT / "data/manifests/g1_rater_facing_export_v2_3.json").read_text()
    )
    attestation = json.loads(
        (
            ROOT
            / "data/attestations/g1_review_execution_environment_v2_3.json"
        ).read_text()
    )
    boundary = config["review_execution_boundary"]
    assert manifest == build_manifest(ROOT)
    validate_boundary_hashes(boundary, manifest, attestation)
    packet_manifests = [
        yaml.safe_load(
            (ROOT / "data/manifests/persona_semantic_review_packet_manifest_v2_3.yaml").read_text()
        ),
        yaml.safe_load(
            (ROOT / "data/manifests/topic_screening_packets_v2_3.yaml").read_text()
        ),
    ]
    validate_packet_manifest_bindings(packet_manifests, boundary)
    assert config["authorization_guard"]["all_required_reviews_complete"] is False
    assert config["ratings_generated"] is False
    assert config["protocol_status"] == "preparation"


def test_wrong_boundary_or_packet_hash_fails_closed() -> None:
    manifest = build_manifest(ROOT)
    attestation = build_attestation()
    boundary = {
        "status": "frozen",
        "rater_facing_export_manifest_sha256": "0" * 64,
        "execution_environment_attestation_sha256": canonical_sha256(attestation),
    }
    with pytest.raises(RaterExportError, match="manifest hash mismatch"):
        validate_boundary_hashes(boundary, manifest, attestation)
    correct_boundary = {
        **boundary,
        "rater_facing_export_manifest_sha256": canonical_sha256(manifest),
    }
    with pytest.raises(RaterExportError, match="packet manifest"):
        validate_packet_manifest_bindings(
            [{"execution_boundary_binding": {}}], correct_boundary
        )
