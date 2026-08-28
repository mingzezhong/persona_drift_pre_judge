"""Auditable, offline-only local Hugging Face runner for G1 reviews.

Synthetic smoke is the default. Production inputs require an explicit flag and
a registry that separately authorizes production. Every model attempt is kept
in an append-only, hash-chained JSONL ledger; only accepted attempts are skipped
when a run resumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
from typing import Any, Callable, Mapping, Protocol, Sequence
import uuid

from persona_drift.g1_manifest import (
    ManifestValidationError,
    canonical_json_bytes,
    load_structured_bytes,
)


LEDGER_SCHEMA_VERSION = "restart-v2.3-g1-local-review-ledger-v2"
REVIEW_CONTRACT_SCHEMA_VERSION = "restart-v2.3-g1-local-review-contract-v2"
OUTPUT_NORMALIZATION_SCHEMA_VERSION = (
    "restart-v2.3-g1-output-normalization-policy-v1"
)
NORMALIZATION_NONE = "none"
NORMALIZATION_STRIP_SINGLE_OUTER_FENCE = (
    "strip_single_outer_markdown_json_fence"
)
OUTPUT_NORMALIZATION_CONTRACT: Mapping[str, Any] = {
    "schema_version": OUTPUT_NORMALIZATION_SCHEMA_VERSION,
    "bare_json_operation": NORMALIZATION_NONE,
    "fenced_json_operation": NORMALIZATION_STRIP_SINGLE_OUTER_FENCE,
    "allowed_fence_openers": ["```json\n", "```\n"],
    "required_fence_closer": "\n```",
    "outer_whitespace": "strip",
    "normalized_payload": "one_strict_json_object",
}
PROMPTS_SCHEMA_VERSION = "restart-v2.3-g1-local-review-prompts-v1"
REGISTRY_SCHEMA_VERSION = "restart-v2.3-g1-reviewer-registry-v1"
RUNNER_IMPLEMENTATION_SCHEMA_VERSION = (
    "restart-v2.3-g1-local-review-implementation-v1"
)
SYNTHETIC_MODE = "SYNTHETIC_SMOKE"
PRODUCTION_MODE = "PRODUCTION"

RUNNER_IMPLEMENTATION_RELATIVE_PATHS = (
    "src/persona_drift/g1_local_reviewer.py",
    "scripts/run_g1_local_reviewer.py",
)

# The role-to-task boundary is intentionally code-frozen rather than inferred
# from packet contents.  Primaries perform the blinded family-membership vote;
# the adjudicator may use the same response shape only for unresolved cases.
# The scenario writer can never rate its own output.
ROLE_TASK_ASSIGNMENTS: Mapping[str, frozenset[str]] = {
    "independent_primary_rater": frozenset(
        {
            "persona_scalar",
            "persona_pair",
            "persona_family",
            "topic_triage",
            "topic_suitability",
            "scenario_qa",
        }
    ),
    "disagreement_and_shortfall_adjudicator": frozenset(
        {
            "persona_scalar",
            "persona_pair",
            "persona_family",
            "topic_suitability",
        }
    ),
    "pressure_free_topic_move_writer": frozenset({"scenario_writer"}),
}

_FULL_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ITEM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ID_FIELDS = (
    "input_id",
    "synthetic_id",
    "blind_item_id",
    "review_item_anonymous_id",
    "item_id",
)
_JSON_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}
_SCHEMA_KEYS = {
    "$schema",
    "$id",
    "title",
    "description",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "const",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
}


class ReviewRunnerError(ValueError):
    """Raised when execution would be unauditable or outside authorization."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_json(data: bytes | str, *, context: str) -> Any:
    if isinstance(data, bytes):
        if data.startswith(b"\xef\xbb\xbf"):
            raise ReviewRunnerError(f"{context} must not contain a UTF-8 BOM")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReviewRunnerError(f"{context} must be valid UTF-8") from exc
    else:
        text = data

    def unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReviewRunnerError(
                    f"{context} contains duplicate JSON key {key!r}"
                )
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ReviewRunnerError(
            f"{context} contains forbidden non-finite number {value}"
        )

    try:
        return json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except ReviewRunnerError:
        raise
    except json.JSONDecodeError as exc:
        raise ReviewRunnerError(f"{context} is not one exact JSON value: {exc}") from exc


@dataclass(frozen=True)
class NormalizedModelOutput:
    """Exact text presented to strict JSON parsing and its audit operation."""

    text: str
    normalization: str

    @property
    def sha256(self) -> str:
        return _sha256(self.text.encode("utf-8"))


def normalize_model_output(raw_output: str) -> NormalizedModelOutput:
    """Apply only the frozen bare-JSON or single-outer-fence policy."""

    if not isinstance(raw_output, str):
        raise ReviewRunnerError("model output must be text")
    stripped = raw_output.strip()
    normalization = NORMALIZATION_NONE
    normalized = stripped
    if stripped.startswith("```"):
        opener = next(
            (
                candidate
                for candidate in OUTPUT_NORMALIZATION_CONTRACT[
                    "allowed_fence_openers"
                ]
                if stripped.startswith(candidate)
            ),
            None,
        )
        closer = OUTPUT_NORMALIZATION_CONTRACT["required_fence_closer"]
        if opener is None or not stripped.endswith(closer):
            raise ReviewRunnerError(
                "model output fence must be exactly one complete outer ```json or ``` fence"
            )
        normalized = stripped[len(opener) : -len(closer)].strip()
        normalization = NORMALIZATION_STRIP_SINGLE_OUTER_FENCE
    elif stripped.endswith("```"):
        raise ReviewRunnerError(
            "model output fence must be exactly one complete outer ```json or ``` fence"
        )
    return NormalizedModelOutput(text=normalized, normalization=normalization)


def _read_regular_file(path: Path, *, label: str) -> bytes:
    try:
        if path.is_symlink():
            raise ReviewRunnerError(f"{label} must not be a symbolic link: {path}")
        if not path.is_file():
            raise ReviewRunnerError(f"{label} is not a regular file: {path}")
        return path.read_bytes()
    except ReviewRunnerError:
        raise
    except OSError as exc:
        raise ReviewRunnerError(f"cannot read {label} {path}: {exc}") from exc


