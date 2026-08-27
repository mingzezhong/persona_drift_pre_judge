"""Materialize the first post-triage G1 Topic stage packets.

The converter is deliberately mechanical.  It verifies two complete local
reviewer ledgers against the frozen anonymous MMLU packet, forms the non-reject
union (U) and double-reject frame (D), selects the frozen ceiling-ten-percent
audit (A), and copies anonymous source rows into the next packets.  It never
creates a rating, scenario card, suitability score, or final Topic decision.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import yaml

from persona_drift.g1_local_reviewer import (
    LEDGER_SCHEMA_VERSION,
    PRODUCTION_MODE,
)
from persona_drift.g1_topic_screening import (
    DOUBLE_REJECT_AUDIT_NAMESPACE,
    DOUBLE_REJECT_AUDIT_SEED,
    RATER_FORBIDDEN_KEYS,
    RATER_RECORD_SCHEMA_VERSION,
    TRIAGE_LABELS,
    deterministic_double_reject_audit_sample,
)
from persona_drift.g1_topics import canonical_json_bytes


SCHEMA_VERSION = "restart-v2.3-g1-topic-triage-join-v1"
IMPLEMENTATION_STATUS = "TRIAGE_JOIN_MATERIALIZED"
ID_SET_SCHEMA_VERSION = "restart-v2.3-g1-topic-stage-id-set-v1"
REVIEW_CONTRACT_SCHEMA_VERSION = "restart-v2.3-g1-local-review-contract-v1"

MMLU_PACKET = Path("data/reviews/topic_mmlu_triage_input_v2_3.jsonl")
ANTHROPIC_PACKET = Path("data/reviews/topic_anthropic_full_screen_input_v2_3.jsonl")
SCREENING_MANIFEST = Path("data/manifests/topic_screening_packets_v2_3.yaml")
PRIMARY_01_RESULTS = Path("outputs/g1/reviews/topic_mmlu_triage_primary_01_v2_3.jsonl")
PRIMARY_02_RESULTS = Path("outputs/g1/reviews/topic_mmlu_triage_primary_02_v2_3.jsonl")
INITIAL_WRITER_PACKET = Path("data/stages/topic_initial_writer_input_v2_3.jsonl")
REMAINING_DOUBLE_REJECT_PACKET = Path(
    "data/stages/topic_remaining_double_reject_input_v2_3.jsonl"
)
TRIAGE_JOIN_MANIFEST = Path("data/manifests/topic_triage_join_v2_3.yaml")

EXPECTED_MMLU_COUNT = 12_032
EXPECTED_ANTHROPIC_COUNT = 158
_BLIND_ID_RE = re.compile(r"^TOP-[0-9a-f]{24}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MODEL_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_LEDGER_TOP_LEVEL_FIELDS = frozenset(
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
        "response",
        "response_canonical_sha256",
        "error",
        "previous_record_sha256",
        "record_sha256",
    }
)
_STAGE_PACKET_FORBIDDEN_KEYS = frozenset(
    {
        *RATER_FORBIDDEN_KEYS,
        "rating",
        "rationale",
        "triage_label",
        "triage_labels",
        "rater_slot_id",
        "reviewer_slot_id",
        "model_id",
        "model_revision",
        "base_model_family",
        "audit_selected",
        "stage_reason",
        "selection_reason",
        "scenario_card",
        "scores",
    }
)


class TopicStageError(ValueError):
    """Raised when a post-triage transition is incomplete or unauditable."""


@dataclass(frozen=True)
class _Packet:
    path: Path
    raw: bytes
    rows: tuple[Mapping[str, Any], ...]
    raw_rows: tuple[bytes, ...]
    by_id: Mapping[str, Mapping[str, Any]]
    line_by_id: Mapping[str, int]
    raw_sha256_by_id: Mapping[str, str]
    canonical_sha256_by_id: Mapping[str, str]

    @property
    def file_sha256(self) -> str:
        return _sha256(self.raw)


@dataclass(frozen=True)
class _Ledger:
    path: Path
    raw: bytes
    slot_id: str
    reviewer: Mapping[str, str]
    review_contract_sha256: str
    chain_head_sha256: str
    record_count: int
    responses: Mapping[str, Mapping[str, Any]]

    @property
    def file_sha256(self) -> str:
        return _sha256(self.raw)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_sha256(value: Any, context: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise TopicStageError(f"{context} must be 64 lowercase hexadecimal characters")
    return value


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TopicStageError(f"{context} must be a mapping")
    return value


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise TopicStageError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise TopicStageError(f"non-finite JSON number is forbidden: {value}")


def _read_regular_file(path: Path, label: str) -> bytes:
    if path.is_symlink():
        raise TopicStageError(f"{label} must not be a symbolic link: {path}")
    if not path.is_file():
        raise TopicStageError(f"{label} is missing or not a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise TopicStageError(f"cannot read {label} {path}: {exc}") from exc


def _strict_jsonl(
    path: Path,
    label: str,
) -> tuple[bytes, tuple[Mapping[str, Any], ...], tuple[bytes, ...]]:
    raw = _read_regular_file(path, label)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise TopicStageError(f"{label} must not contain a UTF-8 BOM")
    if not raw or not raw.endswith(b"\n"):
        raise TopicStageError(f"{label} must be non-empty canonical JSONL ending in LF")
    raw_rows = tuple(raw[:-1].split(b"\n"))
    if any(not row for row in raw_rows):
        raise TopicStageError(f"{label} must not contain blank lines")
    values: list[Mapping[str, Any]] = []
    for line_number, row in enumerate(raw_rows, start=1):
        try:
            text = row.decode("utf-8")
            value = json.loads(
                text,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except TopicStageError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TopicStageError(
                f"{label} line {line_number} is not strict UTF-8 JSON: {exc}"
            ) from exc
        value = _require_mapping(value, f"{label} line {line_number}")
        if canonical_json_bytes(value) != row:
            raise TopicStageError(f"{label} line {line_number} is not canonical JSON")
        values.append(value)
    return raw, tuple(values), raw_rows


def _assert_anonymous(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        forbidden = _STAGE_PACKET_FORBIDDEN_KEYS.intersection(value)
        if forbidden:
            raise TopicStageError(
                f"rater-facing packet has forbidden key(s) at {path}: {sorted(forbidden)}"
            )
        for key, child in value.items():
            _assert_anonymous(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_anonymous(child, f"{path}[{index}]")


def _load_packet(path: Path, label: str, expected_count: int | None) -> _Packet:
    raw, rows, raw_rows = _strict_jsonl(path, label)
    if expected_count is not None and len(rows) != expected_count:
        raise TopicStageError(
            f"{label} row count differs: {len(rows)} != {expected_count}"
        )
    by_id: dict[str, Mapping[str, Any]] = {}
    line_by_id: dict[str, int] = {}
    raw_hashes: dict[str, str] = {}
    canonical_hashes: dict[str, str] = {}
    for line_number, (row, raw_row) in enumerate(zip(rows, raw_rows, strict=True), start=1):
        if set(row) != {"schema_version", "blind_item_id", "content"}:
            raise TopicStageError(f"{label} line {line_number} has a non-exact row schema")
        if row["schema_version"] != RATER_RECORD_SCHEMA_VERSION:
            raise TopicStageError(f"{label} line {line_number} has the wrong schema_version")
        blind_id = row["blind_item_id"]
        if not isinstance(blind_id, str) or not _BLIND_ID_RE.fullmatch(blind_id):
            raise TopicStageError(f"{label} line {line_number} has an invalid blind_item_id")
        _require_mapping(row["content"], f"{label} line {line_number}.content")
        _assert_anonymous(row)
        if blind_id in by_id:
            raise TopicStageError(f"{label} contains duplicate blind_item_id {blind_id}")
        by_id[blind_id] = row
        line_by_id[blind_id] = line_number
        raw_hashes[blind_id] = _sha256(raw_row)
        canonical_hashes[blind_id] = _sha256(canonical_json_bytes(row))
    if tuple(by_id) != tuple(sorted(by_id)):
        raise TopicStageError(f"{label} rows must be sorted by blind_item_id")
    return _Packet(
        path=path,
        raw=raw,
        rows=rows,
        raw_rows=raw_rows,
        by_id=by_id,
        line_by_id=line_by_id,
        raw_sha256_by_id=raw_hashes,
        canonical_sha256_by_id=canonical_hashes,
    )


def _identity_projection(value: Mapping[str, Any], context: str) -> dict[str, str]:
    projected: dict[str, str] = {}
    for field in (
        "reviewer_slot_id",
        "reviewer_role",
        "model_id",
        "model_revision",
        "base_model_family",
    ):
        item = value.get(field)
        if not isinstance(item, str) or not item.strip():
            raise TopicStageError(f"{context}.{field} must be a non-empty string")
        projected[field] = item
    return projected


def _load_primary_ledger(path: Path, slot_id: str, packet: _Packet) -> _Ledger:
    raw, records, _ = _strict_jsonl(path, f"{slot_id} triage ledger")
    previous: str | None = None
    attempt_ids: set[str] = set()
    accepted: dict[str, Mapping[str, Any]] = {}
    contract_hashes: set[str] = set()
    identities: set[tuple[str, ...]] = set()

    for line_number, record in enumerate(records, start=1):
        context = f"{slot_id} triage ledger line {line_number}"
        if set(record) != _LEDGER_TOP_LEVEL_FIELDS:
            raise TopicStageError(f"{context} does not match the runner ledger schema")
        if record["schema_version"] != LEDGER_SCHEMA_VERSION:
            raise TopicStageError(f"{context} has the wrong ledger schema_version")
        if record["mode"] != PRODUCTION_MODE:
            raise TopicStageError(f"{context} is not a PRODUCTION review record")
        attempt_id = record["attempt_id"]
        if not isinstance(attempt_id, str) or not attempt_id or attempt_id in attempt_ids:
            raise TopicStageError(f"{context} has an invalid or duplicate attempt_id")
        attempt_ids.add(attempt_id)

        observed_hash = _require_sha256(record["record_sha256"], f"{context}.record_sha256")
        body = dict(record)
        del body["record_sha256"]
        if observed_hash != _sha256(canonical_json_bytes(body)):
            raise TopicStageError(f"{context} record_sha256 mismatch")
        if record["previous_record_sha256"] != previous:
            raise TopicStageError(f"{context} hash-chain predecessor mismatch")
        previous = observed_hash

        contract = _require_mapping(record["review_contract"], f"{context}.review_contract")
        contract_hash = _require_sha256(
            record["review_contract_sha256"], f"{context}.review_contract_sha256"
        )
        if contract_hash != _sha256(canonical_json_bytes(contract)):
            raise TopicStageError(f"{context} review-contract hash mismatch")
        if contract.get("schema_version") != REVIEW_CONTRACT_SCHEMA_VERSION:
            raise TopicStageError(f"{context} review contract has the wrong schema_version")
        if contract.get("mode") != PRODUCTION_MODE:
            raise TopicStageError(f"{context} review contract is not PRODUCTION")
        if contract.get("packet_file_sha256") != packet.file_sha256:
            raise TopicStageError(f"{context} review contract binds a different packet")
        contract_hashes.add(contract_hash)

        reviewer = _identity_projection(
            _require_mapping(record["reviewer"], f"{context}.reviewer"),
            f"{context}.reviewer",
        )
        contract_reviewer = _identity_projection(
            _require_mapping(contract.get("reviewer"), f"{context}.review_contract.reviewer"),
            f"{context}.review_contract.reviewer",
        )
        if reviewer != contract_reviewer:
            raise TopicStageError(f"{context} reviewer differs from its review contract")
        if reviewer["reviewer_slot_id"] != slot_id:
            raise TopicStageError(f"{context} came from the wrong reviewer slot")
        if reviewer["reviewer_role"] != "independent_primary_rater":
            raise TopicStageError(f"{context} came from an unauthorized reviewer role")
        if not _MODEL_REVISION_RE.fullmatch(reviewer["model_revision"]):
            raise TopicStageError(f"{context} model revision is not a full commit")
        identities.add(tuple(reviewer[field] for field in reviewer))

        packet_binding = _require_mapping(record["packet"], f"{context}.packet")
        if packet_binding.get("file_sha256") != packet.file_sha256:
            raise TopicStageError(f"{context} packet binding differs from source bytes")
        item = _require_mapping(record["item"], f"{context}.item")
        if item.get("task_id") != "topic_triage" or item.get("id_field") != "blind_item_id":
            raise TopicStageError(f"{context} is not a topic_triage blind-item attempt")
        blind_id = item.get("item_id")
        if blind_id not in packet.by_id:
            raise TopicStageError(f"{context} references an item outside the MMLU packet")
        if item.get("line_number") != packet.line_by_id[blind_id]:
            raise TopicStageError(f"{context} packet line-number binding mismatch")
        if item.get("row_sha256") != packet.raw_sha256_by_id[blind_id]:
            raise TopicStageError(f"{context} packet row_sha256 mismatch")
        if item.get("canonical_sha256") != packet.canonical_sha256_by_id[blind_id]:
            raise TopicStageError(f"{context} packet canonical_sha256 mismatch")

        status = record["status"]
        if status == "accepted":
            response = _require_mapping(record["response"], f"{context}.response")
            if set(response) != {"blind_item_id", "rating", "rationale"}:
                raise TopicStageError(f"{context} accepted response has a non-exact schema")
            if response["blind_item_id"] != blind_id:
                raise TopicStageError(f"{context} response/item blind ID mismatch")
            if response["rating"] not in TRIAGE_LABELS:
                raise TopicStageError(f"{context} has an invalid triage label")
            if not isinstance(response["rationale"], str) or not response["rationale"].strip():
                raise TopicStageError(f"{context} has an empty triage rationale")
            expected_response_hash = _sha256(canonical_json_bytes(response))
            if record["response_canonical_sha256"] != expected_response_hash:
                raise TopicStageError(f"{context} response hash mismatch")
            raw_output = record["raw_output"]
            if not isinstance(raw_output, str) or record["raw_output_sha256"] != _sha256(
                raw_output.encode("utf-8")
            ):
                raise TopicStageError(f"{context} accepted raw-output hash mismatch")
            if record["error"] is not None:
                raise TopicStageError(f"{context} accepted attempt unexpectedly has an error")
            if blind_id in accepted:
                raise TopicStageError(f"{slot_id} ledger has duplicate accepted item {blind_id}")
            accepted[blind_id] = response
        elif status in {"rejected_invalid_output", "generation_error"}:
            if record["response"] is not None or record["response_canonical_sha256"] is not None:
                raise TopicStageError(f"{context} failed attempt contains an accepted response")
        else:
            raise TopicStageError(f"{context} has unsupported attempt status {status!r}")

    if len(contract_hashes) != 1:
        raise TopicStageError(f"{slot_id} ledger must contain exactly one review contract")
    if len(identities) != 1:
        raise TopicStageError(f"{slot_id} ledger must contain exactly one reviewer identity")
    expected_ids = set(packet.by_id)
    observed_ids = set(accepted)
    if observed_ids != expected_ids:
        missing = len(expected_ids - observed_ids)
        extra = len(observed_ids - expected_ids)
        raise TopicStageError(
            f"{slot_id} accepted-response join is incomplete: missing={missing}, extra={extra}"
        )
    reviewer_fields = (
        "reviewer_slot_id",
        "reviewer_role",
        "model_id",
        "model_revision",
        "base_model_family",
    )
    identity_tuple = next(iter(identities))
    reviewer = dict(zip(reviewer_fields, identity_tuple, strict=True))
    return _Ledger(
        path=path,
        raw=raw,
        slot_id=slot_id,
        reviewer=reviewer,
        review_contract_sha256=next(iter(contract_hashes)),
        chain_head_sha256=previous or "",
        record_count=len(records),
        responses=accepted,
    )


def _id_set_sha256(ids: Sequence[str]) -> str:
    return _sha256(
        canonical_json_bytes(
            {
                "schema_version": ID_SET_SCHEMA_VERSION,
                "blind_item_ids": sorted(ids),
            }
        )
    )


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def _relative_or_absolute(path: Path, repository_root: Path) -> str:
    absolute = path.absolute()
    try:
        return absolute.relative_to(repository_root).as_posix()
    except ValueError:
        return absolute.as_posix()


def _artifact(
    path: Path,
    payload: bytes,
    rows: Sequence[Mapping[str, Any]],
    repository_root: Path,
    role: str,
) -> dict[str, Any]:
    ids = [str(row["blind_item_id"]) for row in rows]
    return {
        "path": _relative_or_absolute(path, repository_root),
        "role": role,
        "audience": "RATER_FACING_ANONYMOUS",
        "format": "canonical-jsonl-utf8-lf",
        "row_count": len(rows),
        "bytes": len(payload),
        "file_sha256": _sha256(payload),
        "blind_item_ids_sha256": _id_set_sha256(ids),
        "contains_triage_ratings_or_rationales": False,
        "contains_scenario_cards": False,
    }


def _verify_screening_manifest(
    path: Path,
    mmlu_packet: _Packet,
    anthropic_packet: _Packet,
) -> dict[str, Any]:
    raw = _read_regular_file(path, "Topic screening manifest")
    try:
        manifest = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise TopicStageError(f"invalid Topic screening manifest: {exc}") from exc
    manifest = _require_mapping(manifest, "Topic screening manifest")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise TopicStageError("Topic screening manifest lacks artifacts")
    by_path = {
        item.get("path"): item
        for item in artifacts
        if isinstance(item, Mapping) and isinstance(item.get("path"), str)
    }
    for logical_path, packet in (
        (MMLU_PACKET.as_posix(), mmlu_packet),
        (ANTHROPIC_PACKET.as_posix(), anthropic_packet),
    ):
        artifact = by_path.get(logical_path)
        if artifact is None:
            raise TopicStageError(f"screening manifest lacks {logical_path}")
        if (
            artifact.get("sha256") != packet.file_sha256
            or artifact.get("bytes") != len(packet.raw)
            or artifact.get("row_count") != len(packet.rows)
        ):
            raise TopicStageError(f"screening-manifest binding mismatch for {logical_path}")
    return {
        "path": path.as_posix(),
        "bytes": len(raw),
        "file_sha256": _sha256(raw),
    }


def _resolve(repository_root: Path, supplied: Path | None, default: Path) -> Path:
    path = default if supplied is None else Path(supplied)
    return path if path.is_absolute() else repository_root / path


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise TopicStageError(f"output path must not be a symbolic link: {path}")
    temporary = path.with_name(path.name + ".part")
    if temporary.is_symlink():
        raise TopicStageError(f"temporary output path must not be a symbolic link: {temporary}")
    temporary.write_bytes(payload)
    temporary.replace(path)


def build_topic_stage_packets(
    repository_root: Path,
    *,
    primary_01_results_path: Path | None = None,
    primary_02_results_path: Path | None = None,
    mmlu_packet_path: Path | None = None,
    anthropic_packet_path: Path | None = None,
    screening_manifest_path: Path | None = SCREENING_MANIFEST,
    initial_writer_output_path: Path | None = None,
    remaining_double_reject_output_path: Path | None = None,
    join_manifest_output_path: Path | None = None,
    expected_mmlu_count: int | None = EXPECTED_MMLU_COUNT,
    expected_anthropic_count: int | None = EXPECTED_ANTHROPIC_COUNT,
    write_outputs: bool = True,
) -> dict[str, Any]:
    """Strictly join two primary ledgers and materialize anonymous next inputs."""

    repository_root = repository_root.resolve()
    for label, count in (
        ("expected_mmlu_count", expected_mmlu_count),
        ("expected_anthropic_count", expected_anthropic_count),
    ):
        if count is not None and (
            isinstance(count, bool) or not isinstance(count, int) or count < 0
        ):
            raise TopicStageError(f"{label} must be a non-negative integer or None")
    mmlu_path = _resolve(repository_root, mmlu_packet_path, MMLU_PACKET)
    anthropic_path = _resolve(repository_root, anthropic_packet_path, ANTHROPIC_PACKET)
    primary_01_path = _resolve(repository_root, primary_01_results_path, PRIMARY_01_RESULTS)
    primary_02_path = _resolve(repository_root, primary_02_results_path, PRIMARY_02_RESULTS)
    initial_path = _resolve(repository_root, initial_writer_output_path, INITIAL_WRITER_PACKET)
    remaining_path = _resolve(
        repository_root,
        remaining_double_reject_output_path,
        REMAINING_DOUBLE_REJECT_PACKET,
    )
    manifest_path = _resolve(repository_root, join_manifest_output_path, TRIAGE_JOIN_MANIFEST)
    resolved_screening_path = (
        None
        if screening_manifest_path is None
        else _resolve(repository_root, screening_manifest_path, SCREENING_MANIFEST)
    )
    output_paths = (initial_path.absolute(), remaining_path.absolute(), manifest_path.absolute())
    if len(set(output_paths)) != len(output_paths):
        raise TopicStageError("stage output paths must be pairwise distinct")
    protected_inputs = {
        mmlu_path.absolute(),
        anthropic_path.absolute(),
        primary_01_path.absolute(),
        primary_02_path.absolute(),
    }
    if resolved_screening_path is not None:
        protected_inputs.add(resolved_screening_path.absolute())
    if protected_inputs.intersection(output_paths):
        raise TopicStageError("stage outputs must not overwrite any bound input")

    mmlu = _load_packet(mmlu_path, "MMLU triage packet", expected_mmlu_count)
    anthropic = _load_packet(
        anthropic_path,
        "Anthropic full-screen packet",
        expected_anthropic_count,
    )
    overlap = set(mmlu.by_id).intersection(anthropic.by_id)
    if overlap:
        raise TopicStageError("MMLU and Anthropic blind-item universes overlap")

    screening_binding: dict[str, Any] | None = None
    if resolved_screening_path is not None:
        screening_binding = _verify_screening_manifest(
            resolved_screening_path, mmlu, anthropic
        )
        screening_binding["path"] = _relative_or_absolute(
            resolved_screening_path, repository_root
        )

    primary_01 = _load_primary_ledger(primary_01_path, "primary_01", mmlu)
    primary_02 = _load_primary_ledger(primary_02_path, "primary_02", mmlu)
    if primary_01.reviewer["base_model_family"] == primary_02.reviewer["base_model_family"]:
        raise TopicStageError("primary_01 and primary_02 must use distinct base-model families")
    if primary_01.reviewer["model_id"] == primary_02.reviewer["model_id"]:
        raise TopicStageError("primary_01 and primary_02 must use distinct models")

    u_ids: list[str] = []
    d_ids: list[str] = []
    for blind_id in sorted(mmlu.by_id):
        labels = (
            primary_01.responses[blind_id]["rating"],
            primary_02.responses[blind_id]["rating"],
        )
        if labels == ("reject", "reject"):
            d_ids.append(blind_id)
        else:
            u_ids.append(blind_id)
    if set(u_ids).intersection(d_ids) or set(u_ids).union(d_ids) != set(mmlu.by_id):
        raise TopicStageError("U/D classification is not an exact MMLU partition")

    audit_ids = list(deterministic_double_reject_audit_sample(d_ids))
    audit_set = set(audit_ids)
    remaining_ids = sorted(set(d_ids) - audit_set)
    initial_ids = sorted(set(u_ids).union(audit_set).union(anthropic.by_id))
    initial_rows = tuple(
        (mmlu.by_id.get(blind_id) or anthropic.by_id[blind_id])
        for blind_id in initial_ids
    )
    remaining_rows = tuple(mmlu.by_id[blind_id] for blind_id in remaining_ids)
    for row in (*initial_rows, *remaining_rows):
        _assert_anonymous(row)
    if set(initial_ids).intersection(remaining_ids):
        raise TopicStageError("initial and remaining stage packets overlap")
    if set(initial_ids).union(remaining_ids) != set(mmlu.by_id).union(anthropic.by_id):
        raise TopicStageError("stage packets do not preserve the complete source universe")

    initial_payload = _jsonl_bytes(initial_rows)
    remaining_payload = _jsonl_bytes(remaining_rows)
    output_artifacts = [
        _artifact(
            initial_path,
            initial_payload,
            initial_rows,
            repository_root,
            "INITIAL_SCENARIO_WRITER_INPUT",
        ),
        _artifact(
            remaining_path,
            remaining_payload,
            remaining_rows,
            repository_root,
            "CONTINGENT_PRIMARY_03_TRIAGE_INPUT",
        ),
    ]

    def ledger_provenance(ledger: _Ledger) -> dict[str, Any]:
        responses = [ledger.responses[item] for item in sorted(ledger.responses)]
        return {
            "path": _relative_or_absolute(ledger.path, repository_root),
            "file_sha256": ledger.file_sha256,
            "bytes": len(ledger.raw),
            "record_count": ledger.record_count,
            "accepted_response_count": len(responses),
            "accepted_responses_canonical_sha256": _sha256(canonical_json_bytes(responses)),
            "review_contract_sha256": ledger.review_contract_sha256,
            "chain_head_record_sha256": ledger.chain_head_sha256,
            "reviewer": dict(ledger.reviewer),
        }

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "implementation_status": IMPLEMENTATION_STATUS,
        "audience": "ADMIN_ONLY_DO_NOT_SEND_TO_RATERS",
        "g1_ready": False,
        "selection_outcome_blind": True,
        "target_model_execution_authorized": False,
        "scenario_writer_execution_authorized_by_this_manifest": False,
        "primary_03_execution_authorized_by_this_manifest": False,
        "triage_ratings_ingested": True,
        "contains_fabricated_ratings": False,
        "contains_rating_values_or_rationales": False,
        "scenario_cards_generated": False,
        "suitability_ratings_generated": False,
        "final_topic_selection_performed": False,
        "input_bindings": {
            "screening_manifest": screening_binding,
            "mmlu_anonymous_packet": {
                "path": _relative_or_absolute(mmlu.path, repository_root),
                "row_count": len(mmlu.rows),
                "bytes": len(mmlu.raw),
                "file_sha256": mmlu.file_sha256,
                "blind_item_ids_sha256": _id_set_sha256(sorted(mmlu.by_id)),
            },
            "anthropic_anonymous_packet": {
                "path": _relative_or_absolute(anthropic.path, repository_root),
                "row_count": len(anthropic.rows),
                "bytes": len(anthropic.raw),
                "file_sha256": anthropic.file_sha256,
                "blind_item_ids_sha256": _id_set_sha256(sorted(anthropic.by_id)),
            },
            "primary_triage_ledgers": [
                ledger_provenance(primary_01),
                ledger_provenance(primary_02),
            ],
        },
        "triage_sets": {
            "U": {
                "definition": "either_primary_label_is_advance_or_uncertain",
                "count": len(u_ids),
                "blind_item_ids_sha256": _id_set_sha256(u_ids),
            },
            "D": {
                "definition": "both_primary_labels_are_reject",
                "count": len(d_ids),
                "blind_item_ids_sha256": _id_set_sha256(d_ids),
            },
            "A": {
                "definition": "frozen_ceiling_ten_percent_audit_of_D",
                "count": len(audit_ids),
                "blind_item_ids_sha256": _id_set_sha256(audit_ids),
            },
            "R": {
                "definition": "D_minus_A_remaining_unaudited_double_rejects",
                "count": len(remaining_ids),
                "blind_item_ids_sha256": _id_set_sha256(remaining_ids),
            },
        },
        "double_reject_audit": {
            "sampling_algorithm_id": "sha256-rank-without-replacement-v1",
            "namespace": DOUBLE_REJECT_AUDIT_NAMESPACE,
            "seed": DOUBLE_REJECT_AUDIT_SEED,
            "fraction": 0.10,
            "sample_size_rule": "ceiling_fraction_times_double_reject_count",
            "auditor_blind_to_original_triage": True,
        },
        "stage_transitions": {
            "initial_writer_input": "U union A union all_Anthropic_candidates",
            "remaining_double_reject_input": "D minus A",
            "remaining_packet_use_is_contingent_on_audited_rescue_rate_strictly_above_0.02": True,
            "packet_rows_are_unmodified_anonymous_source_rows": True,
        },
        "output_artifacts": output_artifacts,
    }
    rendered_manifest = yaml.safe_dump(
        manifest,
        allow_unicode=True,
        sort_keys=False,
        width=100,
    ).encode("utf-8")
    if write_outputs:
        _atomic_write(initial_path, initial_payload)
        _atomic_write(remaining_path, remaining_payload)
        _atomic_write(manifest_path, rendered_manifest)
    return manifest
