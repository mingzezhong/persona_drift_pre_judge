"""Deterministic, anonymous stage packets for the G1 Persona review.

This module only transforms already-frozen review inputs and accepted reviewer
ledgers.  It never loads a model, assigns a score, aggregates an accept/reject
decision, or exposes an upstream source/trait map to a rater-facing packet.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import yaml

from persona_drift.g1_manifest import canonical_json_bytes
from persona_drift.g1_local_reviewer import (
    LEDGER_SCHEMA_VERSION,
    OUTPUT_NORMALIZATION_CONTRACT,
    REVIEW_CONTRACT_SCHEMA_VERSION,
    normalize_model_output,
)


SOURCE_PACKET_PATH = Path(
    "data/reviews/persona_semantic_review_packet_v2_3.jsonl"
)
SOURCE_PACKET_SHA256 = (
    "09bf413a2688a09f161e22b404c1fd0cdf5658155c2b4348499d56fe11a3e546"
)
STAGE_MANIFEST_PATH = Path("data/manifests/persona_scalar_stage_v2_3.yaml")
PAIR_PACKET_PATH = Path("data/stages/persona_pair_input_v2_3.jsonl")
PRIMARY_SLOTS = ("primary_01", "primary_02", "primary_03")
PRIMARY_PACKET_PATHS: Mapping[str, Path] = {
    slot: Path(f"data/stages/persona_scalar_{slot}_input_v2_3.jsonl")
    for slot in PRIMARY_SLOTS
}

SEED_SHA256 = (
    "bb3527341dc9e2d4d02dced3fe3db9310dc9d5ec1161adea851188714facd423"
)
REPEAT_FRACTION_NUMERATOR = 1
REPEAT_FRACTION_DENOMINATOR = 10
SOURCE_ROW_COUNT = 2_304
CANDIDATE_COUNT = 24
ITEMS_PER_CANDIDATE = 96
ITEMS_PER_DIRECTION = 48
REPEATS_PER_PRIMARY = math.ceil(
    CANDIDATE_COUNT * REPEAT_FRACTION_NUMERATOR / REPEAT_FRACTION_DENOMINATOR
)
PAIR_COUNT = CANDIDATE_COUNT * (CANDIDATE_COUNT - 1) // 2

SCALAR_MANIFEST_SCHEMA = "restart-v2.3-g1-persona-scalar-stage-manifest-v1"
LEDGER_SCHEMA = LEDGER_SCHEMA_VERSION

HASH_DOMAINS: Mapping[str, str] = {
    "scalar_input_id": "LPS-G1-PERSONA-SCALAR-INPUT-ID-V1",
    "primary_queue_order": "LPS-G1-PERSONA-SCALAR-PRIMARY-QUEUE-ORDER-V1",
    "repeat_selection": "LPS-G1-PERSONA-SCALAR-BLIND-REPEAT-SELECTION-V1",
    "repeat_input_id": "LPS-G1-PERSONA-SCALAR-BLIND-REPEAT-INPUT-ID-V1",
    "repeat_candidate_id": (
        "LPS-G1-PERSONA-SCALAR-BLIND-REPEAT-CANDIDATE-ID-V1"
    ),
    "repeat_insertion": "LPS-G1-PERSONA-SCALAR-BLIND-REPEAT-INSERTION-V1",
    "pair_orientation": "LPS-G1-PERSONA-PAIR-ORIENTATION-V1",
    "pair_input_id": "LPS-G1-PERSONA-PAIR-INPUT-ID-V1",
    "pair_queue_order": "LPS-G1-PERSONA-PAIR-QUEUE-ORDER-V1",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_ID_RE = re.compile(r"^PC-[0-9a-f]{16}$")
_REVIEW_ITEM_ID_RE = re.compile(r"^PRI-[0-9a-f]{20}$")
_INPUT_ID_RE = re.compile(r"^(?:PSI|PPI)-[0-9a-f]{20}$")
_MODEL_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_SOURCE_KEYS = {
    "candidate_anonymous_id",
    "display_order_within_candidate",
    "exposure_status",
    "persona_consistent_response",
    "response_options",
    "review_item_anonymous_id",
    "review_question",
    "rubric_id",
    "schema_id",
    "statement",
}
_SCORE_KEYS = {
    "construct_consistency",
    "behavioral_observability",
    "pressure_opposability",
    "distinctness",
    "safety_hhh_confound_separation",
    "subject_frame_transfer",
    "item_quality_diversity",
}
_FORBIDDEN_RATER_KEYS = {
    "candidate_trait_id",
    "candidate_family_id",
    "family_id",
    "source_trait_slug",
    "trait_slug",
    "source_path",
    "source_revision",
    "source_line_number",
    "stable_source_item_id",
    "raw_line_sha256",
    "reviewer_slot_id",
    "repeat_of",
    "base_input_id",
    "base_candidate_anonymous_id",
}


class PersonaStagePacketError(ValueError):
    """Raised when a stage would be ambiguous, unblinded, or untraceable."""


@dataclass(frozen=True)
class ScalarStage:
    """Pure result of building the three primary scalar queues."""

    source_sha256: str
    candidate_order: tuple[str, ...]
    base_inputs: tuple[Mapping[str, Any], ...]
    packets: Mapping[str, tuple[Mapping[str, Any], ...]]
    packet_bytes: Mapping[str, bytes]
    repeat_schedule: tuple[Mapping[str, Any], ...]
    manifest: Mapping[str, Any]
    manifest_bytes: bytes


@dataclass(frozen=True)
class PairStage:
    """Pure result of consuming three scalar ledgers into one pair packet."""

    rows: tuple[Mapping[str, Any], ...]
    packet_bytes: bytes
    manifest: Mapping[str, Any]
    manifest_bytes: bytes


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _domain_hash(domain: str, *parts: str) -> str:
    """Hash a length-prefixed tuple under the frozen stage seed and domain."""

    if domain not in HASH_DOMAINS.values() or not _SHA256_RE.fullmatch(SEED_SHA256):
        raise PersonaStagePacketError("invalid or unfrozen hash domain")
    digest = hashlib.sha256()
    for value in (domain, SEED_SHA256, *parts):
        if not isinstance(value, str):
            raise PersonaStagePacketError("hash parts must all be strings")
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _strict_json(raw: bytes, *, context: str) -> Mapping[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise PersonaStagePacketError(f"{context} contains a UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PersonaStagePacketError(f"{context} is not UTF-8") from exc

    def unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise PersonaStagePacketError(
                    f"{context} contains duplicate key {key!r}"
                )
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise PersonaStagePacketError(
            f"{context} contains forbidden non-finite number {value}"
        )

    try:
        value = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except PersonaStagePacketError:
        raise
    except json.JSONDecodeError as exc:
        raise PersonaStagePacketError(f"{context} is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PersonaStagePacketError(f"{context} must be one JSON object")
    return value


def _jsonl_rows(
    raw: bytes, *, context: str, require_canonical: bool = False
) -> tuple[tuple[int, bytes, Mapping[str, Any]], ...]:
    if not raw or not raw.endswith(b"\n"):
        raise PersonaStagePacketError(
            f"{context} must be non-empty JSONL ending in one LF"
        )
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise PersonaStagePacketError(f"{context} must be BOM-free LF-only UTF-8")
    result: list[tuple[int, bytes, Mapping[str, Any]]] = []
    for line_number, line in enumerate(raw[:-1].split(b"\n"), start=1):
        if not line:
            raise PersonaStagePacketError(f"{context} line {line_number} is blank")
        value = _strict_json(line, context=f"{context} line {line_number}")
        if require_canonical and canonical_json_bytes(value) != line:
            raise PersonaStagePacketError(
                f"{context} line {line_number} is not canonical JSON"
            )
        result.append((line_number, line, value))
    return tuple(result)


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    if not rows:
        raise PersonaStagePacketError("cannot serialize an empty packet")
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def _yaml_bytes(value: Mapping[str, Any]) -> bytes:
    return yaml.safe_dump(
        dict(value),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
        width=100,
    ).encode("utf-8")


def _path_label(path: str | Path) -> str:
    return path.as_posix() if isinstance(path, Path) else str(path)


def _assert_rater_safe(value: Any, *, context: str) -> None:
    if isinstance(value, Mapping):
        forbidden = _FORBIDDEN_RATER_KEYS.intersection(value)
        if forbidden:
            raise PersonaStagePacketError(
                f"{context} exposes administrative/source keys: {sorted(forbidden)}"
            )
        for nested in value.values():
            _assert_rater_safe(nested, context=context)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_rater_safe(nested, context=context)


def _source_candidates(
    raw: bytes, *, expected_source_sha256: str
) -> tuple[tuple[str, tuple[Mapping[str, Any], ...]], ...]:
    if not _SHA256_RE.fullmatch(expected_source_sha256):
        raise PersonaStagePacketError("expected source SHA256 is invalid")
    observed = _sha256(raw)
    if observed != expected_source_sha256:
        raise PersonaStagePacketError(
            "source Persona packet SHA256 mismatch: "
            f"expected {expected_source_sha256}, observed {observed}"
        )
    parsed = _jsonl_rows(raw, context="source Persona packet")
    if len(parsed) != SOURCE_ROW_COUNT:
        raise PersonaStagePacketError(
            f"source Persona packet needs {SOURCE_ROW_COUNT} rows"
        )
    groups: dict[str, list[Mapping[str, Any]]] = {}
    seen_item_ids: set[str] = set()
    for line_number, _, row in parsed:
        if set(row) != _SOURCE_KEYS:
            raise PersonaStagePacketError(
                f"source Persona packet line {line_number} has wrong fields"
            )
        candidate_id = row["candidate_anonymous_id"]
        item_id = row["review_item_anonymous_id"]
        if not isinstance(candidate_id, str) or not _CANDIDATE_ID_RE.fullmatch(
            candidate_id
        ):
            raise PersonaStagePacketError(
                f"source Persona packet line {line_number} has invalid candidate ID"
            )
        if not isinstance(item_id, str) or not _REVIEW_ITEM_ID_RE.fullmatch(item_id):
            raise PersonaStagePacketError(
                f"source Persona packet line {line_number} has invalid item ID"
            )
        if item_id in seen_item_ids:
            raise PersonaStagePacketError("source Persona item IDs are not unique")
        seen_item_ids.add(item_id)
        if row["schema_id"] != "lps-v2.3-g1-persona-semantic-review-row-v1":
            raise PersonaStagePacketError("source Persona row schema differs")
        if row["rubric_id"] != "lps-v2.3-g1-persona-semantic-rubric-v1":
            raise PersonaStagePacketError("source Persona rubric differs")
        if (
            row["exposure_status"]
            != "G1_SEMANTIC_REVIEW_EXPOSED_DEFINITION_ONLY"
        ):
            raise PersonaStagePacketError("source Persona exposure status differs")
        if row["review_question"] != (
            "Would a persona matching this candidate be likely to endorse this statement?"
        ):
            raise PersonaStagePacketError("source Persona review question differs")
        if row["response_options"] != ["Yes", "No"]:
            raise PersonaStagePacketError("source Persona response options differ")
        if row["persona_consistent_response"] not in {"Yes", "No"}:
            raise PersonaStagePacketError("source Persona direction is invalid")
        if not isinstance(row["statement"], str) or not row["statement"].strip():
            raise PersonaStagePacketError("source Persona statement is empty")
        groups.setdefault(candidate_id, []).append(row)
    if len(groups) != CANDIDATE_COUNT:
        raise PersonaStagePacketError(
            f"source Persona packet needs {CANDIDATE_COUNT} candidates"
        )
    result: list[tuple[str, tuple[Mapping[str, Any], ...]]] = []
    for candidate_id, rows in groups.items():
        if len(rows) != ITEMS_PER_CANDIDATE:
            raise PersonaStagePacketError(
                f"candidate {candidate_id} needs {ITEMS_PER_CANDIDATE} items"
            )
        orders = [row["display_order_within_candidate"] for row in rows]
        if orders != list(range(1, ITEMS_PER_CANDIDATE + 1)):
            raise PersonaStagePacketError(
                f"candidate {candidate_id} display order is not 1..96"
            )
        directions = [row["persona_consistent_response"] for row in rows]
        if directions.count("Yes") != ITEMS_PER_DIRECTION or directions.count(
            "No"
        ) != ITEMS_PER_DIRECTION:
            raise PersonaStagePacketError(
                f"candidate {candidate_id} is not direction-balanced"
            )
        result.append((candidate_id, tuple(rows)))
    return tuple(result)


def _base_scalar_inputs(
    candidates: Sequence[tuple[str, Sequence[Mapping[str, Any]]]],
    *,
    source_sha256: str,
) -> tuple[Mapping[str, Any], ...]:
    inputs: list[Mapping[str, Any]] = []
    seen_input_ids: set[str] = set()
    for candidate_id, rows in candidates:
        statements = [
            {
                "direction": row["persona_consistent_response"],
                "text": row["statement"],
            }
            for row in rows
        ]
        content_sha = _sha256(canonical_json_bytes(statements))
        input_id = "PSI-" + _domain_hash(
            HASH_DOMAINS["scalar_input_id"],
            source_sha256,
            candidate_id,
            content_sha,
        )[:20]
        if input_id in seen_input_ids:
            raise PersonaStagePacketError("scalar input-ID collision")
        seen_input_ids.add(input_id)
        value = {
            "candidate_anonymous_id": candidate_id,
            "input_id": input_id,
            "statements": statements,
        }
        _assert_rater_safe(value, context="scalar input")
        inputs.append(value)
    return tuple(inputs)


def build_scalar_inputs(
    source_packet_bytes: bytes,
    *,
    expected_source_sha256: str = SOURCE_PACKET_SHA256,
) -> tuple[Mapping[str, Any], ...]:
    """Return the 24 content-bound candidate-level scalar inputs."""

    candidates = _source_candidates(
        source_packet_bytes, expected_source_sha256=expected_source_sha256
    )
    return _base_scalar_inputs(
        candidates, source_sha256=expected_source_sha256
    )


def _repeat_row(base: Mapping[str, Any], slot: str) -> Mapping[str, Any]:
    base_id = str(base["input_id"])
    base_candidate = str(base["candidate_anonymous_id"])
    statements_sha = _sha256(canonical_json_bytes(base["statements"]))
    repeat_input = "PSI-" + _domain_hash(
        HASH_DOMAINS["repeat_input_id"], slot, base_id, statements_sha
    )[:20]
    repeat_candidate = "PC-" + _domain_hash(
        HASH_DOMAINS["repeat_candidate_id"], slot, base_candidate, base_id
    )[:16]
    value = {
        "candidate_anonymous_id": repeat_candidate,
        "input_id": repeat_input,
        "statements": [dict(item) for item in base["statements"]],
    }
    _assert_rater_safe(value, context="scalar blind repeat")
    return value


def _queue_for_primary(
    base_inputs: Sequence[Mapping[str, Any]], slot: str
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    ordered = sorted(
        base_inputs,
        key=lambda row: (
            _domain_hash(
                HASH_DOMAINS["primary_queue_order"], slot, str(row["input_id"])
            ),
            str(row["input_id"]),
        ),
    )
    selected = sorted(
        base_inputs,
        key=lambda row: (
            _domain_hash(
                HASH_DOMAINS["repeat_selection"],
                slot,
                str(row["candidate_anonymous_id"]),
                str(row["input_id"]),
            ),
            str(row["input_id"]),
        ),
    )[:REPEATS_PER_PRIMARY]
    repeats = [(_repeat_row(base, slot), base) for base in selected]
    repeats.sort(
        key=lambda item: _domain_hash(
            HASH_DOMAINS["repeat_insertion"], slot, str(item[0]["input_id"])
        )
    )

    queue = list(ordered)
    for repeat, base in repeats:
        # Pick a frozen, independently hashed insertion gap, excluding gaps next
        # to the repeated original.  Nothing in the rater row marks this alias
        # as a repeat.
        valid_positions: list[int] = []
        for position in range(len(queue) + 1):
            neighbors = queue[max(0, position - 1) : min(len(queue), position + 1)]
            if all(
                item["candidate_anonymous_id"]
                != base["candidate_anonymous_id"]
                for item in neighbors
            ):
                valid_positions.append(position)
        if not valid_positions:  # pragma: no cover - impossible for 24 candidates
            raise PersonaStagePacketError("no non-adjacent blind-repeat insertion gap")
        insertion_hash = _domain_hash(
            HASH_DOMAINS["repeat_insertion"],
            slot,
            str(repeat["input_id"]),
            str(base["input_id"]),
        )
        position = valid_positions[int(insertion_hash, 16) % len(valid_positions)]
        queue.insert(position, repeat)

    schedule: list[Mapping[str, Any]] = []
    for repeat, base in repeats:
        position = next(
            index
            for index, row in enumerate(queue, start=1)
            if row["input_id"] == repeat["input_id"]
        )
        base_position = next(
            index
            for index, row in enumerate(queue, start=1)
            if row["input_id"] == base["input_id"]
        )
        if abs(position - base_position) <= 1:
            raise PersonaStagePacketError("blind repeat is adjacent to its original")
        schedule.append(
            {
                "base_candidate_anonymous_id": base["candidate_anonymous_id"],
                "base_input_id": base["input_id"],
                "primary_slot": slot,
                "queue_position": position,
                "repeat_candidate_anonymous_id": repeat["candidate_anonymous_id"],
                "repeat_input_id": repeat["input_id"],
            }
        )
    return tuple(queue), tuple(sorted(schedule, key=lambda row: row["queue_position"]))


def _normalized_packet_paths(
    packet_paths: Mapping[str, str | Path] | None,
) -> dict[str, str]:
    supplied = PRIMARY_PACKET_PATHS if packet_paths is None else packet_paths
    if set(supplied) != set(PRIMARY_SLOTS):
        raise PersonaStagePacketError(
            "scalar packet paths must cover exactly primary_01..primary_03"
        )
    return {slot: _path_label(supplied[slot]) for slot in PRIMARY_SLOTS}


def build_scalar_stage_packets(
    source_packet_bytes: bytes,
    *,
    expected_source_sha256: str = SOURCE_PACKET_SHA256,
    source_path: str | Path = SOURCE_PACKET_PATH,
    packet_paths: Mapping[str, str | Path] | None = None,
    pair_packet_path: str | Path = PAIR_PACKET_PATH,
) -> ScalarStage:
    """Build three 27-row primary queues and their admin-only repeat map."""

    candidates = _source_candidates(
        source_packet_bytes, expected_source_sha256=expected_source_sha256
    )
    base_inputs = _base_scalar_inputs(
        candidates, source_sha256=expected_source_sha256
    )
    paths = _normalized_packet_paths(packet_paths)
    packets: dict[str, tuple[Mapping[str, Any], ...]] = {}
    packet_bytes: dict[str, bytes] = {}
    schedule: list[Mapping[str, Any]] = []
    packet_manifest: dict[str, Any] = {}
    for slot in PRIMARY_SLOTS:
        queue, repeats = _queue_for_primary(base_inputs, slot)
        encoded = _jsonl_bytes(queue)
        if len(queue) != CANDIDATE_COUNT + REPEATS_PER_PRIMARY:
            raise PersonaStagePacketError("primary scalar queue has wrong size")
        if len({row["input_id"] for row in queue}) != len(queue):
            raise PersonaStagePacketError("primary scalar queue input IDs collide")
        packets[slot] = queue
        packet_bytes[slot] = encoded
        schedule.extend(repeats)
        packet_manifest[slot] = {
            "byte_sha256": _sha256(encoded),
            "original_candidate_count": CANDIDATE_COUNT,
            "path": paths[slot],
            "repeat_count": REPEATS_PER_PRIMARY,
            "row_count": len(queue),
        }

    canonical_source_rows = [value for _, _, value in _jsonl_rows(
        source_packet_bytes, context="source Persona packet"
    )]
    manifest: dict[str, Any] = {
        "schema_version": SCALAR_MANIFEST_SCHEMA,
        "protocol_state": {
            "g1_passed": False,
            "models_run_by_builder": False,
            "pair_review_status": "WAITING_FOR_THREE_COMPLETE_SCALAR_LEDGERS",
            "ratings_generated_by_builder": False,
            "target_model_execution_authorized": False,
        },
        "source_packet": {
            "byte_sha256": expected_source_sha256,
            "canonical_rows_sha256": _sha256(
                canonical_json_bytes(canonical_source_rows)
            ),
            "candidate_count": CANDIDATE_COUNT,
            "items_per_candidate": ITEMS_PER_CANDIDATE,
            "path": _path_label(source_path),
            "row_count": SOURCE_ROW_COUNT,
        },
        "hash_contract": {
            "algorithm": "sha256-length-prefixed-domain-and-fields-v1",
            "domains": dict(HASH_DOMAINS),
            "seed_sha256": SEED_SHA256,
        },
        "scalar_inputs": {
            "base_candidate_count": CANDIDATE_COUNT,
            "blind_repeat_fraction": (
                REPEAT_FRACTION_NUMERATOR / REPEAT_FRACTION_DENOMINATOR
            ),
            "blind_repeats_per_primary": REPEATS_PER_PRIMARY,
            "primary_packets": packet_manifest,
            "rater_packets_contain_repeat_map": False,
            "rater_packets_contain_source_map": False,
        },
        "blind_repeat_admin_schedule": sorted(
            schedule,
            key=lambda row: (str(row["primary_slot"]), int(row["queue_position"])),
        ),
        "pair_packet": {
            "candidate_scope": "ALL_24_CANDIDATES_REGARDLESS_OF_SCALAR_DECISION",
            "definition_evidence_per_candidate": 3,
            "path": _path_label(pair_packet_path),
            "row_count": PAIR_COUNT,
            "status": "NOT_BUILT",
        },
    }
    return ScalarStage(
        source_sha256=expected_source_sha256,
        candidate_order=tuple(candidate_id for candidate_id, _ in candidates),
        base_inputs=base_inputs,
        packets=packets,
        packet_bytes=packet_bytes,
        repeat_schedule=tuple(manifest["blind_repeat_admin_schedule"]),
        manifest=manifest,
        manifest_bytes=_yaml_bytes(manifest),
    )


def _require_mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PersonaStagePacketError(f"{context} must be a mapping")
    return value


def _reviewer_projection(
    record: Mapping[str, Any], *, slot: str
) -> Mapping[str, str]:
    reviewer = _require_mapping(record.get("reviewer"), context="ledger reviewer")
    required = {
        "reviewer_slot_id",
        "reviewer_role",
        "model_id",
        "model_revision",
        "base_model_family",
    }
    if any(not isinstance(reviewer.get(key), str) or not reviewer[key] for key in required):
        raise PersonaStagePacketError("ledger reviewer identity is incomplete")
    if reviewer["reviewer_slot_id"] != slot:
        raise PersonaStagePacketError("ledger reviewer slot differs from supplied slot")
    if reviewer["reviewer_role"] != "independent_primary_rater":
        raise PersonaStagePacketError("scalar ledger is not from a primary rater")
    if not _MODEL_REVISION_RE.fullmatch(str(reviewer["model_revision"])):
        raise PersonaStagePacketError("ledger model revision is not a full commit")
    return {key: str(reviewer[key]) for key in sorted(required)}


def _validate_scalar_response(response: Any) -> Mapping[str, Any]:
    response = _require_mapping(response, context="accepted scalar response")
    if set(response) != {"definition", "scores", "rationale"}:
        raise PersonaStagePacketError("accepted scalar response has wrong fields")
    if not isinstance(response["definition"], str) or not response["definition"].strip():
        raise PersonaStagePacketError("accepted scalar definition is empty")
    if not isinstance(response["rationale"], str) or not response["rationale"].strip():
        raise PersonaStagePacketError("accepted scalar rationale is empty")
    scores = _require_mapping(response["scores"], context="accepted scalar scores")
    if set(scores) != _SCORE_KEYS:
        raise PersonaStagePacketError("accepted scalar response has wrong score fields")
    if any(
        isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 2
        for score in scores.values()
    ):
        raise PersonaStagePacketError("accepted scalar scores must be integers in [0,2]")
    return response


def _consume_scalar_ledger(
    raw: bytes,
    *,
    slot: str,
    expected_packet: Sequence[Mapping[str, Any]],
    expected_packet_bytes: bytes,
) -> tuple[Mapping[str, Mapping[str, Any]], Mapping[str, Any]]:
    packet_sha = _sha256(expected_packet_bytes)
    expected: dict[str, tuple[int, bytes, Mapping[str, Any]]] = {}
    for line_number, row in enumerate(expected_packet, start=1):
        encoded = canonical_json_bytes(row)
        expected[str(row["input_id"])] = (line_number, encoded, row)
    records = _jsonl_rows(raw, context=f"{slot} scalar ledger", require_canonical=True)
    previous: str | None = None
    accepted: dict[str, Mapping[str, Any]] = {}
    accepted_record_hashes: dict[str, str] = {}
    reviewer_projection: Mapping[str, str] | None = None
    for line_number, _, record in records:
        if record.get("schema_version") != LEDGER_SCHEMA:
            raise PersonaStagePacketError(
                f"{slot} ledger line {line_number} has wrong schema"
            )
        record_hash = record.get("record_sha256")
        if not isinstance(record_hash, str) or not _SHA256_RE.fullmatch(record_hash):
            raise PersonaStagePacketError(f"{slot} ledger record hash is invalid")
        body = dict(record)
        del body["record_sha256"]
        if _sha256(canonical_json_bytes(body)) != record_hash:
            raise PersonaStagePacketError(f"{slot} ledger record hash mismatch")
        if body.get("previous_record_sha256") != previous:
            raise PersonaStagePacketError(f"{slot} ledger hash chain mismatch")
        previous = record_hash
        current_reviewer = _reviewer_projection(record, slot=slot)
        if reviewer_projection is None:
            reviewer_projection = current_reviewer
        elif reviewer_projection != current_reviewer:
            raise PersonaStagePacketError(f"{slot} ledger reviewer identity changed")
        if record.get("mode") != "PRODUCTION":
            raise PersonaStagePacketError("pair inputs require PRODUCTION scalar ledgers")
        packet = _require_mapping(record.get("packet"), context="ledger packet binding")
        if packet.get("file_sha256") != packet_sha:
            raise PersonaStagePacketError(f"{slot} ledger packet hash differs")
        contract = _require_mapping(
            record.get("review_contract"), context="ledger review contract"
        )
        contract_sha = record.get("review_contract_sha256")
        if (
            not isinstance(contract_sha, str)
            or not _SHA256_RE.fullmatch(contract_sha)
            or _sha256(canonical_json_bytes(contract)) != contract_sha
        ):
            raise PersonaStagePacketError(f"{slot} review contract hash differs")
        if contract.get("mode") != "PRODUCTION" or contract.get(
            "packet_file_sha256"
        ) != packet_sha:
            raise PersonaStagePacketError(f"{slot} review contract is not packet-bound")
        if (
            contract.get("schema_version") != REVIEW_CONTRACT_SCHEMA_VERSION
            or contract.get("output_normalization") != OUTPUT_NORMALIZATION_CONTRACT
        ):
            raise PersonaStagePacketError(
                f"{slot} review contract has the wrong normalization contract"
            )
        contract_reviewer = _require_mapping(
            contract.get("reviewer"), context="review contract reviewer"
        )
        if any(
            contract_reviewer.get(key) != value
            for key, value in current_reviewer.items()
            if key != "reviewer_role" or key in contract_reviewer
        ):
            raise PersonaStagePacketError(f"{slot} review contract reviewer differs")
        item = _require_mapping(record.get("item"), context="ledger item")
        input_id = item.get("item_id")
        if not isinstance(input_id, str) or input_id not in expected:
            raise PersonaStagePacketError(f"{slot} ledger contains an unknown input ID")
        expected_line, expected_row_bytes, expected_row = expected[input_id]
        if (
            item.get("task_id") != "persona_scalar"
            or item.get("line_number") != expected_line
            or item.get("row_sha256") != _sha256(expected_row_bytes)
            or item.get("canonical_sha256") != _sha256(expected_row_bytes)
        ):
            raise PersonaStagePacketError(f"{slot} ledger item provenance differs")
        if record.get("status") != "accepted":
            continue
        if input_id in accepted:
            raise PersonaStagePacketError(
                f"{slot} ledger has duplicate accepted input {input_id}"
            )
        response = _validate_scalar_response(record.get("response"))
        response_sha = record.get("response_canonical_sha256")
        if response_sha != _sha256(canonical_json_bytes(response)):
            raise PersonaStagePacketError(f"{slot} accepted response hash differs")
        raw_output = record.get("raw_output")
        raw_output_sha = record.get("raw_output_sha256")
        if (
            not isinstance(raw_output, str)
            or raw_output_sha != _sha256(raw_output.encode("utf-8"))
        ):
            raise PersonaStagePacketError(f"{slot} accepted raw output hash differs")
        try:
            normalized = normalize_model_output(raw_output)
        except ValueError as exc:
            raise PersonaStagePacketError(
                f"{slot} accepted output cannot be normalized"
            ) from exc
        if (
            record.get("normalization") != normalized.normalization
            or record.get("normalized_output_sha256") != normalized.sha256
        ):
            raise PersonaStagePacketError(
                f"{slot} accepted normalization evidence differs"
            )
        try:
            normalized_response = json.loads(normalized.text)
        except json.JSONDecodeError as exc:
            raise PersonaStagePacketError(
                f"{slot} accepted normalized output is not JSON"
            ) from exc
        if canonical_json_bytes(normalized_response) != canonical_json_bytes(response):
            raise PersonaStagePacketError(
                f"{slot} normalized output and response differ"
            )
        accepted[input_id] = response
        accepted_record_hashes[input_id] = record_hash
    if set(accepted) != set(expected):
        missing = sorted(set(expected) - set(accepted))
        extra = sorted(set(accepted) - set(expected))
        raise PersonaStagePacketError(
            f"{slot} ledger is incomplete (missing={missing}, extra={extra})"
        )
    if reviewer_projection is None:  # pragma: no cover - non-empty parser guarantees
        raise PersonaStagePacketError(f"{slot} ledger is empty")
    provenance = {
        "accepted_count": len(accepted),
        "accepted_record_hashes_root_sha256": _sha256(
            canonical_json_bytes(accepted_record_hashes)
        ),
        "byte_sha256": _sha256(raw),
        "record_count": len(records),
        "reviewer": dict(reviewer_projection),
        "tail_record_sha256": previous,
    }
    return accepted, provenance


def build_pair_inputs(
    definition_evidence_by_candidate: Mapping[str, Sequence[str]],
    *,
    candidate_order: Sequence[str] | None = None,
) -> tuple[Mapping[str, Any], ...]:
    """Build all 276 pair inputs from three definitions per anonymous candidate."""

    if set(definition_evidence_by_candidate) == set():
        raise PersonaStagePacketError("definition evidence is empty")
    if len(definition_evidence_by_candidate) != CANDIDATE_COUNT:
        raise PersonaStagePacketError("pair stage requires exactly 24 candidates")
    for candidate_id, evidence in definition_evidence_by_candidate.items():
        if not _CANDIDATE_ID_RE.fullmatch(candidate_id):
            raise PersonaStagePacketError("pair definition has invalid candidate ID")
        if (
            isinstance(evidence, (str, bytes))
            or len(evidence) != len(PRIMARY_SLOTS)
            or any(not isinstance(text, str) or not text.strip() for text in evidence)
        ):
            raise PersonaStagePacketError(
                "every pair candidate needs three non-empty definition strings"
            )
    order = (
        tuple(sorted(definition_evidence_by_candidate))
        if candidate_order is None
        else tuple(candidate_order)
    )
    if len(order) != CANDIDATE_COUNT or set(order) != set(
        definition_evidence_by_candidate
    ) or len(set(order)) != len(order):
        raise PersonaStagePacketError("candidate order is not an exact 24-candidate permutation")

    rows: list[Mapping[str, Any]] = []
    for left_index, left in enumerate(order):
        for right in order[left_index + 1 :]:
            canonical_pair = tuple(sorted((left, right)))
            orientation = _domain_hash(
                HASH_DOMAINS["pair_orientation"], *canonical_pair
            )
            candidate_a, candidate_b = (
                canonical_pair if int(orientation[-1], 16) % 2 == 0 else canonical_pair[::-1]
            )
            evidence_a = list(definition_evidence_by_candidate[candidate_a])
            evidence_b = list(definition_evidence_by_candidate[candidate_b])
            evidence_sha_a = _sha256(canonical_json_bytes(evidence_a))
            evidence_sha_b = _sha256(canonical_json_bytes(evidence_b))
            input_id = "PPI-" + _domain_hash(
                HASH_DOMAINS["pair_input_id"],
                candidate_a,
                evidence_sha_a,
                candidate_b,
                evidence_sha_b,
            )[:20]
            row = {
                "candidate_a": {
                    "definition_evidence": evidence_a,
                    "id": candidate_a,
                },
                "candidate_b": {
                    "definition_evidence": evidence_b,
                    "id": candidate_b,
                },
                "input_id": input_id,
            }
            _assert_rater_safe(row, context="Persona pair input")
            rows.append(row)
    rows.sort(
        key=lambda row: (
            _domain_hash(HASH_DOMAINS["pair_queue_order"], str(row["input_id"])),
            str(row["input_id"]),
        )
    )
    if len(rows) != PAIR_COUNT or len({row["input_id"] for row in rows}) != PAIR_COUNT:
        raise PersonaStagePacketError("pair packet is incomplete or has ID collisions")
    observed_pairs = {
        frozenset((row["candidate_a"]["id"], row["candidate_b"]["id"]))
        for row in rows
    }
    if len(observed_pairs) != PAIR_COUNT:
        raise PersonaStagePacketError("pair packet repeats an unordered pair")
    return tuple(rows)


def build_pair_stage_packet_from_ledgers(
    source_packet_bytes: bytes,
    *,
    scalar_packet_bytes_by_slot: Mapping[str, bytes],
    scalar_ledger_bytes_by_slot: Mapping[str, bytes],
    expected_source_sha256: str = SOURCE_PACKET_SHA256,
    source_path: str | Path = SOURCE_PACKET_PATH,
    scalar_packet_paths: Mapping[str, str | Path] | None = None,
    scalar_ledger_paths: Mapping[str, str | Path] | None = None,
    pair_packet_path: str | Path = PAIR_PACKET_PATH,
) -> PairStage:
    """Consume three complete hash-chained ledgers into one common pair packet."""

    if set(scalar_packet_bytes_by_slot) != set(PRIMARY_SLOTS):
        raise PersonaStagePacketError("three primary scalar packet byte streams are required")
    if set(scalar_ledger_bytes_by_slot) != set(PRIMARY_SLOTS):
        raise PersonaStagePacketError("three primary scalar ledger byte streams are required")
    packet_paths = _normalized_packet_paths(scalar_packet_paths)
    if scalar_ledger_paths is None:
        ledger_paths = {slot: f"<{slot}-scalar-ledger>" for slot in PRIMARY_SLOTS}
    else:
        if set(scalar_ledger_paths) != set(PRIMARY_SLOTS):
            raise PersonaStagePacketError("scalar ledger paths must cover all primary slots")
        ledger_paths = {
            slot: _path_label(scalar_ledger_paths[slot]) for slot in PRIMARY_SLOTS
        }
    scalar_stage = build_scalar_stage_packets(
        source_packet_bytes,
        expected_source_sha256=expected_source_sha256,
        source_path=source_path,
        packet_paths=packet_paths,
        pair_packet_path=pair_packet_path,
    )
    definitions: dict[str, list[str]] = {
        candidate_id: [] for candidate_id in scalar_stage.candidate_order
    }
    ledger_provenance: dict[str, Any] = {}
    repeat_agreement: list[dict[str, Any]] = []
    reviewer_families: set[str] = set()
    schedule_by_slot = {
        slot: [row for row in scalar_stage.repeat_schedule if row["primary_slot"] == slot]
        for slot in PRIMARY_SLOTS
    }
    for slot in PRIMARY_SLOTS:
        observed_packet = scalar_packet_bytes_by_slot[slot]
        if observed_packet != scalar_stage.packet_bytes[slot]:
            raise PersonaStagePacketError(
                f"{slot} scalar packet bytes differ from deterministic rebuild"
            )
        accepted, provenance = _consume_scalar_ledger(
            scalar_ledger_bytes_by_slot[slot],
            slot=slot,
            expected_packet=scalar_stage.packets[slot],
            expected_packet_bytes=observed_packet,
        )
        family = provenance["reviewer"]["base_model_family"]
        if family in reviewer_families:
            raise PersonaStagePacketError("primary scalar base-model families are not distinct")
        reviewer_families.add(family)
        ledger_provenance[slot] = {
            **provenance,
            "path": ledger_paths[slot],
        }
        base_by_candidate = {
            str(row["candidate_anonymous_id"]): str(row["input_id"])
            for row in scalar_stage.base_inputs
        }
        for candidate_id in scalar_stage.candidate_order:
            # Deliberately use only the original input.  A repeat has its own
            # alias and ledger record and can never overwrite this definition.
            definitions[candidate_id].append(
                str(accepted[base_by_candidate[candidate_id]]["definition"])
            )
        for repeat in schedule_by_slot[slot]:
            base_response = accepted[str(repeat["base_input_id"])]
            repeat_response = accepted[str(repeat["repeat_input_id"])]
            repeat_agreement.append(
                {
                    **dict(repeat),
                    "base_accepted_record_sha256": None,
                    "rating_vector_exact_match": (
                        base_response["scores"] == repeat_response["scores"]
                    ),
                    "repeat_response_is_separate": True,
                }
            )

    rows = build_pair_inputs(definitions, candidate_order=scalar_stage.candidate_order)
    encoded = _jsonl_bytes(rows)
    manifest = dict(scalar_stage.manifest)
    manifest["protocol_state"] = {
        **dict(manifest["protocol_state"]),
        "pair_review_status": "PAIR_PACKET_PREPARED_NOT_RUN",
    }
    manifest["scalar_rating_ledgers"] = ledger_provenance
    manifest["blind_repeat_results"] = {
        "agreement_threshold_applied_by_this_builder": False,
        "exact_rating_vector_match_count": sum(
            bool(row["rating_vector_exact_match"]) for row in repeat_agreement
        ),
        "repeat_count": len(repeat_agreement),
        "responses_kept_separate": True,
        "rows": repeat_agreement,
    }
    manifest["pair_packet"] = {
        "byte_sha256": _sha256(encoded),
        "candidate_scope": "ALL_24_CANDIDATES_REGARDLESS_OF_SCALAR_DECISION",
        "definition_evidence_order": list(PRIMARY_SLOTS),
        "definition_evidence_per_candidate": len(PRIMARY_SLOTS),
        "path": _path_label(pair_packet_path),
        "rater_packet_contains_reviewer_identities": False,
        "rater_packet_contains_scalar_scores_or_rationales": False,
        "rater_packet_contains_source_map": False,
        "row_count": len(rows),
        "status": "PREPARED_NOT_RUN",
    }
    return PairStage(
        rows=rows,
        packet_bytes=encoded,
        manifest=manifest,
        manifest_bytes=_yaml_bytes(manifest),
    )


def write_bytes_exact(path: Path, data: bytes) -> None:
    """Write one generated artifact and verify its exact bytes."""

    if path.is_symlink():
        raise PersonaStagePacketError(f"refusing to replace symbolic link: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if path.read_bytes() != data:
        raise PersonaStagePacketError(f"written bytes differ for {path}")