def _load_yaml_or_json(path: Path, *, label: str) -> tuple[Any, bytes]:
    raw = _read_regular_file(path, label=label)
    suffix = path.suffix.lower()
    if suffix not in {".yaml", ".yml", ".json"}:
        raise ReviewRunnerError(f"{label} must be JSON or YAML")
    try:
        value = load_structured_bytes(
            raw, format_name="json" if suffix == ".json" else "yaml"
        )
    except ManifestValidationError as exc:
        raise ReviewRunnerError(f"invalid {label}: {exc}") from exc
    return value, raw


def _require_mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewRunnerError(f"{context} must be a mapping")
    return value


def _require_exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    context: str,
) -> None:
    optional = optional or set()
    missing = sorted(required - set(value))
    extras = sorted(set(value) - required - optional)
    if missing:
        raise ReviewRunnerError(f"{context} is missing fields: {missing}")
    if extras:
        raise ReviewRunnerError(f"{context} has unsupported fields: {extras}")


def runner_implementation_binding() -> dict[str, Any]:
    """Content-address the exact runner module and CLI bytes in this checkout."""

    project_root = Path(__file__).resolve().parents[2]
    file_sha256s = {
        relative_path: _sha256(
            _read_regular_file(
                project_root / relative_path,
                label=f"runner implementation file {relative_path}",
            )
        )
        for relative_path in RUNNER_IMPLEMENTATION_RELATIVE_PATHS
    }
    return {
        "schema_version": RUNNER_IMPLEMENTATION_SCHEMA_VERSION,
        "file_sha256s": file_sha256s,
        "canonical_sha256": _sha256(canonical_json_bytes(file_sha256s)),
    }


def _validate_authorized_runner_implementation(value: Any) -> Mapping[str, Any]:
    context = "reviewer registry runner_implementation"
    implementation = _require_mapping(value, context=context)
    _require_exact_keys(
        implementation,
        required={"schema_version", "file_sha256s", "canonical_sha256"},
        context=context,
    )
    if implementation["schema_version"] != RUNNER_IMPLEMENTATION_SCHEMA_VERSION:
        raise ReviewRunnerError(
            "reviewer registry runner_implementation schema_version is unsupported"
        )
    file_sha256s = _require_mapping(
        implementation["file_sha256s"], context=f"{context}.file_sha256s"
    )
    if set(file_sha256s) != set(RUNNER_IMPLEMENTATION_RELATIVE_PATHS):
        raise ReviewRunnerError(
            "reviewer registry runner_implementation must bind exactly the frozen "
            "runner files"
        )
    if any(
        not isinstance(file_hash, str) or not _SHA256_RE.fullmatch(file_hash)
        for file_hash in file_sha256s.values()
    ):
        raise ReviewRunnerError(
            "reviewer registry runner_implementation file hashes must be SHA-256"
        )
    canonical_sha256 = implementation["canonical_sha256"]
    if (
        not isinstance(canonical_sha256, str)
        or not _SHA256_RE.fullmatch(canonical_sha256)
        or canonical_sha256 != _sha256(canonical_json_bytes(file_sha256s))
    ):
        raise ReviewRunnerError(
            "reviewer registry runner_implementation canonical hash mismatch"
        )
    current = runner_implementation_binding()
    if dict(implementation) != current:
        raise ReviewRunnerError(
            "authorized runner implementation differs from current exact bytes"
        )
    return implementation


def _validate_schema_definition(schema: Any, *, path: str = "$") -> None:
    schema = _require_mapping(schema, context=f"response schema {path}")
    unsupported = sorted(set(schema) - _SCHEMA_KEYS)
    if unsupported:
        raise ReviewRunnerError(
            f"response schema {path} has unsupported keywords: {unsupported}"
        )
    schema_type = schema.get("type")
    if schema_type not in _JSON_TYPES:
        raise ReviewRunnerError(
            f"response schema {path}.type must be one supported string type"
        )
    if "enum" in schema and (
        not isinstance(schema["enum"], list) or not schema["enum"]
    ):
        raise ReviewRunnerError(f"response schema {path}.enum must be non-empty")
    if schema_type == "object":
        if schema.get("additionalProperties") is not False:
            raise ReviewRunnerError(
                f"response schema {path} object must set additionalProperties=false"
            )
        properties = schema.get("properties")
        required = schema.get("required")
        if not isinstance(properties, Mapping) or not isinstance(required, list):
            raise ReviewRunnerError(
                f"response schema {path} object requires properties and required"
            )
        if any(not isinstance(name, str) for name in required) or len(required) != len(
            set(required)
        ):
            raise ReviewRunnerError(
                f"response schema {path}.required must contain unique strings"
            )
        missing = sorted(set(required) - set(properties))
        if missing:
            raise ReviewRunnerError(
                f"response schema {path}.required names absent properties: {missing}"
            )
        for name, child in properties.items():
            if not isinstance(name, str):
                raise ReviewRunnerError(
                    f"response schema {path}.properties keys must be strings"
                )
            _validate_schema_definition(child, path=f"{path}.{name}")
    elif schema_type == "array":
        if "items" not in schema:
            raise ReviewRunnerError(f"response schema {path} array requires items")
        _validate_schema_definition(schema["items"], path=f"{path}[]")
    elif "properties" in schema or "required" in schema or "items" in schema:
        raise ReviewRunnerError(
            f"response schema {path} has container keywords for non-container type"
        )


def _json_equal(left: Any, right: Any) -> bool:
    return type(left) is type(right) and left == right


