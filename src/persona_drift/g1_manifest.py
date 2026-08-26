"""Generic, fail-closed manifest utilities for the restart-v2.3 G1 gate.

This module deliberately does not contain Persona or Topic content.  It provides
the small amount of infrastructure needed to prove that tracked G1 artifacts
exist, are complete, and still match their frozen hashes.  Scientific/domain
validation remains the responsibility of the Persona and Topic contracts.

The canonical structured-data representation is UTF-8 JSON with sorted object
keys, no insignificant whitespace, no ASCII escaping, and no trailing newline.
Both JSON and YAML inputs are parsed first and then encoded with that same rule.
Consequently semantically identical JSON and YAML documents have the same
canonical hash, while their exact file-byte hashes remain distinct.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover - declared project dependency
    yaml = None


CANONICALIZATION_VERSION = "g1-canonical-json-v1"
DEFAULT_G1_CONFIG = Path("configs/g1_v2_3.yaml")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DOTTED_PART_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_PLACEHOLDER_EXACT = {
    "",
    "?",
    "candidate_only",
    "changeme",
    "not_set",
    "notset",
    "open",
    "pending",
    "placeholder",
    "tbd",
    "todo",
    "unknown",
    "unset",
}
_PLACEHOLDER_PREFIXES = (
    "candidate_only_open_",
    "open_must_",
    "placeholder_",
    "tbd_",
    "todo_",
)
_PREPARATION_STATUSES = {
    "building",
    "draft",
    "preparation",
    "protocol_skeleton_only",
}
_READY_CANDIDATE_STATUSES = {
    "freeze_candidate",
    "g1_frozen",
    "ready_for_g1_freeze",
    "ready_for_validation",
}


class ManifestValidationError(ValueError):
    """Raised when bytes or structured manifest content violate the contract."""


class ReadinessStatus(str, Enum):
    PREPARATION = "PREPARATION"
    NOT_READY = "NOT_READY"
    READY = "READY"


@dataclass(frozen=True)
class PlaceholderFinding:
    path: str
    value: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "value": self.value, "reason": self.reason}


@dataclass(frozen=True)
class ReadinessCheck:
    check_id: str
    passed: bool
    code: str
    message: str
    artifact_id: Optional[str] = None
    path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "check_id": self.check_id,
            "passed": self.passed,
            "code": self.code,
            "message": self.message,
        }
        if self.artifact_id is not None:
            result["artifact_id"] = self.artifact_id
        if self.path is not None:
            result["path"] = self.path
        return result


@dataclass(frozen=True)
class G1ReadinessReport:
    config_path: str
    status: ReadinessStatus
    checks: Tuple[ReadinessCheck, ...]

    @property
    def ready(self) -> bool:
        return self.status is ReadinessStatus.READY

    @property
    def failed_checks(self) -> Tuple[ReadinessCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": "G1",
            "status": self.status.value,
            "ready": self.ready,
            "config_path": self.config_path,
            "summary": {
                "checks": len(self.checks),
                "passed": sum(check.passed for check in self.checks),
                "failed": len(self.failed_checks),
            },
            "checks": [check.to_dict() for check in self.checks],
        }


def _reject_json_constant(value: str) -> None:
    raise ManifestValidationError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestValidationError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


if yaml is not None:

    class _UniqueKeySafeLoader(yaml.SafeLoader):
        pass


    def _construct_unique_mapping(
        loader: Any, node: Any, deep: bool = False
    ) -> dict[Any, Any]:
        loader.flatten_mapping(node)
        result: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            try:
                duplicate = key in result
            except TypeError as exc:
                raise ManifestValidationError(
                    "YAML mapping keys must be scalar/hashable"
                ) from exc
            if duplicate:
                raise ManifestValidationError(f"duplicate YAML mapping key: {key!r}")
            result[key] = loader.construct_object(value_node, deep=deep)
        return result


    _UniqueKeySafeLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        _construct_unique_mapping,
    )


def _normalize_json_value(value: Any, *, path: str = "$") -> Any:
    """Return a JSON-compatible value and reject lossy/ambiguous types."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ManifestValidationError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ManifestValidationError(
                    f"{path} contains non-string mapping key {key!r}"
                )
            normalized[key] = _normalize_json_value(item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _normalize_json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ManifestValidationError(
        f"{path} contains unsupported canonical-data type {type(value).__name__}"
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize structured data with ``g1-canonical-json-v1``."""

    normalized = _normalize_json_value(value)
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:  # defensive; normalization is stricter
        raise ManifestValidationError("structured value is not canonicalizable") from exc
    return encoded.encode("utf-8")


def canonical_data_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_bytes_sha256(path: Path | str) -> str:
    target = Path(path)
    digest = hashlib.sha256()
    try:
        with target.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ManifestValidationError(f"cannot read file bytes: {target}: {exc}") from exc
    return digest.hexdigest()


def _validate_sha256(value: Any, *, field: str, reject_placeholder: bool = True) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ManifestValidationError(f"{field} must be 64 lowercase hexadecimal characters")
    if reject_placeholder and len(set(value)) == 1:
        raise ManifestValidationError(f"{field} is a repeated-character placeholder hash")
    return value


def verify_file_sha256(path: Path | str, expected_sha256: str) -> str:
    expected = _validate_sha256(expected_sha256, field="expected_sha256")
    observed = file_bytes_sha256(path)
    if observed != expected:
        raise ManifestValidationError(
            f"file SHA256 mismatch for {Path(path)}: expected {expected}, observed {observed}"
        )
    return observed


def load_structured_bytes(data: bytes, *, format_name: str) -> Any:
    """Strictly parse UTF-8 JSON, JSONL, or YAML bytes."""

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestValidationError("structured manifest must be valid UTF-8") from exc
    normalized_format = format_name.lower().lstrip(".")
    if normalized_format == "json":
        try:
            return json.loads(
                text,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_json_constant,
            )
        except ManifestValidationError:
            raise
        except json.JSONDecodeError as exc:
            raise ManifestValidationError(f"invalid JSON: {exc}") from exc
    if normalized_format == "jsonl":
        records = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(
                    line,
                    object_pairs_hook=_unique_object,
                    parse_constant=_reject_json_constant,
                )
            except ManifestValidationError:
                raise
            except json.JSONDecodeError as exc:
                raise ManifestValidationError(
                    f"invalid JSONL record on line {line_number}: {exc}"
                ) from exc
            if not isinstance(record, Mapping):
                raise ManifestValidationError(
                    f"JSONL record on line {line_number} must be an object"
                )
            records.append(record)
        if not records:
            raise ManifestValidationError("JSONL manifest must contain at least one record")
        return records
    if normalized_format in {"yaml", "yml"}:
        if yaml is None:
            raise ManifestValidationError("PyYAML is required to parse YAML manifests")
        try:
            value = yaml.load(text, Loader=_UniqueKeySafeLoader)
        except ManifestValidationError:
            raise
        except yaml.YAMLError as exc:
            raise ManifestValidationError(f"invalid YAML: {exc}") from exc
        if value is None:
            raise ManifestValidationError("YAML manifest cannot be empty")
        return value
    raise ManifestValidationError(
        f"unsupported structured manifest format {format_name!r}"
    )


def infer_structured_format(path: Path | str) -> str:
    suffix = Path(path).suffix.lower()
    formats = {".json": "json", ".jsonl": "jsonl", ".yaml": "yaml", ".yml": "yaml"}
    if suffix not in formats:
        raise ManifestValidationError(
            f"cannot infer structured format from suffix {suffix!r}"
        )
    return formats[suffix]


def load_structured_file(path: Path | str, *, format_name: Optional[str] = None) -> Any:
    target = Path(path)
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise ManifestValidationError(f"cannot read structured manifest: {target}: {exc}") from exc
    return load_structured_bytes(
        data,
        format_name=format_name or infer_structured_format(target),
    )


def canonical_structured_file_sha256(
    path: Path | str, *, format_name: Optional[str] = None
) -> str:
    return canonical_data_sha256(load_structured_file(path, format_name=format_name))


def _placeholder_reason(value: str) -> Optional[str]:
    stripped = value.strip()
    lowered = stripped.lower().replace("-", "_").replace(" ", "_")
    if lowered in _PLACEHOLDER_EXACT:
        return "placeholder token"
    if lowered.startswith(_PLACEHOLDER_PREFIXES):
        return "open/candidate placeholder state"
    if "example.invalid" in lowered or "changeme" in lowered:
        return "placeholder URI/value"
    if re.fullmatch(r"<[^<>]+>|\{\{[^{}]+\}\}|\$\{[^{}]+\}", stripped):
        return "unresolved template token"
    if _SHA256_RE.fullmatch(lowered) and len(set(lowered)) == 1:
        return "repeated-character placeholder hash"
    return None


def find_placeholders(value: Any, *, path: str = "$") -> Tuple[PlaceholderFinding, ...]:
    """Recursively find unresolved string placeholders with precise paths."""

    findings: list[PlaceholderFinding] = []
    if isinstance(value, str):
        reason = _placeholder_reason(value)
        if reason is not None:
            findings.append(PlaceholderFinding(path=path, value=value, reason=reason))
    elif isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}"
            findings.extend(find_placeholders(item, path=child))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            findings.extend(find_placeholders(item, path=f"{path}[{index}]"))
    return tuple(findings)


def _split_dotted_path(path: str) -> Tuple[str, ...]:
    if not isinstance(path, str) or not path.strip():
        raise ManifestValidationError("required field path must be non-empty")
    parts = tuple(path.split("."))
    if any(not _DOTTED_PART_RE.fullmatch(part) for part in parts):
        raise ManifestValidationError(f"invalid dotted field path {path!r}")
    return parts


def value_at_path(value: Any, dotted_path: str) -> Any:
    current = value
    for part in _split_dotted_path(dotted_path):
        if not isinstance(current, Mapping) or part not in current:
            raise KeyError(dotted_path)
        current = current[part]
    return current


def _is_missing_required_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, tuple, Mapping)) and len(value) == 0:
        return True
    return False


def missing_required_fields(
    value: Any, required_fields: Iterable[str]
) -> Tuple[str, ...]:
    missing: list[str] = []
    if not isinstance(value, Mapping):
        return tuple(required_fields)
    for field in required_fields:
        try:
            found = value_at_path(value, field)
        except KeyError:
            missing.append(field)
            continue
        if _is_missing_required_value(found):
            missing.append(field)
    return tuple(missing)


def require_fields(value: Any, required_fields: Iterable[str], *, context: str) -> None:
    required = tuple(required_fields)
    missing = missing_required_fields(value, required)
    if missing:
        raise ManifestValidationError(
            f"{context} is missing required fields: {', '.join(missing)}"
        )


def _check(
    checks: list[ReadinessCheck],
    *,
    check_id: str,
    passed: bool,
    code: str,
    message: str,
    artifact_id: Optional[str] = None,
    path: Optional[Path] = None,
) -> None:
    checks.append(
        ReadinessCheck(
            check_id=check_id,
            passed=passed,
            code=code,
            message=message,
            artifact_id=artifact_id,
            path=str(path) if path is not None else None,
        )
    )


def _artifact_root(config_path: Path, config: Mapping[str, Any]) -> Path:
    configured = config.get("artifact_root")
    if configured is None:
        base = config_path.parent.parent if config_path.parent.name == "configs" else config_path.parent
        return base.resolve()
    if not isinstance(configured, str) or not configured.strip():
        raise ManifestValidationError("artifact_root must be a non-empty path string")
    root = Path(configured)
    if not root.is_absolute():
        root = config_path.parent / root
    return root.resolve()


def _resolve_artifact_path(root: Path, path_value: Any) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise ManifestValidationError("artifact path must be a non-empty string")
    raw = Path(path_value)
    target = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ManifestValidationError(
            f"artifact path escapes artifact_root: {path_value!r}"
        ) from exc
    return target


def _as_string_tuple(value: Any, *, field: str) -> Tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ManifestValidationError(f"{field} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise ManifestValidationError(f"{field} contains duplicate values")
    return tuple(value)


def _validate_artifact(
    requirement: Mapping[str, Any],
    *,
    artifact_root: Path,
    checks: list[ReadinessCheck],
) -> None:
    artifact_id_raw = requirement.get("artifact_id")
    artifact_id = artifact_id_raw if isinstance(artifact_id_raw, str) else "<invalid>"
    check_prefix = f"artifact:{artifact_id}"
    try:
        require_fields(
            requirement,
            ("artifact_id", "path", "format", "file_sha256"),
            context=check_prefix,
        )
        if not isinstance(artifact_id_raw, str) or not artifact_id_raw.strip():
            raise ManifestValidationError("artifact_id must be non-empty")
        target = _resolve_artifact_path(artifact_root, requirement["path"])
    except ManifestValidationError as exc:
        _check(
            checks,
            check_id=f"{check_prefix}:spec",
            passed=False,
            code="ARTIFACT_SPEC_INVALID",
            message=str(exc),
            artifact_id=artifact_id,
        )
        return

    if not target.is_file():
        _check(
            checks,
            check_id=f"{check_prefix}:exists",
            passed=False,
            code="ARTIFACT_MISSING",
            message="required artifact file does not exist",
            artifact_id=artifact_id,
            path=target,
        )
        return
    _check(
        checks,
        check_id=f"{check_prefix}:exists",
        passed=True,
        code="ARTIFACT_PRESENT",
        message="required artifact file exists",
        artifact_id=artifact_id,
        path=target,
    )

    try:
        expected_file_sha = _validate_sha256(
            requirement["file_sha256"], field=f"{check_prefix}.file_sha256"
        )
        raw_bytes = target.read_bytes()
        observed_file_sha = hashlib.sha256(raw_bytes).hexdigest()
        if observed_file_sha != expected_file_sha:
            raise ManifestValidationError(
                f"expected {expected_file_sha}, observed {observed_file_sha}"
            )
    except (OSError, ManifestValidationError) as exc:
        _check(
            checks,
            check_id=f"{check_prefix}:file_sha256",
            passed=False,
            code="FILE_SHA256_MISMATCH",
            message=str(exc),
            artifact_id=artifact_id,
            path=target,
        )
        return
    _check(
        checks,
        check_id=f"{check_prefix}:file_sha256",
        passed=True,
        code="FILE_SHA256_VERIFIED",
        message=observed_file_sha,
        artifact_id=artifact_id,
        path=target,
    )

    format_name = requirement["format"]
    if not isinstance(format_name, str):
        _check(
            checks,
            check_id=f"{check_prefix}:format",
            passed=False,
            code="ARTIFACT_FORMAT_INVALID",
            message="format must be a string",
            artifact_id=artifact_id,
            path=target,
        )
        return
    normalized_format = format_name.lower().lstrip(".")
    if normalized_format in {"bytes", "binary"}:
        return
    if normalized_format == "yml":
        normalized_format = "yaml"
    if normalized_format not in {"json", "jsonl", "yaml"}:
        _check(
            checks,
            check_id=f"{check_prefix}:format",
            passed=False,
            code="ARTIFACT_FORMAT_INVALID",
            message=f"unsupported artifact format {format_name!r}",
            artifact_id=artifact_id,
            path=target,
        )
        return

    try:
        if requirement.get("canonicalization_version") != CANONICALIZATION_VERSION:
            raise ManifestValidationError(
                "structured artifact must declare "
                f"canonicalization_version={CANONICALIZATION_VERSION!r}"
            )
        expected_canonical_sha = _validate_sha256(
            requirement.get("canonical_sha256"),
            field=f"{check_prefix}.canonical_sha256",
        )
        parsed = load_structured_bytes(raw_bytes, format_name=normalized_format)
        observed_canonical_sha = canonical_data_sha256(parsed)
        if observed_canonical_sha != expected_canonical_sha:
            raise ManifestValidationError(
                f"expected {expected_canonical_sha}, observed {observed_canonical_sha}"
            )
    except ManifestValidationError as exc:
        _check(
            checks,
            check_id=f"{check_prefix}:canonical",
            passed=False,
            code="CANONICAL_MANIFEST_INVALID",
            message=str(exc),
            artifact_id=artifact_id,
            path=target,
        )
        return
    _check(
        checks,
        check_id=f"{check_prefix}:canonical",
        passed=True,
        code="CANONICAL_SHA256_VERIFIED",
        message=observed_canonical_sha,
        artifact_id=artifact_id,
        path=target,
    )

    try:
        required_fields = _as_string_tuple(
            requirement.get("required_fields", []),
            field=f"{check_prefix}.required_fields",
        )
        required_record_fields = _as_string_tuple(
            requirement.get("required_record_fields", []),
            field=f"{check_prefix}.required_record_fields",
        )
        if not required_fields and not required_record_fields:
            raise ManifestValidationError(
                "structured artifact needs required_fields or required_record_fields"
            )
        if required_fields:
            require_fields(parsed, required_fields, context=check_prefix)
        if required_record_fields:
            if not isinstance(parsed, list) or not parsed:
                raise ManifestValidationError(
                    "required_record_fields requires a non-empty JSONL/list artifact"
                )
            for index, record in enumerate(parsed):
                require_fields(
                    record,
                    required_record_fields,
                    context=f"{check_prefix}[{index}]",
                )
        expected_values = requirement.get("expected_values", {})
        if not isinstance(expected_values, Mapping):
            raise ManifestValidationError("expected_values must be a mapping")
        for dotted_path, expected in expected_values.items():
            if not isinstance(dotted_path, str):
                raise ManifestValidationError("expected_values keys must be strings")
            try:
                observed = value_at_path(parsed, dotted_path)
            except KeyError as exc:
                raise ManifestValidationError(
                    f"expected value field is missing: {dotted_path}"
                ) from exc
            if observed != expected:
                raise ManifestValidationError(
                    f"{dotted_path} must equal {expected!r}; observed {observed!r}"
                )
        expected_lengths = requirement.get("expected_lengths", {})
        if not isinstance(expected_lengths, Mapping):
            raise ManifestValidationError("expected_lengths must be a mapping")
        for dotted_path, expected_length in expected_lengths.items():
            if (
                isinstance(expected_length, bool)
                or not isinstance(expected_length, int)
                or expected_length < 0
            ):
                raise ManifestValidationError(
                    f"expected length for {dotted_path} must be a non-negative integer"
                )
            try:
                observed_value = value_at_path(parsed, dotted_path)
                observed_length = len(observed_value)
            except (KeyError, TypeError) as exc:
                raise ManifestValidationError(
                    f"cannot evaluate expected length for {dotted_path}"
                ) from exc
            if observed_length != expected_length:
                raise ManifestValidationError(
                    f"{dotted_path} must have length {expected_length}; "
                    f"observed {observed_length}"
                )
        placeholders = find_placeholders(parsed)
        if placeholders:
            preview = ", ".join(
                f"{item.path}={item.value!r}" for item in placeholders[:5]
            )
            raise ManifestValidationError(
                f"unresolved placeholders found ({len(placeholders)}): {preview}"
            )
    except ManifestValidationError as exc:
        _check(
            checks,
            check_id=f"{check_prefix}:content",
            passed=False,
            code="ARTIFACT_CONTENT_INCOMPLETE",
            message=str(exc),
            artifact_id=artifact_id,
            path=target,
        )
        return
    _check(
        checks,
        check_id=f"{check_prefix}:content",
        passed=True,
        code="ARTIFACT_CONTENT_COMPLETE",
        message="required fields, expected values, and placeholder scan passed",
        artifact_id=artifact_id,
        path=target,
    )


def _readiness_contract_error(
    config: Mapping[str, Any], *, required_artifact_ids: Sequence[str]
) -> Optional[str]:
    """Return why a requested G1 READY state lacks a complete freeze contract."""

    contract = config.get("readiness_contract")
    if not isinstance(contract, Mapping):
        return "ready status requires a readiness_contract mapping"
    required_contract_fields = (
        "inventory_scope",
        "all_freeze_artifacts_declared",
        "execution_authorized",
        "freeze_attestation_artifact_id",
    )
    missing = missing_required_fields(contract, required_contract_fields)
    if missing:
        return f"readiness_contract is missing fields: {', '.join(missing)}"
    if contract["inventory_scope"] != "full_g1_freeze":
        return "readiness_contract.inventory_scope must equal 'full_g1_freeze'"
    if contract["all_freeze_artifacts_declared"] is not True:
        return "all_freeze_artifacts_declared must be true"
    if contract["execution_authorized"] is not True:
        return "readiness_contract.execution_authorized must be true"
    attestation_id = contract["freeze_attestation_artifact_id"]
    if not isinstance(attestation_id, str) or not attestation_id.strip():
        return "freeze_attestation_artifact_id must be a non-empty string"
    if attestation_id not in required_artifact_ids:
        return "freeze attestation must be a required, hash-verified artifact"
    for field in ("planned_g1_freeze_artifacts", "planned_incomplete_artifacts"):
        planned = config.get(field, [])
        if not isinstance(planned, list):
            return f"{field} must be a list"
        if planned:
            return f"{field} must be empty before READY can be requested"
    return None


def evaluate_g1_readiness(config_path: Path | str) -> G1ReadinessReport:
    """Aggregate config and artifact checks without ever inferring a false PASS."""

    target = Path(config_path).expanduser().resolve()
    checks: list[ReadinessCheck] = []
    if not target.is_file():
        _check(
            checks,
            check_id="config:exists",
            passed=False,
            code="CONFIG_MISSING",
            message=(
                "G1 configuration is absent; remain in PREPARATION. "
                "Create it from real frozen decisions or pass --config explicitly."
            ),
            path=target,
        )
        return G1ReadinessReport(
            config_path=str(target),
            status=ReadinessStatus.PREPARATION,
            checks=tuple(checks),
        )

    _check(
        checks,
        check_id="config:exists",
        passed=True,
        code="CONFIG_PRESENT",
        message="G1 configuration file exists",
        path=target,
    )
    try:
        config = load_structured_file(target)
        if not isinstance(config, Mapping):
            raise ManifestValidationError("G1 config root must be a mapping")
        require_fields(
            config,
            (
                "schema_version",
                "gate_id",
                "implementation_status",
                "required_artifact_ids",
                "artifacts",
            ),
            context="G1 config",
        )
        if config["gate_id"] != "G1":
            raise ManifestValidationError("gate_id must equal 'G1'")
        schema_version = config["schema_version"]
        if not isinstance(schema_version, str) or not schema_version.startswith("restart-v2.3"):
            raise ManifestValidationError(
                "schema_version must identify restart-v2.3"
            )
        config_placeholders = find_placeholders(config)
        if config_placeholders:
            preview = ", ".join(
                f"{item.path}={item.value!r}" for item in config_placeholders[:5]
            )
            raise ManifestValidationError(
                f"G1 config contains unresolved placeholders: {preview}"
            )
        required_ids = _as_string_tuple(
            config["required_artifact_ids"], field="required_artifact_ids"
        )
        if not required_ids:
            raise ManifestValidationError(
                "required_artifact_ids cannot be empty; empty inventory can never pass G1"
            )
        artifacts = config["artifacts"]
        if not isinstance(artifacts, list) or not artifacts:
            raise ManifestValidationError(
                "artifacts must be a non-empty list; empty inventory can never pass G1"
            )
        artifact_ids = []
        for item in artifacts:
            if not isinstance(item, Mapping):
                raise ManifestValidationError("each artifact specification must be a mapping")
            artifact_ids.append(item.get("artifact_id"))
        if any(not isinstance(item, str) or not item.strip() for item in artifact_ids):
            raise ManifestValidationError("every artifact requires a non-empty artifact_id")
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ManifestValidationError("artifact specifications contain duplicate artifact_id")
        missing_specs = set(required_ids) - set(artifact_ids)
        if missing_specs:
            raise ManifestValidationError(
                f"required artifacts lack specifications: {sorted(missing_specs)}"
            )
        root = _artifact_root(target, config)
    except ManifestValidationError as exc:
        _check(
            checks,
            check_id="config:contract",
            passed=False,
            code="CONFIG_INVALID",
            message=str(exc),
            path=target,
        )
        return G1ReadinessReport(
            config_path=str(target),
            status=ReadinessStatus.NOT_READY,
            checks=tuple(checks),
        )

    _check(
        checks,
        check_id="config:contract",
        passed=True,
        code="CONFIG_VALID",
        message="G1 config inventory and gate contract are structurally valid",
        path=target,
    )
    for item in artifacts:
        _validate_artifact(item, artifact_root=root, checks=checks)

    status_value = config["implementation_status"]
    normalized_status = (
        status_value.strip().lower() if isinstance(status_value, str) else ""
    )
    if normalized_status in _PREPARATION_STATUSES:
        readiness = ReadinessStatus.PREPARATION
        _check(
            checks,
            check_id="config:readiness_intent",
            passed=False,
            code="PREPARATION_STATUS",
            message=(
                "implementation_status remains preparation; a complete artifact set "
                "does not become G1-ready until readiness is explicitly requested"
            ),
            path=target,
        )
    elif normalized_status in _READY_CANDIDATE_STATUSES:
        contract_error = _readiness_contract_error(
            config, required_artifact_ids=required_ids
        )
        _check(
            checks,
            check_id="config:readiness_contract",
            passed=contract_error is None,
            code=(
                "READINESS_CONTRACT_VERIFIED"
                if contract_error is None
                else "READINESS_CONTRACT_INCOMPLETE"
            ),
            message=contract_error or "full G1 freeze contract is present",
            path=target,
        )
        _check(
            checks,
            check_id="config:readiness_intent",
            passed=True,
            code="READINESS_REQUESTED",
            message=f"implementation_status={status_value!r}",
            path=target,
        )
        readiness = (
            ReadinessStatus.READY
            if contract_error is None and all(check.passed for check in checks)
            else ReadinessStatus.NOT_READY
        )
    else:
        readiness = ReadinessStatus.NOT_READY
        _check(
            checks,
            check_id="config:readiness_intent",
            passed=False,
            code="IMPLEMENTATION_STATUS_INVALID",
            message=(
                "implementation_status must be a preparation status or an explicit "
                "ready-for-validation/freeze-candidate status"
            ),
            path=target,
        )

    # The readiness-intent check is appended after artifact checks. Recompute so
    # READY is possible only when every single check, including intent, passes.
    if readiness is ReadinessStatus.READY and any(not check.passed for check in checks):
        readiness = ReadinessStatus.NOT_READY
    return G1ReadinessReport(
        config_path=str(target), status=readiness, checks=tuple(checks)
    )


__all__ = [
    "CANONICALIZATION_VERSION",
    "DEFAULT_G1_CONFIG",
    "G1ReadinessReport",
    "ManifestValidationError",
    "PlaceholderFinding",
    "ReadinessCheck",
    "ReadinessStatus",
    "canonical_data_sha256",
    "canonical_json_bytes",
    "canonical_structured_file_sha256",
    "evaluate_g1_readiness",
    "file_bytes_sha256",
    "find_placeholders",
    "infer_structured_format",
    "load_structured_bytes",
    "load_structured_file",
    "missing_required_fields",
    "require_fields",
    "value_at_path",
    "verify_file_sha256",
]
