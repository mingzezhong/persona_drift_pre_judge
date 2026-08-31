"""Build the hash-frozen, data-only G1 reviewer export."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import stat
from typing import Mapping, Sequence

from persona_drift.g1_manifest import canonical_json_bytes


MANIFEST_SCHEMA_VERSION = "restart-v2.3-g1-rater-facing-export-manifest-v1"
ATTESTATION_SCHEMA_VERSION = "restart-v2.3-g1-review-environment-attestation-v1"
MANIFEST_FILENAME = "rater_facing_export_manifest.json"
ATTESTATION_FILENAME = "execution_environment_attestation.json"


@dataclass(frozen=True)
class ExportAsset:
    path: str
    role: str


ALLOWED_EXPORT_ASSETS: tuple[ExportAsset, ...] = (
    ExportAsset(
        "data/rater_specs/g1_local_reviewer_prompts_v2_3.yaml",
        "frozen_prompt_rubric_and_response_schemas",
    ),
    ExportAsset(
        "data/reviews/persona_semantic_review_packet_v2_3.jsonl",
        "anonymous_review_packet",
    ),
    ExportAsset(
        "data/reviews/topic_anthropic_full_screen_input_v2_3.jsonl",
        "anonymous_review_packet",
    ),
    ExportAsset(
        "data/reviews/topic_mmlu_triage_input_v2_3.jsonl",
        "anonymous_review_packet",
    ),
    ExportAsset(
        "data/stages/persona_scalar_primary_01_input_v2_3.jsonl",
        "anonymous_review_packet",
    ),
    ExportAsset(
        "data/stages/persona_scalar_primary_02_input_v2_3.jsonl",
        "anonymous_review_packet",
    ),
    ExportAsset(
        "data/stages/persona_scalar_primary_03_input_v2_3.jsonl",
        "anonymous_review_packet",
    ),
)

FORBIDDEN_EXPORT_CLASSES = (
    "repository_checkout",
    "administrator_maps",
    "persona_exposure_maps",
    "split_or_pilot_assignment",
    "target_model_outputs_or_activations",
)


class RaterExportError(ValueError):
    """Raised when a data-only export would violate the frozen boundary."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _regular_file_bytes(root: Path, relative_path: str) -> bytes:
    path = root / relative_path
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RaterExportError(f"required export asset is unavailable: {relative_path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RaterExportError(f"export asset must be a regular non-symlink file: {relative_path}")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise RaterExportError(f"export asset escapes project root: {relative_path}") from exc
    return resolved.read_bytes()


def build_manifest(
    project_root: str | Path,
    *,
    assets: Sequence[ExportAsset] = ALLOWED_EXPORT_ASSETS,
) -> Mapping[str, object]:
    root = Path(project_root).resolve(strict=True)
    if tuple(assets) != ALLOWED_EXPORT_ASSETS:
        raise RaterExportError("export assets must equal the frozen exact allowlist")
    files = []
    for asset in sorted(assets, key=lambda item: item.path):
        raw = _regular_file_bytes(root, asset.path)
        files.append(
            {
                "path": asset.path,
                "role": asset.role,
                "sha256": _sha256(raw),
                "size_bytes": len(raw),
            }
        )
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "path_order": "ascending_unicode_codepoint_order",
        "files": files,
        "allowed_content_classes": [
            "anonymous_review_packets",
            "frozen_prompts_and_rubrics",
            "response_schemas",
        ],
        "forbidden_content_classes": list(FORBIDDEN_EXPORT_CLASSES),
        "contains_ratings": False,
        "contains_target_model_data": False,
    }


def build_attestation() -> Mapping[str, object]:
    return {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "backend": "local_transformers",
        "backend_input_contract": "messages_only",
        "model_receives_only": ["messages"],
        "model_access": {
            "repository_filesystem": False,
            "web_or_network": False,
            "tools": False,
        },
        "offline_environment": {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        "export_is_data_only": True,
        "repository_checkout_in_export": False,
        "ratings_generated_by_attestation": False,
    }


def canonical_sha256(value: Mapping[str, object]) -> str:
    return _sha256(canonical_json_bytes(value))


def validate_boundary_hashes(
    boundary: Mapping[str, object],
    manifest: Mapping[str, object],
    attestation: Mapping[str, object],
) -> None:
    if boundary.get("status") != "frozen":
        raise RaterExportError("review execution boundary is not frozen")
    if boundary.get("rater_facing_export_manifest_sha256") != canonical_sha256(
        manifest
    ):
        raise RaterExportError("review execution boundary manifest hash mismatch")
    if boundary.get("execution_environment_attestation_sha256") != canonical_sha256(
        attestation
    ):
        raise RaterExportError("review execution boundary attestation hash mismatch")
    if manifest != build_manifest_from_entries(manifest):
        raise RaterExportError("rater-facing manifest violates its exact schema")
    if attestation != build_attestation():
        raise RaterExportError("execution environment attestation differs from contract")


def build_manifest_from_entries(
    manifest: Mapping[str, object],
) -> Mapping[str, object]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise RaterExportError("rater-facing manifest files must be a list")
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "path_order": "ascending_unicode_codepoint_order",
        "files": files,
        "allowed_content_classes": [
            "anonymous_review_packets",
            "frozen_prompts_and_rubrics",
            "response_schemas",
        ],
        "forbidden_content_classes": list(FORBIDDEN_EXPORT_CLASSES),
        "contains_ratings": False,
        "contains_target_model_data": False,
    }


def validate_packet_manifest_bindings(
    packet_manifests: Sequence[Mapping[str, object]],
    boundary: Mapping[str, object],
) -> None:
    expected = {
        "rater_facing_export_manifest_sha256": boundary.get(
            "rater_facing_export_manifest_sha256"
        ),
        "execution_environment_attestation_sha256": boundary.get(
            "execution_environment_attestation_sha256"
        ),
    }
    for packet_manifest in packet_manifests:
        if packet_manifest.get("execution_boundary_binding") != expected:
            raise RaterExportError("packet manifest execution-boundary binding mismatch")


def build_rater_facing_export(
    project_root: str | Path,
    output_directory: str | Path,
    *,
    assets: Sequence[ExportAsset] = ALLOWED_EXPORT_ASSETS,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    root = Path(project_root).resolve(strict=True)
    output = Path(output_directory).resolve()
    try:
        output.relative_to(root)
    except ValueError:
        pass
    else:
        raise RaterExportError("data-only export directory must be outside repository checkout")
    if output.exists() and any(output.iterdir()):
        raise RaterExportError("export directory must not already contain files")

    manifest = build_manifest(root, assets=assets)
    attestation = build_attestation()
    output.mkdir(parents=True, exist_ok=True)
    for entry in manifest["files"]:
        relative_path = entry["path"]
        destination = output / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative_path, destination)
    (output / MANIFEST_FILENAME).write_bytes(canonical_json_bytes(manifest))
    (output / ATTESTATION_FILENAME).write_bytes(canonical_json_bytes(attestation))
    return manifest, attestation