def _validate_instance(value: Any, schema: Mapping[str, Any], *, path: str = "$") -> None:
    schema_type = schema["type"]
    valid_type = {
        "object": lambda item: isinstance(item, Mapping),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float))
        and not isinstance(item, bool)
        and math.isfinite(item),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }[schema_type]
    if not valid_type(value):
        raise ReviewRunnerError(f"response {path} must have type {schema_type}")
    if "const" in schema and not _json_equal(value, schema["const"]):
        raise ReviewRunnerError(f"response {path} differs from schema const")
    if "enum" in schema and not any(_json_equal(value, item) for item in schema["enum"]):
        raise ReviewRunnerError(f"response {path} is outside schema enum")
    if schema_type == "object":
        properties = schema["properties"]
        extras = sorted(set(value) - set(properties))
        missing = sorted(set(schema["required"]) - set(value))
        if extras:
            raise ReviewRunnerError(f"response {path} has extra fields: {extras}")
        if missing:
            raise ReviewRunnerError(f"response {path} is missing fields: {missing}")
        for key, child in properties.items():
            if key in value:
                _validate_instance(value[key], child, path=f"{path}.{key}")
    elif schema_type == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ReviewRunnerError(f"response {path} has too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ReviewRunnerError(f"response {path} has too many items")
        if schema.get("uniqueItems") and len(
            {canonical_json_bytes(item) for item in value}
        ) != len(value):
            raise ReviewRunnerError(f"response {path} items must be unique")
        for index, item in enumerate(value):
            _validate_instance(item, schema["items"], path=f"{path}[{index}]")
    elif schema_type == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ReviewRunnerError(f"response {path} is shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ReviewRunnerError(f"response {path} is longer than maxLength")
        if "pattern" in schema:
            try:
                matches = re.search(schema["pattern"], value) is not None
            except (re.error, TypeError) as exc:
                raise ReviewRunnerError(
                    f"response schema {path}.pattern is invalid"
                ) from exc
            if not matches:
                raise ReviewRunnerError(f"response {path} does not match pattern")
    elif schema_type in {"integer", "number"}:
        for keyword, predicate in (
            ("minimum", lambda item, limit: item >= limit),
            ("maximum", lambda item, limit: item <= limit),
            ("exclusiveMinimum", lambda item, limit: item > limit),
            ("exclusiveMaximum", lambda item, limit: item < limit),
        ):
            if keyword in schema and not predicate(value, schema[keyword]):
                raise ReviewRunnerError(f"response {path} violates {keyword}")


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    user_template: str
    packet_expected_schema: Mapping[str, Any]
    response_schema: Mapping[str, Any]
    canonical_sha256: str

    def messages(
        self, *, system_prompt: str, input_value: Mapping[str, Any]
    ) -> tuple[dict[str, str], ...]:
        user = self.user_template.replace(
            "{input_json}", canonical_json_bytes(input_value).decode("utf-8")
        ).replace(
            "{response_schema_json}",
            canonical_json_bytes(self.response_schema).decode("utf-8"),
        )
        return (
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user},
        )

    def parse_output(self, raw_output: str, item: "InputItem") -> Mapping[str, Any]:
        normalized = normalize_model_output(raw_output)
        return self.parse_normalized_output(normalized, item)

    def parse_normalized_output(
        self, normalized: NormalizedModelOutput, item: "InputItem"
    ) -> Mapping[str, Any]:
        if not normalized.text.startswith("{") or not normalized.text.endswith("}"):
            raise ReviewRunnerError(
                "normalized model output must be one strict JSON object without prose"
            )
        value = _strict_json(normalized.text, context="normalized model output")
        if not isinstance(value, Mapping):
            raise ReviewRunnerError("model output must be a JSON object")
        _validate_instance(value, self.response_schema)
        _validate_task_semantics(self.task_id, value, item)
        return value


@dataclass(frozen=True)
class PromptCatalog:
    system_prompt: str
    tasks: Mapping[str, TaskSpec]
    file_sha256: str
    canonical_sha256: str

    @classmethod
    def load(cls, path: Path) -> "PromptCatalog":
        value, raw = _load_yaml_or_json(path, label="prompt catalog")
        value = _require_mapping(value, context="prompt catalog")
        _require_exact_keys(
            value,
            required={"schema_version", "system_prompt", "tasks"},
            context="prompt catalog",
        )
        if value["schema_version"] != PROMPTS_SCHEMA_VERSION:
            raise ReviewRunnerError("unsupported prompt catalog schema_version")
        system = value["system_prompt"]
        if not isinstance(system, str) or not system.strip():
            raise ReviewRunnerError("prompt catalog system_prompt must be non-empty")
        raw_tasks = _require_mapping(value["tasks"], context="prompt catalog tasks")
        if not raw_tasks:
            raise ReviewRunnerError("prompt catalog must contain at least one task")
        tasks: dict[str, TaskSpec] = {}
        for task_id, raw_task in raw_tasks.items():
            if not isinstance(task_id, str) or not task_id:
                raise ReviewRunnerError("prompt task IDs must be non-empty strings")
            task = _require_mapping(raw_task, context=f"prompt task {task_id}")
            _require_exact_keys(
                task,
                required={"user_template", "packet_expected_schema", "response_schema"},
                context=f"prompt task {task_id}",
            )
            template = task["user_template"]
            if not isinstance(template, str) or template.count("{input_json}") != 1:
                raise ReviewRunnerError(
                    f"prompt task {task_id} must contain {{input_json}} exactly once"
                )
            if template.count("{response_schema_json}") != 1:
                raise ReviewRunnerError(
                    f"prompt task {task_id} must contain {{response_schema_json}} exactly once"
                )
            packet_schema = _require_mapping(
                task["packet_expected_schema"],
                context=f"prompt task {task_id} packet_expected_schema",
            )
            response_schema = _require_mapping(
                task["response_schema"],
                context=f"prompt task {task_id} response_schema",
            )
            _validate_schema_definition(response_schema)
            if response_schema.get("type") != "object":
                raise ReviewRunnerError(
                    f"prompt task {task_id} response schema must be an object"
                )
            tasks[task_id] = TaskSpec(
                task_id=task_id,
                user_template=template,
                packet_expected_schema=packet_schema,
                response_schema=response_schema,
                canonical_sha256=_sha256(canonical_json_bytes(task)),
            )
        return cls(
            system_prompt=system,
            tasks=tasks,
            file_sha256=_sha256(raw),
            canonical_sha256=_sha256(canonical_json_bytes(value)),
        )


@dataclass(frozen=True)
class DecoderSpec:
    values: Mapping[str, Any]
    canonical_sha256: str
    batch_size: int

    @classmethod
    def from_registry(cls, value: Any, *, batch_size: int) -> "DecoderSpec":
        value = _require_mapping(value, context="registry runtime.decoding")
        _require_exact_keys(
            value,
            required={
                "do_sample",
                "temperature",
                "top_p",
                "max_new_tokens",
            },
            context="registry runtime.decoding",
        )
        if value["do_sample"] is not False:
            raise ReviewRunnerError("review decoding must set do_sample=false")
        if value["temperature"] != 0.0 or value["top_p"] != 1.0:
            raise ReviewRunnerError(
                "greedy review decoding must freeze temperature=0.0 and top_p=1.0"
            )
        maximum = value["max_new_tokens"]
        if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 8192:
            raise ReviewRunnerError("max_new_tokens must be an integer in [1, 8192]")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 256:
            raise ReviewRunnerError("batch_size must be an integer in [1, 256]")
        return cls(
            values=dict(value),
            canonical_sha256=_sha256(canonical_json_bytes(value)),
            batch_size=batch_size,
        )

    @property
    def max_new_tokens(self) -> int:
        return int(self.values["max_new_tokens"])

    def generation_kwargs(self) -> dict[str, Any]:
        return {"do_sample": False, "max_new_tokens": self.max_new_tokens}


@dataclass(frozen=True)
class ModelIdentity:
    model_id: str
    revision: str
    snapshot_path: Path
    base_model_family: str
    reviewer_slot_id: str
    reviewer_role: str

    def __post_init__(self) -> None:
        for field in (
            "model_id",
            "base_model_family",
            "reviewer_slot_id",
            "reviewer_role",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ReviewRunnerError(f"{field} must be a non-empty string")
        if not isinstance(self.revision, str) or not _FULL_REVISION_RE.fullmatch(self.revision):
            raise ReviewRunnerError(
                "model revision must be a full 40-character lowercase hex revision"
            )

    def provenance(self) -> dict[str, str]:
        return {
            "reviewer_slot_id": self.reviewer_slot_id,
            "model_id": self.model_id,
            "model_revision": self.revision,
            "base_model_family": self.base_model_family,
            "reviewer_role": self.reviewer_role,
            "model_snapshot_path": str(self.snapshot_path.resolve()),
        }


@dataclass(frozen=True)
class Registry:
    identity: ModelIdentity
    decoder: DecoderSpec
    runtime: Mapping[str, Any]
    file_sha256: str
    canonical_sha256: str
    production_authorized: bool
    runner_implementation: Mapping[str, Any] | None

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        reviewer_slot_id: str,
        production: bool,
        batch_size: int,
    ) -> "Registry":
        value, raw = _load_yaml_or_json(path, label="reviewer registry")
        value = _require_mapping(value, context="reviewer registry")
        required = {
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
        }
        registry_status = value.get("registry_status")
        if registry_status == "frozen_for_production":
            required.add("runner_implementation")
        _require_exact_keys(value, required=required, context="reviewer registry")
        if value["schema_version"] != REGISTRY_SCHEMA_VERSION:
            raise ReviewRunnerError("unsupported reviewer registry schema_version")
        if value["offline_only"] is not True or value["target_model_use"] != "forbidden":
            raise ReviewRunnerError("reviewer registry must be offline-only and forbid target models")
        if production:
            if registry_status != "frozen_for_production":
                raise ReviewRunnerError("production requires registry_status=frozen_for_production")
            if value["production_review_authorized"] is not True:
                raise ReviewRunnerError("registry does not authorize production review")
        else:
            if registry_status not in {
                "frozen_for_synthetic_smoke",
                "frozen_for_production",
            }:
                raise ReviewRunnerError("synthetic smoke requires a frozen registry")
            if value["synthetic_smoke_authorized"] is not True:
                raise ReviewRunnerError("registry does not authorize synthetic smoke")
        authorized_implementation = None
        if registry_status == "frozen_for_production":
            authorized_implementation = _validate_authorized_runner_implementation(
                value["runner_implementation"]
            )
        runtime = _require_mapping(value["runtime"], context="reviewer registry runtime")
        for field, expected in (
            ("framework", "transformers"),
            ("local_files_only", True),
            ("trust_remote_code", False),
        ):
            if runtime.get(field) != expected:
                raise ReviewRunnerError(f"reviewer registry runtime.{field} must equal {expected!r}")
        decoder = DecoderSpec.from_registry(runtime.get("decoding"), batch_size=batch_size)
        slots = _require_mapping(value["slots"], context="reviewer registry slots")
        slot = _require_mapping(
            slots.get(reviewer_slot_id),
            context=f"reviewer registry slot {reviewer_slot_id}",
        )
        for field in (
            "role",
            "model_id",
            "model_revision",
            "base_model_family",
            "local_snapshot",
        ):
            if not isinstance(slot.get(field), str) or not slot[field]:
                raise ReviewRunnerError(f"reviewer registry slot {reviewer_slot_id}.{field} is empty")
        identity = ModelIdentity(
            model_id=slot["model_id"],
            revision=slot["model_revision"],
            snapshot_path=Path(slot["local_snapshot"]),
            base_model_family=slot["base_model_family"],
            reviewer_slot_id=reviewer_slot_id,
            reviewer_role=slot["role"],
        )
        return cls(
            identity=identity,
            decoder=decoder,
            runtime=runtime,
            file_sha256=_sha256(raw),
            canonical_sha256=_sha256(canonical_json_bytes(value)),
            production_authorized=bool(value["production_review_authorized"]),
            runner_implementation=authorized_implementation,
        )


@dataclass(frozen=True)
class InputItem:
    item_id: str
    id_field: str
    task_id: str
    input_value: Mapping[str, Any]
    line_number: int
    row_sha256: str
    canonical_sha256: str


def _jsonl_rows(raw: bytes, *, context: str) -> tuple[tuple[int, bytes], ...]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ReviewRunnerError(f"{context} must not contain a UTF-8 BOM")
    rows: list[tuple[int, bytes]] = []
    offset = 0
    line_number = 1
    while offset < len(raw):
        newline = raw.find(b"\n", offset)
        if newline < 0:
            row = raw[offset:]
            offset = len(raw)
        else:
            row = raw[offset:newline]
            offset = newline + 1
            if row.endswith(b"\r"):
                row = row[:-1]
        if not row:
            raise ReviewRunnerError(f"{context} line {line_number} is blank")
        rows.append((line_number, row))
        line_number += 1
    if not rows:
        raise ReviewRunnerError(f"{context} must contain at least one JSONL row")
    return tuple(rows)


def _resolve_id(record: Mapping[str, Any], *, line_number: int) -> tuple[str, str]:
    fields = [field for field in _ID_FIELDS if field in record]
    if len(fields) != 1:
        raise ReviewRunnerError(
            f"packet line {line_number} must contain exactly one recognized item-ID field"
        )
    field = fields[0]
    item_id = record[field]
    if not isinstance(item_id, str) or not _ITEM_ID_RE.fullmatch(item_id):
        raise ReviewRunnerError(f"packet line {line_number} has an invalid item ID")
    return field, item_id


def load_packet(
    path: Path,
    *,
    prompts: PromptCatalog,
    production: bool,
    production_task: str | None = None,
) -> tuple[tuple[InputItem, ...], str]:
    raw = _read_regular_file(path, label="input packet")
    items: list[InputItem] = []
    seen: set[str] = set()
    for line_number, row in _jsonl_rows(raw, context="input packet"):
        value = _strict_json(row, context=f"input packet line {line_number}")
        value = _require_mapping(value, context=f"input packet line {line_number}")
        id_field, item_id = _resolve_id(value, line_number=line_number)
        if production:
            if item_id.startswith("SYN-"):
                raise ReviewRunnerError("production packets must not contain SYN-* item IDs")
            if production_task is None:
                raise ReviewRunnerError("production packets require an explicit production task")
            task_id = production_task
            input_value = value
        else:
            if not item_id.startswith("SYN-"):
                raise ReviewRunnerError(
                    "default smoke mode accepts only SYN-* item IDs; use --production explicitly"
                )
            _require_exact_keys(
                value,
                required={"input_id", "task", "payload", "expected_schema"},
                context=f"synthetic packet line {line_number}",
            )
            task_id = value["task"]
            if not isinstance(task_id, str):
                raise ReviewRunnerError(f"synthetic packet line {line_number} task must be text")
            input_value = _require_mapping(
                value["payload"], context=f"synthetic packet line {line_number} payload"
            )
        if task_id not in prompts.tasks:
            raise ReviewRunnerError(f"packet line {line_number} has unknown task {task_id!r}")
        if not production and value["expected_schema"] != prompts.tasks[task_id].packet_expected_schema:
            raise ReviewRunnerError(
                f"synthetic packet line {line_number} expected_schema differs from prompt contract"
            )
        if item_id in seen:
            raise ReviewRunnerError(f"input packet contains duplicate item ID {item_id}")
        seen.add(item_id)
        items.append(
            InputItem(
                item_id=item_id,
                id_field=id_field,
                task_id=task_id,
                input_value=input_value,
                line_number=line_number,
                row_sha256=_sha256(row),
                canonical_sha256=_sha256(canonical_json_bytes(value)),
            )
        )
    return tuple(items), _sha256(raw)


def _validate_task_semantics(
    task_id: str, response: Mapping[str, Any], item: InputItem
) -> None:
    payload = item.input_value
    comparisons: list[tuple[str, Any]] = []
    if task_id == "persona_scalar":
        comparisons.append(("candidate_anonymous_id", payload.get("candidate_anonymous_id")))
    elif task_id == "persona_pair":
        comparisons.extend(
            (
                ("candidate_a_id", _require_mapping(payload.get("candidate_a"), context="candidate_a").get("id")),
                ("candidate_b_id", _require_mapping(payload.get("candidate_b"), context="candidate_b").get("id")),
            )
        )
    elif task_id == "persona_family":
        comparisons.append(("candidate_id", payload.get("candidate_id")))
        if response.get("family_id") not in payload.get("family_options", []):
            raise ReviewRunnerError("response family_id is absent from input family_options")
    else:
        comparisons.append(("blind_item_id", payload.get("blind_item_id")))
    for field, expected in comparisons:
        if response.get(field) != expected:
            raise ReviewRunnerError(f"response {field} differs from anonymous input ID")
    if task_id == "scenario_writer":
        indices = [move["move_index"] for move in response["moves"]]
        if indices != list(range(1, 26)):
            raise ReviewRunnerError("scenario move_index values must be exactly 1 through 25")


@dataclass(frozen=True)
class PreparedReview:
    mode: str
    registry: Registry
    prompts: PromptCatalog
    packet_path: Path
    packet_sha256: str
    items: tuple[InputItem, ...]


def prepare_review(
    *,
    registry_path: Path,
    reviewer_slot_id: str,
    prompts_path: Path,
    packet_path: Path,
    production: bool = False,
    production_task: str | None = None,
    batch_size: int = 1,
    selected_tasks: Sequence[str] = (),
) -> PreparedReview:
    prompts = PromptCatalog.load(prompts_path)
    registry = Registry.load(
        registry_path,
        reviewer_slot_id=reviewer_slot_id,
        production=production,
        batch_size=batch_size,
    )
    items, packet_sha256 = load_packet(
        packet_path,
        prompts=prompts,
        production=production,
        production_task=production_task,
    )
    if selected_tasks:
        unknown = sorted(set(selected_tasks) - set(prompts.tasks))
        if unknown:
            raise ReviewRunnerError(f"selected tasks are unknown: {unknown}")
        selected = set(selected_tasks)
        items = tuple(item for item in items if item.task_id in selected)
        if not items:
            raise ReviewRunnerError("task selection removed every packet item")
    return PreparedReview(
        mode=PRODUCTION_MODE if production else SYNTHETIC_MODE,
        registry=registry,
        prompts=prompts,
        packet_path=packet_path,
        packet_sha256=packet_sha256,
        items=items,
    )

def assigned_items(prepared: PreparedReview) -> tuple[InputItem, ...]:
    """Return only tasks authorized for the selected frozen reviewer role."""

    role = prepared.registry.identity.reviewer_role
    allowed = ROLE_TASK_ASSIGNMENTS.get(role)
    if allowed is None:
        raise ReviewRunnerError(f"reviewer role has no frozen task assignment: {role!r}")
    items = tuple(item for item in prepared.items if item.task_id in allowed)
    if not items:
        raise ReviewRunnerError(
            f"reviewer slot {prepared.registry.identity.reviewer_slot_id!r} "
            "has no assigned packet items"
        )
    return items


def review_contract(prepared: PreparedReview) -> dict[str, Any]:
    """Return the content-addressed contract that defines resumability."""

    identity = prepared.registry.identity
    return {
        "schema_version": REVIEW_CONTRACT_SCHEMA_VERSION,
        "mode": prepared.mode,
        "reviewer": {
            "reviewer_slot_id": identity.reviewer_slot_id,
            "reviewer_role": identity.reviewer_role,
            "model_id": identity.model_id,
            "model_revision": identity.revision,
            "base_model_family": identity.base_model_family,
        },
        "registry_file_sha256": prepared.registry.file_sha256,
        "registry_canonical_sha256": prepared.registry.canonical_sha256,
        "prompt_catalog_file_sha256": prepared.prompts.file_sha256,
        "prompt_catalog_canonical_sha256": prepared.prompts.canonical_sha256,
        "packet_file_sha256": prepared.packet_sha256,
        "decoding_canonical_sha256": prepared.registry.decoder.canonical_sha256,
        "decoding": dict(prepared.registry.decoder.values),
        "batch_size": prepared.registry.decoder.batch_size,
        "output_normalization": dict(OUTPUT_NORMALIZATION_CONTRACT),
        "runner_implementation": runner_implementation_binding(),
    }


def review_contract_sha256(prepared: PreparedReview) -> str:
    return _sha256(canonical_json_bytes(review_contract(prepared)))


def review_plan(prepared: PreparedReview) -> dict[str, Any]:
    """Build a JSON-serializable dry-run plan without loading transformers."""

    items = assigned_items(prepared)
    counts: dict[str, int] = {}
    for item in items:
        counts[item.task_id] = counts.get(item.task_id, 0) + 1
    identity = prepared.registry.identity
    return {
        "status": "DRY_RUN",
        "mode": prepared.mode,
        "model_loaded": False,
        "network_allowed": False,
        "reviewer": identity.provenance(),
        "snapshot_directory_present": identity.snapshot_path.is_dir(),
        "registry_file_sha256": prepared.registry.file_sha256,
        "registry_canonical_sha256": prepared.registry.canonical_sha256,
        "prompt_catalog_file_sha256": prepared.prompts.file_sha256,
        "prompt_catalog_canonical_sha256": prepared.prompts.canonical_sha256,
        "packet_path": str(prepared.packet_path.resolve()),
        "packet_file_sha256": prepared.packet_sha256,
        "review_contract_sha256": review_contract_sha256(prepared),
        "assigned_item_count": len(items),
        "assigned_task_counts": counts,
        "decoding": {
            **dict(prepared.registry.decoder.values),
            "batch_size": prepared.registry.decoder.batch_size,
            "canonical_sha256": prepared.registry.decoder.canonical_sha256,
        },
    }


class ReviewerBackend(Protocol):
    """Small injectable boundary used by the real HF backend and unit fakes."""

    @property
    def provenance(self) -> Mapping[str, Any]:
        ...

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        decoder: DecoderSpec,
    ) -> str:
        ...


