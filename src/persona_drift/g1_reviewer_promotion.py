"""Fail-closed promotion of the G1 reviewer registry after synthetic smoke.

The promotion boundary consumes the smoke-only registry, the frozen seven-row
synthetic packet, and one append-only ledger for each of the five reviewer
slots.  It does not run a model or manufacture a missing result.  Only after
all five ledgers independently validate does it materialize a deterministic
evidence report and a *new* production registry.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

import yaml

from persona_drift.g1_local_reviewer import (
    LEDGER_SCHEMA_VERSION,
    NORMALIZATION_NONE,
    NORMALIZATION_STRIP_SINGLE_OUTER_FENCE,
    OUTPUT_NORMALIZATION_CONTRACT,
    PROMPTS_SCHEMA_VERSION,
    PRODUCTION_MODE,
    REGISTRY_SCHEMA_VERSION,
    REVIEW_CONTRACT_SCHEMA_VERSION,
    RUNNER_IMPLEMENTATION_RELATIVE_PATHS,
    RUNNER_IMPLEMENTATION_SCHEMA_VERSION,
    SYNTHETIC_MODE,
    _validate_instance,
    normalize_model_output,
    runner_implementation_binding,
)
from persona_drift.g1_manifest import (
    ManifestValidationError,
    canonical_json_bytes,
    load_structured_bytes,
)


REPORT_SCHEMA_VERSION = "restart-v2.3-g1-reviewer-synthetic-smoke-report-v1"
CONTRACT_SCHEMA_VERSION = REVIEW_CONTRACT_SCHEMA_VERSION

SMOKE_REGISTRY_PATH = Path("configs/g1_reviewer_registry_v2_3.yaml")
SYNTHETIC_PACKET_PATH = Path("data/synthetic/g1_reviewer_smoke_v2_3.jsonl")
PROMPT_CATALOG_PATH = Path("data/rater_specs/g1_local_reviewer_prompts_v2_3.yaml")
SMOKE_LEDGER_DIRECTORY = Path("outputs/g1/reviewer_smoke")
SMOKE_REPORT_PATH = Path("data/reports/g1_reviewer_synthetic_smoke_v2_3.json")
PRODUCTION_REGISTRY_PATH = Path(
    "configs/g1_reviewer_registry_production_v2_3.yaml"
)

SLOT_IDS = (
    "primary_01",
    "primary_02",
    "primary_03",
    "adjudicator_04",
    "scenario_writer",
)
EXPECTED_ROLES: Mapping[str, str] = {
    "primary_01": "independent_primary_rater",
    "primary_02": "independent_primary_rater",
    "primary_03": "independent_primary_rater",
    "adjudicator_04": "disagreement_and_shortfall_adjudicator",
    "scenario_writer": "pressure_free_topic_move_writer",
}
PRIMARY_TASKS = (
    "persona_scalar",
    "persona_pair",
    "persona_family",
    "topic_triage",
    "topic_suitability",
    "scenario_qa",
)
EXPECTED_TASKS_BY_SLOT: Mapping[str, tuple[str, ...]] = {
    "primary_01": PRIMARY_TASKS,
    "primary_02": PRIMARY_TASKS,
    "primary_03": PRIMARY_TASKS,
    "adjudicator_04": (
        "persona_scalar",
        "persona_pair",
        "persona_family",
        "topic_suitability",
    ),
    "scenario_writer": ("scenario_writer",),
}

# These IDs and tasks are the frozen smoke contract, not a discoverable set.
# Checking them prevents a caller from substituting a different all-SYN packet.
FROZEN_SMOKE_ITEM_TASKS: Mapping[str, str] = {
    "SYN-PERSONA-SCALAR-001": "persona_scalar",
    "SYN-PERSONA-PAIR-001": "persona_pair",
    "SYN-PERSONA-FAMILY-001": "persona_family",
    "SYN-TOPIC-TRIAGE-001": "topic_triage",
    "SYN-TOPIC-SUITABILITY-001": "topic_suitability",
    "SYN-SCENARIO-WRITER-001": "scenario_writer",
    "SYN-SCENARIO-QA-001": "scenario_qa",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_LEDGER_FIELDS = frozenset(
    {
        "schema_version",
        "attempt_id",
        "started_at_utc",
        "finished_at_utc",
        "mode",
        "status",
        "review_contract_sha256",
        "review_contract",
        "reviewer",
        "runtime_provenance",
        "packet",
        "item",
        "prompt",
        "decoding",
        "raw_output",
        "raw_output_sha256",
        "normalization",
        "normalized_output_sha256",
        "response",
        "response_canonical_sha256",
        "error",
        "previous_record_sha256",
        "record_sha256",
    }
)
_CONTRACT_FIELDS = frozenset(
    {
        "schema_version",
        "mode",
        "reviewer",
        "registry_file_sha256",
        "registry_canonical_sha256",
        "prompt_catalog_file_sha256",
        "prompt_catalog_canonical_sha256",
        "packet_file_sha256",
        "decoding_canonical_sha256",
        "decoding",
        "batch_size",
        "output_normalization",
        "runner_implementation",
    }
)


class ReviewerPromotionError(ValueError):
    """Raised when synthetic evidence cannot authorize production review."""


@dataclass(frozen=True)
class _SmokeItem:
    item_id: str
    task_id: str
    line_number: int
    row_sha256: str
    canonical_sha256: str
    payload: Mapping[str, Any]
    expected_schema: Mapping[str, Any]


@dataclass(frozen=True)
class _PromptTask:
    user_template: str
    packet_expected_schema: Mapping[str, Any]
    response_schema: Mapping[str, Any]
    canonical_sha256: str


@dataclass(frozen=True)
class _PromptCatalog:
    system_prompt: str
    tasks: Mapping[str, _PromptTask]
    file_sha256: str
    canonical_sha256: str


@dataclass(frozen=True)
class _LedgerEvidence:
    report: Mapping[str, Any]
    contract_common: Mapping[str, Any]


@dataclass(frozen=True)
class PromotionArtifacts:
    """Deterministic artifacts produced only after all checks pass."""

    report: Mapping[str, Any]
    report_bytes: bytes
    production_registry: Mapping[str, Any]
    production_registry_bytes: bytes


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewerPromotionError(f"{context} must be a mapping")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str] | frozenset[str], context: str
) -> None:
    missing = sorted(set(expected) - set(value))
    extra = sorted(set(value) - set(expected))
    if missing or extra:
        raise ReviewerPromotionError(
            f"{context} fields differ; missing={missing}, extra={extra}"
        )


def _require_sha256(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ReviewerPromotionError(
            f"{context} must be 64 lowercase hexadecimal characters"
        )
    return value


def _strict_json(raw: bytes, context: str) -> Mapping[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ReviewerPromotionError(f"{context} must not contain a UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReviewerPromotionError(f"{context} must be UTF-8") from exc

    def unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReviewerPromotionError(
                    f"{context} contains duplicate JSON key {key!r}"
                )
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ReviewerPromotionError(
            f"{context} contains forbidden non-finite number {value}"
        )

    try:
        value = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except ReviewerPromotionError:
        raise
    except json.JSONDecodeError as exc:
        raise ReviewerPromotionError(f"{context} is invalid JSON: {exc}") from exc
    return _require_mapping(value, context)


def _strict_jsonl(
    raw: bytes, context: str, *, require_canonical: bool = True
) -> tuple[tuple[bytes, Mapping[str, Any]], ...]:
    if not raw or not raw.endswith(b"\n"):
        raise ReviewerPromotionError(
            f"{context} must be non-empty JSONL ending in one LF"
        )
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise ReviewerPromotionError(f"{context} must be BOM-free LF-only UTF-8")
    rows = raw[:-1].split(b"\n")
    if any(not row for row in rows):
        raise ReviewerPromotionError(f"{context} must not contain blank lines")
    result: list[tuple[bytes, Mapping[str, Any]]] = []
    for line_number, row in enumerate(rows, start=1):
        value = _strict_json(row, f"{context} line {line_number}")
        if require_canonical and canonical_json_bytes(value) != row:
            raise ReviewerPromotionError(
                f"{context} line {line_number} is not canonical JSON"
            )
        result.append((row, value))
    return tuple(result)


def _load_registry(raw: bytes) -> Mapping[str, Any]:
    if not raw:
        raise ReviewerPromotionError("smoke registry is empty")
    try:
        value = load_structured_bytes(raw, format_name="yaml")
    except ManifestValidationError as exc:
        raise ReviewerPromotionError(f"invalid smoke registry: {exc}") from exc
    registry = _require_mapping(value, "smoke registry")
    _require_exact_keys(
        registry,
        {
            "schema_version",
            "protocol_id",
            "registry_status",
            "production_review_authorized",
            "synthetic_smoke_authorized",
            "offline_only",
            "target_model_use",
            "runtime",
            "slots",
            "independence_checks",
        },
        "smoke registry",
    )
    if registry["schema_version"] != REGISTRY_SCHEMA_VERSION:
        raise ReviewerPromotionError("smoke registry schema_version is unsupported")
    if registry["registry_status"] != "frozen_for_synthetic_smoke":
        raise ReviewerPromotionError(
            "input registry must have registry_status=frozen_for_synthetic_smoke"
        )
    if registry["production_review_authorized"] is not False:
        raise ReviewerPromotionError(
            "input registry must have production_review_authorized=false"
        )
    if registry["synthetic_smoke_authorized"] is not True:
        raise ReviewerPromotionError("input registry must authorize synthetic smoke")
    if registry["offline_only"] is not True or registry["target_model_use"] != "forbidden":
        raise ReviewerPromotionError(
            "input registry must be offline-only and forbid target-model use"
        )
    if not isinstance(registry["protocol_id"], str) or not registry["protocol_id"]:
        raise ReviewerPromotionError("smoke registry protocol_id must be non-empty")

    runtime = _require_mapping(registry["runtime"], "smoke registry runtime")
    if (
        runtime.get("framework") != "transformers"
        or runtime.get("local_files_only") is not True
        or runtime.get("trust_remote_code") is not False
    ):
        raise ReviewerPromotionError("smoke registry runtime is not offline-frozen")
    decoding = _require_mapping(runtime.get("decoding"), "registry decoding")
    if (
        decoding.get("do_sample") is not False
        or decoding.get("temperature") != 0.0
        or decoding.get("top_p") != 1.0
        or not isinstance(decoding.get("max_new_tokens"), int)
    ):
        raise ReviewerPromotionError("smoke registry decoding is not frozen greedy decoding")

    slots = _require_mapping(registry["slots"], "smoke registry slots")
    if set(slots) != set(SLOT_IDS):
        raise ReviewerPromotionError(
            f"smoke registry must contain exactly the five slots {list(SLOT_IDS)}"
        )
    model_ids: set[str] = set()
    families: set[str] = set()
    for slot_id in SLOT_IDS:
        slot = _require_mapping(slots[slot_id], f"registry slot {slot_id}")
        _require_exact_keys(
            slot,
            {
                "role",
                "model_id",
                "model_revision",
                "base_model_family",
                "local_snapshot",
                "license_spdx",
                "license_evidence_url",
            },
            f"registry slot {slot_id}",
        )
        if slot["role"] != EXPECTED_ROLES[slot_id]:
            raise ReviewerPromotionError(f"registry slot {slot_id} has the wrong role")
        for field in ("model_id", "base_model_family", "local_snapshot"):
            if not isinstance(slot[field], str) or not slot[field]:
                raise ReviewerPromotionError(
                    f"registry slot {slot_id}.{field} must be non-empty text"
                )
        if not isinstance(slot["model_revision"], str) or not _REVISION_RE.fullmatch(
            slot["model_revision"]
        ):
            raise ReviewerPromotionError(
                f"registry slot {slot_id}.model_revision is not a full revision"
            )
        if Path(slot["local_snapshot"]).name != slot["model_revision"]:
            raise ReviewerPromotionError(
                f"registry slot {slot_id} snapshot is not revision-bound"
            )
        model_ids.add(slot["model_id"])
        families.add(slot["base_model_family"])
    if len(model_ids) != len(SLOT_IDS) or len(families) != len(SLOT_IDS):
        raise ReviewerPromotionError(
            "reviewer model IDs and base-model families must be pairwise distinct"
        )
    checks = _require_mapping(
        registry["independence_checks"], "registry independence_checks"
    )
    if not checks or any(value is not True for value in checks.values()):
        raise ReviewerPromotionError("all frozen independence checks must be true")
    return registry


def _load_smoke_packet(raw: bytes) -> Mapping[str, _SmokeItem]:
    result: dict[str, _SmokeItem] = {}
    for line_number, (row_raw, row) in enumerate(
        _strict_jsonl(raw, "synthetic smoke packet", require_canonical=False),
        start=1,
    ):
        _require_exact_keys(
            row, {"input_id", "task", "payload", "expected_schema"},
            f"synthetic smoke packet line {line_number}",
        )
        item_id = row["input_id"]
        task_id = row["task"]
        if not isinstance(item_id, str) or not item_id.startswith("SYN-"):
            raise ReviewerPromotionError(
                f"synthetic smoke packet line {line_number} has a production ID"
            )
        if not isinstance(task_id, str):
            raise ReviewerPromotionError(
                f"synthetic smoke packet line {line_number} task must be text"
            )
        if item_id in result:
            raise ReviewerPromotionError(
                f"synthetic smoke packet repeats item ID {item_id}"
            )
        result[item_id] = _SmokeItem(
            item_id=item_id,
            task_id=task_id,
            line_number=line_number,
            row_sha256=_sha256(row_raw),
            canonical_sha256=_sha256(canonical_json_bytes(row)),
            payload=_require_mapping(
                row["payload"], f"synthetic smoke packet line {line_number} payload"
            ),
            expected_schema=_require_mapping(
                row["expected_schema"],
                f"synthetic smoke packet line {line_number} expected_schema",
            ),
        )
    observed = {item_id: item.task_id for item_id, item in result.items()}
    if observed != dict(FROZEN_SMOKE_ITEM_TASKS):
        raise ReviewerPromotionError(
            "synthetic smoke packet does not contain the exact frozen seven items/tasks"
        )
    return result


def _load_prompt_catalog(raw: bytes) -> _PromptCatalog:
    if not raw:
        raise ReviewerPromotionError("prompt catalog is empty")
    try:
        value = load_structured_bytes(raw, format_name="yaml")
    except ManifestValidationError as exc:
        raise ReviewerPromotionError(f"invalid prompt catalog: {exc}") from exc
    catalog = _require_mapping(value, "prompt catalog")
    _require_exact_keys(
        catalog, {"schema_version", "system_prompt", "tasks"}, "prompt catalog"
    )
    if catalog["schema_version"] != PROMPTS_SCHEMA_VERSION:
        raise ReviewerPromotionError("prompt catalog schema_version is unsupported")
    system_prompt = catalog["system_prompt"]
    if not isinstance(system_prompt, str) or not system_prompt:
        raise ReviewerPromotionError("prompt catalog system_prompt must be non-empty")
    raw_tasks = _require_mapping(catalog["tasks"], "prompt catalog tasks")
    if set(raw_tasks) != set(FROZEN_SMOKE_ITEM_TASKS.values()):
        raise ReviewerPromotionError(
            "prompt catalog must contain exactly the seven frozen smoke tasks"
        )
    tasks: dict[str, _PromptTask] = {}
    for task_id, raw_task in raw_tasks.items():
        task = _require_mapping(raw_task, f"prompt task {task_id}")
        _require_exact_keys(
            task,
            {"user_template", "packet_expected_schema", "response_schema"},
            f"prompt task {task_id}",
        )
        template = task["user_template"]
        if (
            not isinstance(template, str)
            or template.count("{input_json}") != 1
            or template.count("{response_schema_json}") != 1
        ):
            raise ReviewerPromotionError(
                f"prompt task {task_id} template placeholders are not exact"
            )
        tasks[task_id] = _PromptTask(
            user_template=template,
            packet_expected_schema=_require_mapping(
                task["packet_expected_schema"],
                f"prompt task {task_id} packet_expected_schema",
            ),
            response_schema=_require_mapping(
                task["response_schema"], f"prompt task {task_id} response_schema"
            ),
            canonical_sha256=_sha256(canonical_json_bytes(task)),
        )
    return _PromptCatalog(
        system_prompt=system_prompt,
        tasks=tasks,
        file_sha256=_sha256(raw),
        canonical_sha256=_sha256(canonical_json_bytes(catalog)),
    )


def _expected_items(
    slot_id: str, smoke_items: Mapping[str, _SmokeItem]
) -> tuple[_SmokeItem, ...]:
    tasks = EXPECTED_TASKS_BY_SLOT[slot_id]
    selected = tuple(
        smoke_items[item_id]
        for item_id in FROZEN_SMOKE_ITEM_TASKS
        if smoke_items[item_id].task_id in tasks
    )
    if tuple(item.task_id for item in selected) != tasks:
        raise ReviewerPromotionError(
            f"internal expected smoke task order differs for slot {slot_id}"
        )
    return selected


def _validate_response_ids(item: _SmokeItem, response: Mapping[str, Any]) -> None:
    payload = item.payload
    if item.task_id == "persona_scalar":
        expected = {"candidate_anonymous_id": payload.get("candidate_anonymous_id")}
    elif item.task_id == "persona_pair":
        candidate_a = _require_mapping(payload.get("candidate_a"), "candidate_a")
        candidate_b = _require_mapping(payload.get("candidate_b"), "candidate_b")
        expected = {
            "candidate_a_id": candidate_a.get("id"),
            "candidate_b_id": candidate_b.get("id"),
        }
    elif item.task_id == "persona_family":
        expected = {"candidate_id": payload.get("candidate_id")}
    else:
        expected = {"blind_item_id": payload.get("blind_item_id")}
    for field, expected_id in expected.items():
        if not isinstance(expected_id, str) or not expected_id.startswith("SYN-"):
            raise ReviewerPromotionError(
                f"frozen packet {item.item_id} has a non-synthetic response ID"
            )
        if response.get(field) != expected_id:
            raise ReviewerPromotionError(
                f"accepted response for {item.item_id} has a production or mismatched {field}"
            )
    if item.task_id == "persona_family" and response.get("family_id") not in payload.get(
        "family_options", []
    ):
        raise ReviewerPromotionError(
            f"accepted response for {item.item_id} has an unknown family_id"
        )
    if item.task_id == "scenario_writer":
        moves = response.get("moves")
        if not isinstance(moves, list) or [
            move.get("move_index") if isinstance(move, Mapping) else None
            for move in moves
        ] != list(range(1, 26)):
            raise ReviewerPromotionError(
                f"accepted response for {item.item_id} lacks exact moves 1 through 25"
            )


def _expected_messages(
    item: _SmokeItem, prompt_catalog: _PromptCatalog
) -> list[Mapping[str, str]]:
    task = prompt_catalog.tasks[item.task_id]
    user = task.user_template.replace(
        "{input_json}", canonical_json_bytes(item.payload).decode("utf-8")
    ).replace(
        "{response_schema_json}",
        canonical_json_bytes(task.response_schema).decode("utf-8"),
    )
    return [
        {"role": "system", "content": prompt_catalog.system_prompt},
        {"role": "user", "content": user},
    ]


def _validate_runtime_provenance(
    value: Any,
    *,
    slot_id: str,
    registry_slot: Mapping[str, Any],
    registry_runtime: Mapping[str, Any],
) -> None:
    provenance = _require_mapping(value, f"{slot_id} runtime_provenance")
    required = {
        "snapshot_path",
        "snapshot_revision",
        "core_file_sha256s",
        "core_manifest_sha256",
        "python_version",
        "torch_version",
        "transformers_version",
        "cuda_version",
        "cuda_available",
        "cuda_device_count",
        "cuda_device_names",
        "hostname",
        "offline_environment",
    }
    _require_exact_keys(provenance, required, f"{slot_id} runtime_provenance")
    if provenance["snapshot_path"] != str(Path(registry_slot["local_snapshot"]).resolve()):
        raise ReviewerPromotionError(f"{slot_id} runtime snapshot path differs from registry")
    if provenance["snapshot_revision"] != registry_slot["model_revision"]:
        raise ReviewerPromotionError(f"{slot_id} runtime snapshot revision differs from registry")
    core_hashes = _require_mapping(
        provenance["core_file_sha256s"], f"{slot_id} runtime core_file_sha256s"
    )
    if "config.json" not in core_hashes:
        raise ReviewerPromotionError(f"{slot_id} runtime snapshot lacks config.json evidence")
    for name, digest in core_hashes.items():
        if not isinstance(name, str) or not name:
            raise ReviewerPromotionError(f"{slot_id} runtime core filename is invalid")
        _require_sha256(digest, f"{slot_id} runtime core hash {name}")
    if provenance["core_manifest_sha256"] != _sha256(canonical_json_bytes(core_hashes)):
        raise ReviewerPromotionError(f"{slot_id} runtime core manifest hash mismatch")
    if provenance["transformers_version"] != registry_runtime.get("framework_version"):
        raise ReviewerPromotionError(
            f"{slot_id} runtime transformers version differs from registry"
        )
    if provenance["torch_version"] != registry_runtime.get("torch_version"):
        raise ReviewerPromotionError(f"{slot_id} runtime torch version differs from registry")
    for field in ("python_version", "cuda_version", "hostname"):
        if not isinstance(provenance[field], str) or not provenance[field]:
            raise ReviewerPromotionError(f"{slot_id} runtime {field} must be non-empty")
    device_count = provenance["cuda_device_count"]
    device_names = provenance["cuda_device_names"]
    if (
        provenance["cuda_available"] is not True
        or isinstance(device_count, bool)
        or not isinstance(device_count, int)
        or device_count < 1
        or not isinstance(device_names, list)
        or len(device_names) != device_count
        or any(not isinstance(name, str) or not name for name in device_names)
    ):
        raise ReviewerPromotionError(f"{slot_id} runtime has no real CUDA smoke evidence")
    offline = _require_mapping(
        provenance["offline_environment"], f"{slot_id} offline_environment"
    )
    if dict(offline) != {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }:
        raise ReviewerPromotionError(f"{slot_id} runtime was not provably offline")


def _validate_contract(
    contract: Mapping[str, Any],
    *,
    contract_sha256: str,
    registry: Mapping[str, Any],
    registry_file_sha256: str,
    registry_canonical_sha256: str,
    packet_file_sha256: str,
    slot_id: str,
    prompt_catalog: _PromptCatalog,
) -> Mapping[str, Any]:
    _require_exact_keys(contract, _CONTRACT_FIELDS, f"{slot_id} review contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise ReviewerPromotionError(f"{slot_id} contract schema_version is wrong")
    if contract.get("mode") != SYNTHETIC_MODE:
        raise ReviewerPromotionError(f"{slot_id} contract is not synthetic smoke")
    if _sha256(canonical_json_bytes(contract)) != contract_sha256:
        raise ReviewerPromotionError(f"{slot_id} review contract hash mismatch")
    if contract.get("registry_file_sha256") != registry_file_sha256:
        raise ReviewerPromotionError(f"{slot_id} contract uses a different registry file")
    if contract.get("registry_canonical_sha256") != registry_canonical_sha256:
        raise ReviewerPromotionError(
            f"{slot_id} contract uses a different registry contract"
        )
    if contract.get("packet_file_sha256") != packet_file_sha256:
        raise ReviewerPromotionError(f"{slot_id} contract uses a different smoke packet")
    if (
        contract.get("prompt_catalog_file_sha256") != prompt_catalog.file_sha256
        or contract.get("prompt_catalog_canonical_sha256")
        != prompt_catalog.canonical_sha256
    ):
        raise ReviewerPromotionError(
            f"{slot_id} contract uses a different prompt catalog"
        )

    slot = _require_mapping(registry["slots"], "registry slots")[slot_id]
    reviewer = _require_mapping(contract.get("reviewer"), f"{slot_id} contract reviewer")
    expected_reviewer = {
        "reviewer_slot_id": slot_id,
        "reviewer_role": slot["role"],
        "model_id": slot["model_id"],
        "model_revision": slot["model_revision"],
        "base_model_family": slot["base_model_family"],
    }
    if dict(reviewer) != expected_reviewer:
        raise ReviewerPromotionError(
            f"{slot_id} contract model ID/revision/role differs from registry"
        )
    decoding = _require_mapping(contract.get("decoding"), f"{slot_id} contract decoding")
    registry_decoding = _require_mapping(
        _require_mapping(registry["runtime"], "registry runtime")["decoding"],
        "registry decoding",
    )
    if dict(decoding) != dict(registry_decoding):
        raise ReviewerPromotionError(f"{slot_id} contract decoding differs from registry")
    if contract.get("decoding_canonical_sha256") != _sha256(
        canonical_json_bytes(decoding)
    ):
        raise ReviewerPromotionError(f"{slot_id} decoding contract hash mismatch")
    if contract.get("batch_size") != 1:
        raise ReviewerPromotionError(f"{slot_id} smoke contract batch_size must equal 1")
    if contract.get("output_normalization") != OUTPUT_NORMALIZATION_CONTRACT:
        raise ReviewerPromotionError(
            f"{slot_id} contract output-normalization policy differs from frozen policy"
        )
    implementation = _require_mapping(
        contract.get("runner_implementation"),
        f"{slot_id} contract runner_implementation",
    )
    _require_exact_keys(
        implementation,
        {"schema_version", "file_sha256s", "canonical_sha256"},
        f"{slot_id} contract runner_implementation",
    )
    if implementation["schema_version"] != RUNNER_IMPLEMENTATION_SCHEMA_VERSION:
        raise ReviewerPromotionError(
            f"{slot_id} runner implementation schema_version is wrong"
        )
    implementation_hashes = _require_mapping(
        implementation["file_sha256s"],
        f"{slot_id} contract runner_implementation.file_sha256s",
    )
    if set(implementation_hashes) != set(RUNNER_IMPLEMENTATION_RELATIVE_PATHS):
        raise ReviewerPromotionError(
            f"{slot_id} runner implementation does not bind exactly the frozen files"
        )
    for relative_path, file_hash in implementation_hashes.items():
        _require_sha256(
            file_hash,
            f"{slot_id} runner implementation hash for {relative_path}",
        )
    implementation_root = _require_sha256(
        implementation["canonical_sha256"],
        f"{slot_id} runner implementation canonical hash",
    )
    if implementation_root != _sha256(canonical_json_bytes(implementation_hashes)):
        raise ReviewerPromotionError(
            f"{slot_id} runner implementation canonical hash mismatch"
        )
    if dict(implementation) != runner_implementation_binding():
        raise ReviewerPromotionError(
            f"{slot_id} runner implementation differs from current exact bytes"
        )
    for field in (
        "prompt_catalog_file_sha256",
        "prompt_catalog_canonical_sha256",
        "decoding_canonical_sha256",
    ):
        _require_sha256(contract.get(field), f"{slot_id} contract {field}")
    common = dict(contract)
    del common["reviewer"]
    return common


def _validate_record_payload_hashes(
    record: Mapping[str, Any], slot_id: str, line_number: int
) -> None:
    context = f"{slot_id} ledger line {line_number}"
    raw_output = record["raw_output"]
    raw_hash = record["raw_output_sha256"]
    normalization = record["normalization"]
    normalized_hash = record["normalized_output_sha256"]
    response = record["response"]
    response_hash = record["response_canonical_sha256"]
    if raw_output is None:
        if raw_hash is not None:
            raise ReviewerPromotionError(f"{context} has a hash for null raw_output")
    elif not isinstance(raw_output, str) or raw_hash != _sha256(raw_output.encode("utf-8")):
        raise ReviewerPromotionError(f"{context} raw_output hash mismatch")
    if raw_output is None:
        if normalization is not None or normalized_hash is not None:
            raise ReviewerPromotionError(
                f"{context} has normalization evidence for null raw_output"
            )
    else:
        try:
            normalized = normalize_model_output(raw_output)
        except ValueError:
            normalized = None
        if normalized is None:
            if normalization is not None or normalized_hash is not None:
                raise ReviewerPromotionError(
                    f"{context} unsupported output form has normalization evidence"
                )
        elif (
            normalization
            not in {NORMALIZATION_NONE, NORMALIZATION_STRIP_SINGLE_OUTER_FENCE}
            or normalization != normalized.normalization
            or normalized_hash != normalized.sha256
        ):
            raise ReviewerPromotionError(f"{context} normalization evidence mismatch")
    if response is None:
        if response_hash is not None:
            raise ReviewerPromotionError(f"{context} has a hash for null response")
    else:
        response = _require_mapping(response, f"{context} response")
        if response_hash != _sha256(canonical_json_bytes(response)):
            raise ReviewerPromotionError(f"{context} response hash mismatch")

    status = record["status"]
    error = record["error"]
    if status == "accepted":
        if raw_output is None or response is None or error is not None:
            raise ReviewerPromotionError(f"{context} accepted payload is incomplete")
        if normalization is None or normalized_hash is None:
            raise ReviewerPromotionError(
                f"{context} accepted payload lacks normalization evidence"
            )
    elif status == "rejected_invalid_output":
        if raw_output is None or response is not None or not isinstance(error, str):
            raise ReviewerPromotionError(f"{context} rejected payload is inconsistent")
    elif status == "generation_error":
        if raw_output is not None or response is not None or not isinstance(error, str):
            raise ReviewerPromotionError(f"{context} generation error is inconsistent")
    else:
        raise ReviewerPromotionError(f"{context} has unsupported status {status!r}")


def _validate_ledger(
    raw: bytes,
    *,
    path_label: str,
    slot_id: str,
    registry: Mapping[str, Any],
    registry_file_sha256: str,
    registry_canonical_sha256: str,
    packet_file_sha256: str,
    smoke_items: Mapping[str, _SmokeItem],
    prompt_catalog: _PromptCatalog,
) -> _LedgerEvidence:
    rows = _strict_jsonl(raw, f"{slot_id} smoke ledger")
    expected_items = _expected_items(slot_id, smoke_items)
    expected_by_id = {item.item_id: item for item in expected_items}
    accepted: dict[str, Mapping[str, Any]] = {}
    prior_hash: str | None = None
    chain_head: str | None = None
    contract_hash: str | None = None
    contract_value: Mapping[str, Any] | None = None
    contract_common: Mapping[str, Any] | None = None
    attempt_ids: set[str] = set()

    registry_slot = _require_mapping(registry["slots"], "registry slots")[slot_id]
    expected_reviewer = {
        "reviewer_slot_id": slot_id,
        "model_id": registry_slot["model_id"],
        "model_revision": registry_slot["model_revision"],
        "base_model_family": registry_slot["base_model_family"],
        "reviewer_role": registry_slot["role"],
        "model_snapshot_path": str(Path(registry_slot["local_snapshot"]).resolve()),
    }

    for line_number, (_, record) in enumerate(rows, start=1):
        context = f"{slot_id} ledger line {line_number}"
        _require_exact_keys(record, _LEDGER_FIELDS, context)
        if record["schema_version"] != LEDGER_SCHEMA_VERSION:
            raise ReviewerPromotionError(f"{context} has the wrong schema_version")
        observed_hash = _require_sha256(record["record_sha256"], f"{context} record hash")
        body = dict(record)
        del body["record_sha256"]
        if observed_hash != _sha256(canonical_json_bytes(body)):
            raise ReviewerPromotionError(f"{context} record hash mismatch")
        if record["previous_record_sha256"] != prior_hash:
            raise ReviewerPromotionError(f"{context} hash chain mismatch")
        prior_hash = observed_hash
        chain_head = observed_hash

        if record["mode"] != SYNTHETIC_MODE or record["mode"] == PRODUCTION_MODE:
            raise ReviewerPromotionError(f"{context} is not synthetic smoke")
        attempt_id = record["attempt_id"]
        if not isinstance(attempt_id, str) or not attempt_id or attempt_id in attempt_ids:
            raise ReviewerPromotionError(f"{context} has an invalid or duplicate attempt ID")
        attempt_ids.add(attempt_id)
        if dict(_require_mapping(record["reviewer"], f"{context} reviewer")) != expected_reviewer:
            raise ReviewerPromotionError(
                f"{context} model ID/revision/slot differs from smoke registry"
            )

        item_map = _require_mapping(record["item"], f"{context} item")
        _require_exact_keys(
            item_map,
            {"item_id", "id_field", "task_id", "line_number", "row_sha256", "canonical_sha256"},
            f"{context} item",
        )
        item_id = item_map["item_id"]
        if not isinstance(item_id, str) or not item_id.startswith("SYN-"):
            raise ReviewerPromotionError(f"{context} contains a production item ID")
        if item_id not in expected_by_id:
            raise ReviewerPromotionError(
                f"{context} item is outside the exact expected synthetic tasks"
            )
        expected_item = expected_by_id[item_id]
        expected_item_map = {
            "item_id": expected_item.item_id,
            "id_field": "input_id",
            "task_id": expected_item.task_id,
            "line_number": expected_item.line_number,
            "row_sha256": expected_item.row_sha256,
            "canonical_sha256": expected_item.canonical_sha256,
        }
        if dict(item_map) != expected_item_map:
            raise ReviewerPromotionError(
                f"{context} item provenance differs from frozen smoke packet"
            )
        prompt_task = prompt_catalog.tasks[expected_item.task_id]
        if dict(expected_item.expected_schema) != dict(
            prompt_task.packet_expected_schema
        ):
            raise ReviewerPromotionError(
                f"{context} packet expected_schema differs from prompt catalog"
            )

        current_contract_hash = _require_sha256(
            record["review_contract_sha256"], f"{context} contract hash"
        )
        current_contract = _require_mapping(
            record["review_contract"], f"{context} review_contract"
        )
        current_common = _validate_contract(
            current_contract,
            contract_sha256=current_contract_hash,
            registry=registry,
            registry_file_sha256=registry_file_sha256,
            registry_canonical_sha256=registry_canonical_sha256,
            packet_file_sha256=packet_file_sha256,
            slot_id=slot_id,
            prompt_catalog=prompt_catalog,
        )
        if contract_hash is None:
            contract_hash = current_contract_hash
            contract_value = current_contract
            contract_common = current_common
        elif current_contract_hash != contract_hash or dict(current_contract) != dict(contract_value):
            raise ReviewerPromotionError(f"{slot_id} ledger mixes review contracts")

        packet = _require_mapping(record["packet"], f"{context} packet")
        _require_exact_keys(packet, {"path", "file_sha256"}, f"{context} packet")
        if not isinstance(packet["path"], str) or packet["file_sha256"] != packet_file_sha256:
            raise ReviewerPromotionError(f"{context} packet provenance mismatch")

        prompt = _require_mapping(record["prompt"], f"{context} prompt")
        _require_exact_keys(
            prompt,
            {
                "catalog_file_sha256",
                "catalog_canonical_sha256",
                "task_canonical_sha256",
                "messages",
                "messages_canonical_sha256",
            },
            f"{context} prompt",
        )
        if (
            prompt["catalog_file_sha256"] != current_contract["prompt_catalog_file_sha256"]
            or prompt["catalog_canonical_sha256"]
            != current_contract["prompt_catalog_canonical_sha256"]
        ):
            raise ReviewerPromotionError(f"{context} prompt catalog differs from contract")
        if prompt["task_canonical_sha256"] != prompt_task.canonical_sha256:
            raise ReviewerPromotionError(f"{context} task prompt hash mismatch")
        messages = prompt["messages"]
        if not isinstance(messages, list) or prompt["messages_canonical_sha256"] != _sha256(
            canonical_json_bytes(messages)
        ):
            raise ReviewerPromotionError(f"{context} prompt messages hash mismatch")
        if messages != _expected_messages(expected_item, prompt_catalog):
            raise ReviewerPromotionError(
                f"{context} prompt messages differ from frozen task and input"
            )

        decoding = _require_mapping(record["decoding"], f"{context} decoding")
        if dict(decoding) != {
            "parameters": dict(current_contract["decoding"]),
            "batch_size": current_contract["batch_size"],
            "canonical_sha256": current_contract["decoding_canonical_sha256"],
        }:
            raise ReviewerPromotionError(f"{context} decoding differs from contract")
        _validate_runtime_provenance(
            record["runtime_provenance"],
            slot_id=slot_id,
            registry_slot=registry_slot,
            registry_runtime=_require_mapping(registry["runtime"], "registry runtime"),
        )
        _validate_record_payload_hashes(record, slot_id, line_number)

        if record["status"] == "accepted":
            if item_id in accepted:
                raise ReviewerPromotionError(
                    f"{slot_id} ledger contains duplicate accepted item {item_id}"
                )
            response = _require_mapping(record["response"], f"{context} accepted response")
            normalized = normalize_model_output(record["raw_output"])
            raw_response = _strict_json(
                normalized.text.encode("utf-8"),
                f"{context} accepted normalized_output",
            )
            if canonical_json_bytes(raw_response) != canonical_json_bytes(response):
                raise ReviewerPromotionError(
                    f"{context} raw_output and accepted response differ"
                )
            try:
                _validate_instance(response, prompt_task.response_schema)
            except ValueError as exc:
                raise ReviewerPromotionError(
                    f"{context} accepted response violates frozen schema: {exc}"
                ) from exc
            _validate_response_ids(expected_item, response)
            accepted[item_id] = record

    expected_ids = {item.item_id for item in expected_items}
    if set(accepted) != expected_ids:
        missing = sorted(expected_ids - set(accepted))
        extra = sorted(set(accepted) - expected_ids)
        raise ReviewerPromotionError(
            f"{slot_id} does not have every exact expected synthetic task accepted; "
            f"missing={missing}, extra={extra}"
        )
    if chain_head is None or contract_hash is None or contract_common is None:
        raise ReviewerPromotionError(f"{slot_id} smoke ledger is empty")

    accepted_items = [
        {"item_id": item.item_id, "task_id": item.task_id}
        for item in expected_items
    ]
    return _LedgerEvidence(
        report={
            "path": path_label,
            "file_sha256": _sha256(raw),
            "chain_head_sha256": chain_head,
            "record_count": len(rows),
            "accepted_record_count": len(accepted),
            "review_contract_sha256": contract_hash,
            "role": registry_slot["role"],
            "model_id": registry_slot["model_id"],
            "model_revision": registry_slot["model_revision"],
            "accepted_items": accepted_items,
        },
        contract_common=contract_common,
    )


def _yaml_bytes(value: Mapping[str, Any]) -> bytes:
    return yaml.safe_dump(
        dict(value),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100,
    ).encode("utf-8")


def build_g1_reviewer_promotion(
    *,
    registry_bytes: bytes,
    ledger_bytes_by_slot: Mapping[str, bytes],
    synthetic_packet_bytes: bytes,
    prompt_catalog_bytes: bytes,
    registry_path: str | Path = SMOKE_REGISTRY_PATH,
    ledger_paths_by_slot: Mapping[str, str | Path] | None = None,
    synthetic_packet_path: str | Path = SYNTHETIC_PACKET_PATH,
    prompt_catalog_path: str | Path = PROMPT_CATALOG_PATH,
    production_registry_path: str | Path = PRODUCTION_REGISTRY_PATH,
) -> PromotionArtifacts:
    """Validate all smoke evidence and return in-memory promotion artifacts."""

    if set(ledger_bytes_by_slot) != set(SLOT_IDS):
        missing = sorted(set(SLOT_IDS) - set(ledger_bytes_by_slot))
        extra = sorted(set(ledger_bytes_by_slot) - set(SLOT_IDS))
        raise ReviewerPromotionError(
            "promotion requires exactly five real smoke ledgers; "
            f"missing={missing}, extra={extra}"
        )
    labels = ledger_paths_by_slot or {
        slot: SMOKE_LEDGER_DIRECTORY / f"{slot}.jsonl" for slot in SLOT_IDS
    }
    if set(labels) != set(SLOT_IDS):
        raise ReviewerPromotionError("ledger path labels must cover exactly five slots")

    registry = _load_registry(registry_bytes)
    smoke_items = _load_smoke_packet(synthetic_packet_bytes)
    prompt_catalog = _load_prompt_catalog(prompt_catalog_bytes)
    for item in smoke_items.values():
        if dict(item.expected_schema) != dict(
            prompt_catalog.tasks[item.task_id].packet_expected_schema
        ):
            raise ReviewerPromotionError(
                f"synthetic smoke item {item.item_id} expected_schema differs from prompt catalog"
            )
    registry_file_sha256 = _sha256(registry_bytes)
    registry_canonical_sha256 = _sha256(canonical_json_bytes(registry))
    packet_file_sha256 = _sha256(synthetic_packet_bytes)

    evidence: dict[str, Mapping[str, Any]] = {}
    common_contract: Mapping[str, Any] | None = None
    for slot_id in SLOT_IDS:
        raw = ledger_bytes_by_slot[slot_id]
        if not isinstance(raw, bytes) or not raw:
            raise ReviewerPromotionError(
                f"{slot_id} smoke ledger is missing or has no real records"
            )
        validated = _validate_ledger(
            raw,
            path_label=str(labels[slot_id]),
            slot_id=slot_id,
            registry=registry,
            registry_file_sha256=registry_file_sha256,
            registry_canonical_sha256=registry_canonical_sha256,
            packet_file_sha256=packet_file_sha256,
            smoke_items=smoke_items,
            prompt_catalog=prompt_catalog,
        )
        if common_contract is None:
            common_contract = validated.contract_common
        elif dict(validated.contract_common) != dict(common_contract):
            raise ReviewerPromotionError(
                f"{slot_id} smoke contract differs from the other reviewer slots"
            )
        evidence[slot_id] = validated.report

    production_registry = dict(registry)
    production_registry["registry_status"] = "frozen_for_production"
    production_registry["production_review_authorized"] = True
    if common_contract is None:  # pragma: no cover - SLOT_IDS is frozen non-empty
        raise ReviewerPromotionError("promotion has no validated review contract")
    production_registry["runner_implementation"] = dict(
        _require_mapping(
            common_contract["runner_implementation"],
            "validated runner implementation",
        )
    )
    production_registry_bytes = _yaml_bytes(production_registry)
    reparsed = _load_production_registry(production_registry_bytes)
    if dict(reparsed) != production_registry:
        raise ReviewerPromotionError("production registry did not round-trip exactly")

    report: Mapping[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": "PASS",
        "production_promotion_eligible": True,
        "source_registry": {
            "path": str(registry_path),
            "file_sha256": registry_file_sha256,
            "canonical_sha256": registry_canonical_sha256,
            "registry_status": "frozen_for_synthetic_smoke",
            "production_review_authorized": False,
        },
        "synthetic_packet": {
            "path": str(synthetic_packet_path),
            "file_sha256": packet_file_sha256,
            "item_count": len(smoke_items),
            "all_item_ids_synthetic": True,
        },
        "prompt_catalog": {
            "path": str(prompt_catalog_path),
            "file_sha256": prompt_catalog.file_sha256,
            "canonical_sha256": prompt_catalog.canonical_sha256,
            "task_count": len(prompt_catalog.tasks),
        },
        "validation": {
            "required_slot_count": len(SLOT_IDS),
            "validated_slot_count": len(evidence),
            "all_hash_chains_valid": True,
            "all_expected_tasks_accepted": True,
            "all_records_synthetic_only": True,
            "models_and_contracts_match_registry": True,
        },
        "slots": evidence,
        "production_registry": {
            "path": str(production_registry_path),
            "file_sha256": _sha256(production_registry_bytes),
            "canonical_sha256": _sha256(canonical_json_bytes(production_registry)),
            "registry_status": "frozen_for_production",
            "production_review_authorized": True,
        },
    }
    report_bytes = canonical_json_bytes(report) + b"\n"
    return PromotionArtifacts(
        report=report,
        report_bytes=report_bytes,
        production_registry=production_registry,
        production_registry_bytes=production_registry_bytes,
    )


def _load_production_registry(raw: bytes) -> Mapping[str, Any]:
    try:
        value = load_structured_bytes(raw, format_name="yaml")
    except ManifestValidationError as exc:
        raise ReviewerPromotionError(f"invalid generated production registry: {exc}") from exc
    registry = _require_mapping(value, "generated production registry")
    if (
        registry.get("registry_status") != "frozen_for_production"
        or registry.get("production_review_authorized") is not True
    ):
        raise ReviewerPromotionError("generated registry is not production-frozen")
    return registry


def _read_regular_file(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ReviewerPromotionError(f"{label} is missing or not a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ReviewerPromotionError(f"cannot read {label} {path}: {exc}") from exc


def _resolved_identity(path: Path) -> Path:
    return path.resolve(strict=False)


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ReviewerPromotionError(f"output is not a replaceable regular file: {path}")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
        temporary_name = None
    except OSError as exc:
        raise ReviewerPromotionError(f"cannot write output {path}: {exc}") from exc
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


def _preflight_output(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ReviewerPromotionError(
            f"cannot prepare output directory {path.parent}: {exc}"
        ) from exc
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ReviewerPromotionError(f"output is not a replaceable regular file: {path}")


def _write_output_pair(
    report_path: Path,
    report_bytes: bytes,
    production_path: Path,
    production_bytes: bytes,
) -> None:
    prior = {
        report_path: report_path.read_bytes() if report_path.exists() else None,
        production_path: production_path.read_bytes()
        if production_path.exists()
        else None,
    }
    try:
        _write_atomic(report_path, report_bytes)
        _write_atomic(production_path, production_bytes)
    except Exception as exc:
        rollback_errors: list[str] = []
        for path, previous in prior.items():
            try:
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    _write_atomic(path, previous)
            except OSError as rollback_exc:
                rollback_errors.append(f"{path}: {rollback_exc}")
        if rollback_errors:
            raise ReviewerPromotionError(
                f"paired output commit failed ({exc}); rollback also failed: "
                + "; ".join(rollback_errors)
            ) from exc
        raise


def promote_g1_reviewer_registry(
    *,
    registry_path: Path,
    ledger_paths_by_slot: Mapping[str, Path],
    synthetic_packet_path: Path,
    prompt_catalog_path: Path,
    report_output_path: Path,
    production_registry_output_path: Path,
    write_outputs: bool = True,
) -> PromotionArtifacts:
    """Read real files, validate all five, then optionally write both outputs."""

    if set(ledger_paths_by_slot) != set(SLOT_IDS):
        missing = sorted(set(SLOT_IDS) - set(ledger_paths_by_slot))
        extra = sorted(set(ledger_paths_by_slot) - set(SLOT_IDS))
        raise ReviewerPromotionError(
            f"promotion requires exactly five ledger paths; missing={missing}, extra={extra}"
        )

    # Read every required input before constructing or touching an output path.
    registry_bytes = _read_regular_file(registry_path, "smoke registry")
    packet_bytes = _read_regular_file(synthetic_packet_path, "synthetic smoke packet")
    prompt_catalog_bytes = _read_regular_file(prompt_catalog_path, "prompt catalog")
    ledger_bytes = {
        slot: _read_regular_file(ledger_paths_by_slot[slot], f"{slot} smoke ledger")
        for slot in SLOT_IDS
    }
    artifacts = build_g1_reviewer_promotion(
        registry_bytes=registry_bytes,
        ledger_bytes_by_slot=ledger_bytes,
        synthetic_packet_bytes=packet_bytes,
        prompt_catalog_bytes=prompt_catalog_bytes,
        registry_path=registry_path,
        ledger_paths_by_slot=ledger_paths_by_slot,
        synthetic_packet_path=synthetic_packet_path,
        prompt_catalog_path=prompt_catalog_path,
        production_registry_path=production_registry_output_path,
    )
    if not write_outputs:
        return artifacts

    input_paths = {
        _resolved_identity(registry_path),
        _resolved_identity(synthetic_packet_path),
        _resolved_identity(prompt_catalog_path),
        *(_resolved_identity(path) for path in ledger_paths_by_slot.values()),
    }
    report_identity = _resolved_identity(report_output_path)
    production_identity = _resolved_identity(production_registry_output_path)
    if report_identity in input_paths or production_identity in input_paths:
        raise ReviewerPromotionError(
            "promotion outputs must not overwrite the source registry, packet, or ledgers"
        )
    if report_identity == production_identity:
        raise ReviewerPromotionError("report and production registry outputs must differ")

    # Both artifacts have already been fully serialized and validated here.
    # Preflight both destinations before the first artifact becomes visible.
    _preflight_output(report_output_path)
    _preflight_output(production_registry_output_path)
    _write_output_pair(
        report_output_path,
        artifacts.report_bytes,
        production_registry_output_path,
        artifacts.production_registry_bytes,
    )
    return artifacts


# Concise alias for callers that prefer a noun-oriented builder name.
build_promotion_artifacts = build_g1_reviewer_promotion