def _snapshot_provenance(identity: ModelIdentity) -> dict[str, Any]:
    snapshot = identity.snapshot_path
    if snapshot.name != identity.revision:
        raise ReviewRunnerError(
            "local snapshot directory basename must equal the frozen model revision"
        )
    if not snapshot.is_dir():
        raise ReviewRunnerError(f"local model snapshot is unavailable: {snapshot}")
    core_hashes: dict[str, str] = {}
    for name in (
        "config.json",
        "generation_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
    ):
        candidate = snapshot / name
        if candidate.is_file():
            try:
                core_hashes[name] = _sha256(candidate.read_bytes())
            except OSError as exc:
                raise ReviewRunnerError(
                    f"cannot read local snapshot metadata {candidate}: {exc}"
                ) from exc
    if "config.json" not in core_hashes:
        raise ReviewRunnerError("local model snapshot is missing config.json")
    return {
        "snapshot_path": str(snapshot.resolve()),
        "snapshot_revision": identity.revision,
        "core_file_sha256s": core_hashes,
        "core_manifest_sha256": _sha256(canonical_json_bytes(core_hashes)),
    }


class LocalHuggingFaceBackend:
    """Greedy, network-disabled text generation from one frozen local snapshot."""

    def __init__(
        self,
        *,
        model: Any,
        tokenizer: Any,
        torch_module: Any,
        provenance: Mapping[str, Any],
    ) -> None:
        self._model = model
        self._tokenizer = tokenizer
        self._torch = torch_module
        self._provenance = dict(provenance)

    @property
    def provenance(self) -> Mapping[str, Any]:
        return self._provenance

    @classmethod
    def load(cls, registry: Registry) -> "LocalHuggingFaceBackend":
        # Set both switches before importing transformers.  All from_pretrained
        # calls also carry local_files_only=True as a second, explicit lock.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        try:
            import torch
            import transformers
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - exercised on GPU host
            raise ReviewRunnerError(
                "torch and transformers are required for a non-dry local review"
            ) from exc

        expected_transformers = registry.runtime.get("framework_version")
        expected_torch = registry.runtime.get("torch_version")
        if transformers.__version__ != expected_transformers:
            raise ReviewRunnerError(
                "transformers version differs from frozen registry: "
                f"expected {expected_transformers}, got {transformers.__version__}"
            )
        if torch.__version__ != expected_torch:
            raise ReviewRunnerError(
                "torch version differs from frozen registry: "
                f"expected {expected_torch}, got {torch.__version__}"
            )

        snapshot_info = _snapshot_provenance(registry.identity)
        dtype_name = registry.runtime.get("dtype")
        dtype_by_name = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }
        if dtype_name not in dtype_by_name:
            raise ReviewRunnerError(f"unsupported frozen dtype: {dtype_name!r}")
        device_map = registry.runtime.get("device_map")
        if not isinstance(device_map, str) or not device_map:
            raise ReviewRunnerError("registry runtime.device_map must be non-empty")

        snapshot = str(registry.identity.snapshot_path)
        common = {
            "local_files_only": True,
            "trust_remote_code": False,
        }
        try:
            tokenizer = AutoTokenizer.from_pretrained(snapshot, **common)
            model = AutoModelForCausalLM.from_pretrained(
                snapshot,
                device_map=device_map,
                torch_dtype=dtype_by_name[dtype_name],
                **common,
            )
        except Exception as exc:  # pragma: no cover - exercised on GPU host
            raise ReviewRunnerError(
                f"failed to load frozen local snapshot {snapshot}: {exc}"
            ) from exc
        model.eval()
        provenance = {
            **snapshot_info,
            "python_version": platform.python_version(),
            "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
            "cuda_version": torch.version.cuda,
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_device_count": int(torch.cuda.device_count()),
            "cuda_device_names": [
                torch.cuda.get_device_name(index)
                for index in range(torch.cuda.device_count())
            ],
            "hostname": platform.node(),
            "offline_environment": {
                "HF_HUB_OFFLINE": os.environ["HF_HUB_OFFLINE"],
                "TRANSFORMERS_OFFLINE": os.environ["TRANSFORMERS_OFFLINE"],
            },
        }
        return cls(
            model=model,
            tokenizer=tokenizer,
            torch_module=torch,
            provenance=provenance,
        )

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        decoder: DecoderSpec,
    ) -> str:
        try:
            rendered = self._tokenizer.apply_chat_template(
                list(messages),
                tokenize=False,
                add_generation_prompt=True,
            )
            encoded = self._tokenizer(
                rendered,
                return_tensors="pt",
                add_special_tokens=False,
            )
            input_device = next(self._model.parameters()).device
            encoded = {
                key: value.to(input_device)
                for key, value in encoded.items()
            }
            input_length = int(encoded["input_ids"].shape[-1])
            generation_kwargs = decoder.generation_kwargs()
            if self._tokenizer.pad_token_id is not None:
                generation_kwargs["pad_token_id"] = self._tokenizer.pad_token_id
            elif self._tokenizer.eos_token_id is not None:
                generation_kwargs["pad_token_id"] = self._tokenizer.eos_token_id
            with self._torch.inference_mode():
                generated = self._model.generate(
                    **encoded,
                    **generation_kwargs,
                )
            completion_ids = generated[0, input_length:]
            return self._tokenizer.decode(
                completion_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
        except ReviewRunnerError:
            raise
        except Exception as exc:  # pragma: no cover - exercised on GPU host
            raise ReviewRunnerError(f"local model generation failed: {exc}") from exc


class AppendOnlyLedger:
    """Locked JSONL writer that verifies every prior hash-chain link."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None
        self._records: list[Mapping[str, Any]] = []
        self._last_hash: str | None = None

    def __enter__(self) -> "AppendOnlyLedger":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_APPEND | os.O_CREAT
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            self._fd = os.open(self.path, flags, 0o600)
            file_stat = os.fstat(self._fd)
            if not stat.S_ISREG(file_stat.st_mode):
                raise ReviewRunnerError(
                    f"append-only output is not a regular file: {self.path}"
                )
            fcntl.flock(self._fd, fcntl.LOCK_EX)
            self._verify_existing()
        except Exception:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            raise
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None

    @property
    def records(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._records)

    def _require_open(self) -> int:
        if self._fd is None:
            raise ReviewRunnerError("append-only ledger is not open")
        return self._fd

    def _read_all(self) -> bytes:
        fd = self._require_open()
        os.lseek(fd, 0, os.SEEK_SET)
        blocks: list[bytes] = []
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                return b"".join(blocks)
            blocks.append(block)

    def _verify_existing(self) -> None:
        raw = self._read_all()
        self._records = []
        self._last_hash = None
        if not raw:
            return
        if not raw.endswith(b"\n"):
            raise ReviewRunnerError(
                "append-only output ends with a partial JSONL record"
            )
        for line_number, row in _jsonl_rows(
            raw, context="append-only output"
        ):
            value = _strict_json(
                row, context=f"append-only output line {line_number}"
            )
            value = _require_mapping(
                value, context=f"append-only output line {line_number}"
            )
            if canonical_json_bytes(value) != row:
                raise ReviewRunnerError(
                    f"append-only output line {line_number} is not canonical JSON"
                )
            if value.get("schema_version") != LEDGER_SCHEMA_VERSION:
                raise ReviewRunnerError(
                    f"append-only output line {line_number} has wrong schema_version"
                )
            observed_hash = value.get("record_sha256")
            if not isinstance(observed_hash, str) or not _SHA256_RE.fullmatch(
                observed_hash
            ):
                raise ReviewRunnerError(
                    f"append-only output line {line_number} has invalid record hash"
                )
            body = dict(value)
            del body["record_sha256"]
            expected_hash = _sha256(canonical_json_bytes(body))
            if observed_hash != expected_hash:
                raise ReviewRunnerError(
                    f"append-only output line {line_number} record hash mismatch"
                )
            if body.get("previous_record_sha256") != self._last_hash:
                raise ReviewRunnerError(
                    f"append-only output line {line_number} hash chain mismatch"
                )
            self._records.append(value)
            self._last_hash = observed_hash

    def accepted_item_ids(self, *, contract_sha256: str) -> frozenset[str]:
        return frozenset(
            str(record["item"]["item_id"])
            for record in self._records
            if record.get("status") == "accepted"
            and record.get("review_contract_sha256") == contract_sha256
            and isinstance(record.get("item"), Mapping)
            and isinstance(record["item"].get("item_id"), str)
        )

    def append(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        if "record_sha256" in body or "previous_record_sha256" in body:
            raise ReviewRunnerError("ledger body contains reserved chain fields")
        chained = {
            **dict(body),
            "previous_record_sha256": self._last_hash,
        }
        record_hash = _sha256(canonical_json_bytes(chained))
        record = {**chained, "record_sha256": record_hash}
        encoded = canonical_json_bytes(record) + b"\n"
        fd = self._require_open()
        offset = 0
        while offset < len(encoded):
            written = os.write(fd, encoded[offset:])
            if written <= 0:
                raise ReviewRunnerError("append-only output write made no progress")
            offset += written
        os.fsync(fd)
        self._records.append(record)
        self._last_hash = record_hash
        return record


@dataclass(frozen=True)
class RunSummary:
    review_contract_sha256: str
    assigned: int
    skipped_accepted: int
    attempted: int
    accepted: int
    rejected_invalid_output: int
    output_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "COMPLETE"
            if self.rejected_invalid_output == 0
            else "COMPLETED_WITH_INVALID_OUTPUTS",
            "review_contract_sha256": self.review_contract_sha256,
            "assigned": self.assigned,
            "skipped_accepted": self.skipped_accepted,
            "attempted": self.attempted,
            "accepted": self.accepted,
            "rejected_invalid_output": self.rejected_invalid_output,
            "output_path": self.output_path,
        }


def _timestamp_utc(clock: Callable[[], datetime]) -> str:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReviewRunnerError("runner clock must return a timezone-aware datetime")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _attempt_id() -> str:
    return f"ATT-{uuid.uuid4().hex}"


def _attempt_body(
    *,
    prepared: PreparedReview,
    item: InputItem,
    messages: Sequence[Mapping[str, str]],
    backend_provenance: Mapping[str, Any],
    contract_sha256: str,
    attempt_id: str,
    started_at: str,
    finished_at: str,
    status: str,
    raw_output: str | None,
    normalization: str | None,
    normalized_output_sha256: str | None,
    response: Mapping[str, Any] | None,
    error: str | None,
) -> dict[str, Any]:
    task = prepared.prompts.tasks[item.task_id]
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "mode": prepared.mode,
        "status": status,
        "review_contract_sha256": contract_sha256,
        "review_contract": review_contract(prepared),
        "reviewer": prepared.registry.identity.provenance(),
        "runtime_provenance": dict(backend_provenance),
        "packet": {
            "path": str(prepared.packet_path.resolve()),
            "file_sha256": prepared.packet_sha256,
        },
        "item": {
            "item_id": item.item_id,
            "id_field": item.id_field,
            "task_id": item.task_id,
            "line_number": item.line_number,
            "row_sha256": item.row_sha256,
            "canonical_sha256": item.canonical_sha256,
        },
        "prompt": {
            "catalog_file_sha256": prepared.prompts.file_sha256,
            "catalog_canonical_sha256": prepared.prompts.canonical_sha256,
            "task_canonical_sha256": task.canonical_sha256,
            "messages": [dict(message) for message in messages],
            "messages_canonical_sha256": _sha256(canonical_json_bytes(messages)),
        },
        "decoding": {
            "parameters": dict(prepared.registry.decoder.values),
            "batch_size": prepared.registry.decoder.batch_size,
            "canonical_sha256": prepared.registry.decoder.canonical_sha256,
        },
        "raw_output": raw_output,
        "raw_output_sha256": None
        if raw_output is None
        else _sha256(raw_output.encode("utf-8")),
        "normalization": normalization,
        "normalized_output_sha256": normalized_output_sha256,
        "response": None if response is None else dict(response),
        "response_canonical_sha256": None
        if response is None
        else _sha256(canonical_json_bytes(response)),
        "error": error,
    }


def run_review(
    prepared: PreparedReview,
    *,
    output_path: Path,
    backend: ReviewerBackend | None = None,
    backend_factory: Callable[[Registry], ReviewerBackend] = LocalHuggingFaceBackend.load,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    attempt_id_factory: Callable[[], str] = _attempt_id,
) -> RunSummary:
    """Run assigned items, retaining invalid attempts and resuming accepted ones."""

    items = assigned_items(prepared)
    contract_sha = review_contract_sha256(prepared)
    accepted_count = 0
    invalid_count = 0
    attempted = 0
    with AppendOnlyLedger(output_path) as ledger:
        already_accepted = ledger.accepted_item_ids(contract_sha256=contract_sha)
        pending = [item for item in items if item.item_id not in already_accepted]
        skipped = len(items) - len(pending)
        if pending and backend is None:
            backend = backend_factory(prepared.registry)
        backend_provenance: Mapping[str, Any] = (
            {} if backend is None else backend.provenance
        )

        for item in pending:
            task = prepared.prompts.tasks[item.task_id]
            messages = task.messages(
                system_prompt=prepared.prompts.system_prompt,
                input_value=item.input_value,
            )
            started_at = _timestamp_utc(clock)
            attempt_id = attempt_id_factory()
            if not isinstance(attempt_id, str) or not attempt_id:
                raise ReviewRunnerError("attempt ID factory returned an invalid value")
            attempted += 1
            try:
                raw_output = backend.generate(  # type: ignore[union-attr]
                    messages, prepared.registry.decoder
                )
            except Exception as exc:
                finished_at = _timestamp_utc(clock)
                body = _attempt_body(
                    prepared=prepared,
                    item=item,
                    messages=messages,
                    backend_provenance=backend_provenance,
                    contract_sha256=contract_sha,
                    attempt_id=attempt_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    status="generation_error",
                    raw_output=None,
                    normalization=None,
                    normalized_output_sha256=None,
                    response=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
                ledger.append(body)
                raise ReviewRunnerError(
                    f"generation failed for {item.item_id}; attempt was appended"
                ) from exc
            if not isinstance(raw_output, str):
                raw_output = repr(raw_output)
                normalized_output = None
                validation_error: ReviewRunnerError | None = ReviewRunnerError(
                    "model output must be text"
                )
                response = None
            else:
                normalized_output = None
                try:
                    normalized_output = normalize_model_output(raw_output)
                    response = task.parse_normalized_output(normalized_output, item)
                    validation_error = None
                except ReviewRunnerError as exc:
                    response = None
                    validation_error = exc
            finished_at = _timestamp_utc(clock)
            if validation_error is None:
                status = "accepted"
                accepted_count += 1
                error = None
            else:
                status = "rejected_invalid_output"
                invalid_count += 1
                error = f"{type(validation_error).__name__}: {validation_error}"
            ledger.append(
                _attempt_body(
                    prepared=prepared,
                    item=item,
                    messages=messages,
                    backend_provenance=backend_provenance,
                    contract_sha256=contract_sha,
                    attempt_id=attempt_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    status=status,
                    raw_output=raw_output,
                    normalization=None
                    if normalized_output is None
                    else normalized_output.normalization,
                    normalized_output_sha256=None
                    if normalized_output is None
                    else normalized_output.sha256,
                    response=response,
                    error=error,
                )
            )

    return RunSummary(
        review_contract_sha256=contract_sha,
        assigned=len(items),
        skipped_accepted=skipped,
        attempted=attempted,
        accepted=accepted_count,
        rejected_invalid_output=invalid_count,
        output_path=str(output_path.resolve()),
    )
