"""Prepare outcome-blind, source-anonymized G1 Persona review packets.

The packet builder samples only globally unique Phase-1 source items.  Every
sampled item is permanently consumed by the ``trait_definition`` role and is
therefore unavailable to Persona-vector extraction or held-out validation.
This module prepares review inputs only; it never assigns raters, emits scores,
selects traits, or authorizes target-model execution.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import yaml
from .g1_manifest import canonical_data_sha256

from .g1_personas import (
    G1PersonaAssetError,
    SOURCE_COMMIT,
    UNIQUE_ITEM_STATUS,
    normalize_statement,
    sha256_bytes,
)


CONFIG_FILENAME = "g1_persona_semantic_review_v2_3.yaml"
UMBRELLA_CONFIG_FILENAME = "g1_phase2_v2_3.yaml"
RUBRIC_FILENAME = "persona_adjudication_rubric_v2_3.yaml"
PACKET_MANIFEST_FILENAME = "persona_semantic_review_packet_manifest_v2_3.yaml"
EXPOSURE_FILENAME = "persona_semantic_review_exposure_v2_3.yaml"
PACKET_FILENAME = "persona_semantic_review_packet_v2_3.jsonl"
AUDIT_FILENAME = "persona_semantic_review_packet_audit_v2_3.json"
THIRD_PARTY_NOTICE_PATH = Path("THIRD_PARTY_NOTICES.md")
ANTHROPIC_LICENSE_EVIDENCE_PATH = Path(
    "data/licenses/"
    "anthropics_evals_84fcc677e52e1902d696c32cd1a6b663e70d3993_LICENSE.txt"
)
EXPECTED_THIRD_PARTY_NOTICE_SHA256 = (
    "a0c84cb61235ece2b039644fdf53195cbd6978290da2fbbb490537c709fb8441"
)
EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256 = (
    "7e7170e3cebf88a9f60c7b8421418323c09304da1af4d5e90f4da1dc1c8a2661"
)

PREPARATION_STATUS = "PREPARATION"
EXPOSURE_STATUS = "G1_SEMANTIC_REVIEW_EXPOSED_DEFINITION_ONLY"
ALLOWED_ROLE = "trait_definition"
FORBIDDEN_ROLES = frozenset({"persona_vector_extraction", "held_out_validation"})
RUBRIC_ID = "lps-v2.3-g1-persona-semantic-rubric-v1"
PACKET_SCHEMA_ID = "lps-v2.3-g1-persona-semantic-review-row-v1"
PERSONA_RELEVANT_CONTRACT_PROJECTION_SCHEMA = (
    "restart-v2.3-g1-persona-relevant-contract-projection-v1"
)
PERSONA_PRIMARY_SLOTS = ("primary_01", "primary_02", "primary_03")
PERSONA_ADJUDICATOR_SLOT = "adjudicator_04"
PERSONA_PRE_REVIEW_GUARD_FIELDS = (
    "rule_id",
    "status_flip_alone_authorizes_execution",
    "execution_authorized",
    "reviewer_registry_complete",
    "reviewer_synthetic_smoke_passed",
    "rater_facing_export_frozen",
    "review_access_boundary_attested",
    "review_packet_manifests_frozen",
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class PersonaReviewPacketError(ValueError):
    """Raised when a frozen review-packet or exposure contract is violated."""


def _hash_parts(domain: str, seed: str, *parts: str) -> str:
    """Hash a length-prefixed tuple so domains and fields cannot collide."""

    if not domain or not _SHA256_RE.fullmatch(seed):
        raise PersonaReviewPacketError("hash domain/seed is invalid")
    digest = hashlib.sha256()
    for value in (domain, seed, *parts):
        if not isinstance(value, str):
            raise PersonaReviewPacketError("hash inputs must be strings")
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def anonymous_candidate_id(candidate_trait_id: str, contract: Mapping[str, Any]) -> str:
    digest = _hash_parts(
        contract["anonymous_candidate_id_domain"],
        contract["seed_sha256"],
        candidate_trait_id,
    )
    return f"PC-{digest[:16]}"


def anonymous_review_item_id(source_item_id: str, contract: Mapping[str, Any]) -> str:
    digest = _hash_parts(
        contract["anonymous_item_id_domain"],
        contract["seed_sha256"],
        source_item_id,
    )
    return f"PRI-{digest[:20]}"


def candidate_display_rank(candidate_trait_id: str, contract: Mapping[str, Any]) -> str:
    """Return the separately domain-separated rater-facing group-order rank."""

    return _hash_parts(
        contract["candidate_display_order_domain"],
        contract["seed_sha256"],
        candidate_trait_id,
    )


def sampling_rank(
    candidate_trait_id: str,
    matching_response: str,
    source_item_id: str,
    contract: Mapping[str, Any],
) -> str:
    return _hash_parts(
        contract["ranking_domain"],
        contract["seed_sha256"],
        candidate_trait_id,
        matching_response,
        source_item_id,
    )


def _load_yaml(path: Path) -> Mapping[str, Any]:
    value = yaml.safe_load(path.read_bytes())
    if not isinstance(value, dict):
        raise PersonaReviewPacketError(f"{path} must contain one YAML mapping")
    return value


def _verify_file(path: Path, expected_sha256: str, label: str) -> bytes:
    if not path.is_file():
        raise PersonaReviewPacketError(f"missing {label}: {path}")
    raw = path.read_bytes()
    observed = sha256_bytes(raw)
    if observed != expected_sha256:
        raise PersonaReviewPacketError(
            f"{label} SHA256 mismatch: expected {expected_sha256}, got {observed}"
        )
    return raw


def _persona_reviewer_registry_projection(
    reviewer_registry: Mapping[str, Any],
) -> dict[str, Any]:
    required_fields = (
        "identity_lock_status",
        "exact_model_id_and_revision_required",
        "primary_base_model_families_must_be_pairwise_distinct",
        "adjudicator_base_model_family_must_differ_from_all_primary_families",
        "prompt_sha256s",
        "decoding_parameter_manifest_sha256",
        "training_and_calibration_material_sha256",
        "unresolved_identity_policy",
    )
    missing = [field for field in required_fields if field not in reviewer_registry]
    if missing:
        raise PersonaReviewPacketError(
            f"umbrella Persona reviewer registry is missing field(s): {missing}"
        )
    slots = reviewer_registry.get("slots")
    if not isinstance(slots, list):
        raise PersonaReviewPacketError("umbrella reviewer_registry.slots must be a list")
    expected_slots = (*PERSONA_PRIMARY_SLOTS, PERSONA_ADJUDICATOR_SLOT)
    by_slot: dict[str, Mapping[str, Any]] = {}
    for slot in slots:
        if not isinstance(slot, Mapping):
            raise PersonaReviewPacketError("umbrella reviewer slot must be a mapping")
        slot_id = slot.get("reviewer_slot_id")
        if slot_id in expected_slots:
            if slot_id in by_slot:
                raise PersonaReviewPacketError("duplicate Persona reviewer slot")
            by_slot[slot_id] = slot
    if set(by_slot) != set(expected_slots):
        raise PersonaReviewPacketError("umbrella Persona reviewer panel is incomplete")
    projected_slots: list[dict[str, Any]] = []
    for slot_id in expected_slots:
        slot = by_slot[slot_id]
        slot_fields = (
            "reviewer_slot_id",
            "role",
            "model_id",
            "model_revision",
            "base_model_family",
        )
        if any(field not in slot for field in slot_fields):
            raise PersonaReviewPacketError(
                f"umbrella Persona reviewer slot {slot_id} is incomplete"
            )
        projected_slots.append({field: slot[field] for field in slot_fields})
    return {
        **{field: reviewer_registry[field] for field in required_fields},
        "slots": projected_slots,
    }


def persona_relevant_contract_projection(
    umbrella: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the explicit cycle-free umbrella contract used by Persona review."""

    required_protocol_fields = (
        "schema_version",
        "protocol_id",
        "gate_id",
        "protocol_status",
        "selection_outcome_blind",
        "ratings_generated",
        "target_model_execution_authorized",
    )
    missing = [field for field in required_protocol_fields if field not in umbrella]
    if missing:
        raise PersonaReviewPacketError(
            f"umbrella Persona projection is missing protocol field(s): {missing}"
        )
    for field in (
        "authorization_guard",
        "reviewer_registry",
        "review_execution_boundary",
        "blinding",
        "outputs",
        "persona_review",
    ):
        if not isinstance(umbrella.get(field), Mapping):
            raise PersonaReviewPacketError(
                f"umbrella Persona projection is missing mapping: {field}"
            )
    missing_guard_fields = [
        field
        for field in PERSONA_PRE_REVIEW_GUARD_FIELDS
        if field not in umbrella["authorization_guard"]
    ]
    if missing_guard_fields:
        raise PersonaReviewPacketError(
            f"umbrella Persona authorization guard is missing: {missing_guard_fields}"
        )
    blinding = umbrella["blinding"]
    for field in (
        "forbidden_to_all_reviewers",
        "persona_packet_hides",
        "reviewer_outputs_are_immutable_append_only",
    ):
        if field not in blinding:
            raise PersonaReviewPacketError(f"umbrella blinding is missing {field}")
    projection = {
        "projection_schema_id": PERSONA_RELEVANT_CONTRACT_PROJECTION_SCHEMA,
        "protocol_state": {
            field: umbrella[field] for field in required_protocol_fields
        },
        "authorization_guard": {
            field: umbrella["authorization_guard"][field]
            for field in PERSONA_PRE_REVIEW_GUARD_FIELDS
        },
        "reviewer_registry": _persona_reviewer_registry_projection(
            umbrella["reviewer_registry"]
        ),
        "review_execution_boundary": umbrella["review_execution_boundary"],
        "blinding": {
            "forbidden_to_all_reviewers": blinding["forbidden_to_all_reviewers"],
            "persona_packet_hides": blinding["persona_packet_hides"],
            "reviewer_outputs_are_immutable_append_only": blinding[
                "reviewer_outputs_are_immutable_append_only"
            ],
        },
        "outputs": umbrella["outputs"],
        "persona_review": umbrella["persona_review"],
    }
    return json.loads(json.dumps(projection, ensure_ascii=False))


def validate_persona_relevant_contract_binding(
    payload: Mapping[str, Any],
    umbrella: Mapping[str, Any],
) -> str:
    projection = persona_relevant_contract_projection(umbrella)
    if payload.get("umbrella_relevant_contract_projection_schema_id") != (
        PERSONA_RELEVANT_CONTRACT_PROJECTION_SCHEMA
    ):
        raise PersonaReviewPacketError("Persona projection schema binding mismatch")
    if payload.get("umbrella_relevant_contract_projection") != projection:
        raise PersonaReviewPacketError("Persona relevant-contract projection differs")
    projection_sha256 = canonical_data_sha256(projection)
    if payload.get("umbrella_relevant_contract_projection_sha256") != projection_sha256:
        raise PersonaReviewPacketError("Persona relevant-contract projection hash mismatch")
    return projection_sha256


def _license_evidence_bindings(project_root: Path) -> dict[str, Any]:
    evidence = (
        (
            "third_party_notice",
            THIRD_PARTY_NOTICE_PATH,
            EXPECTED_THIRD_PARTY_NOTICE_SHA256,
        ),
        (
            "anthropic_cc_by_license",
            ANTHROPIC_LICENSE_EVIDENCE_PATH,
            EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256,
        ),
    )
    bindings: dict[str, Any] = {}
    for evidence_id, relative_path, expected_sha256 in evidence:
        _verify_file(project_root / relative_path, expected_sha256, evidence_id)
        bindings[evidence_id] = {
            "path": relative_path.as_posix(),
            "file_sha256": expected_sha256,
        }
    return bindings


def _validate_config(config: Mapping[str, Any]) -> None:
    if config.get("implementation_status") != PREPARATION_STATUS:
        raise PersonaReviewPacketError("review preparation must remain PREPARATION")
    for field in (
        "execution_authorized",
        "contains_target_model_data",
        "target_model_outcomes_observed",
    ):
        if config.get(field) is not False:
            raise PersonaReviewPacketError(f"{field} must be false")
    sampling = config.get("sampling_contract")
    if not isinstance(sampling, dict):
        raise PersonaReviewPacketError("sampling_contract must be a mapping")
    expected = {
        "algorithm_id": "domain-separated-sha256-rank-v1",
        "eligible_item_status": UNIQUE_ITEM_STATUS,
        "candidates": 24,
        "items_per_candidate": 96,
        "matching_yes_per_candidate": 48,
        "matching_no_per_candidate": 48,
        "tie_breaker": "stable_source_item_id_ascending",
    }
    for key, value in expected.items():
        if sampling.get(key) != value:
            raise PersonaReviewPacketError(f"sampling_contract.{key} is not frozen value")
    exposure = config.get("exposure_contract")
    if not isinstance(exposure, dict):
        raise PersonaReviewPacketError("exposure_contract must be a mapping")
    if exposure.get("assigned_status") != EXPOSURE_STATUS:
        raise PersonaReviewPacketError("exposure status is not frozen")
    if exposure.get("allowed_future_persona_item_roles") != [ALLOWED_ROLE]:
        raise PersonaReviewPacketError("only trait_definition may reuse exposed items")
    if set(exposure.get("forbidden_future_persona_item_roles", [])) != FORBIDDEN_ROLES:
        raise PersonaReviewPacketError("forbidden future roles are not frozen")
    review = config.get("review_contract")
    if not isinstance(review, dict):
        raise PersonaReviewPacketError("review_contract must be a mapping")
    required_review_values = {
        "rubric_id": RUBRIC_ID,
        "primary_rater_count": 3,
        "primary_raters_must_use_distinct_base_model_families": True,
        "adjudicator_count": 1,
        "adjudicator_must_use_a_fourth_distinct_base_model_family": True,
        "rater_identity_status": "NOT_ASSIGNED",
        "ratings_status": "NOT_RUN",
        "ratings_must_not_be_generated_by_packet_builder": True,
    }
    for key, value in required_review_values.items():
        if review.get(key) != value:
            raise PersonaReviewPacketError(f"review_contract.{key} is not frozen")
    readiness = config.get("readiness", {})
    if readiness.get("g1_passed") is not False:
        raise PersonaReviewPacketError("G1 cannot be passed by packet preparation")
    if readiness.get("target_model_execution_authorized") is not False:
        raise PersonaReviewPacketError("target-model execution must remain unauthorized")


def _normalized_rubric_dimensions(dimensions: Any) -> list[dict[str, Any]]:
    """Normalize only YAML numeric-key representation; preserve anchor text exactly."""

    if not isinstance(dimensions, list) or len(dimensions) != 7:
        raise PersonaReviewPacketError("umbrella Persona rubric must contain seven dimensions")
    normalized: list[dict[str, Any]] = []
    dimension_ids: set[str] = set()
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            raise PersonaReviewPacketError("every umbrella Persona dimension must be a mapping")
        if set(dimension) != {"dimension_id", "label", "anchors"}:
            raise PersonaReviewPacketError("umbrella Persona dimension fields are not exact")
        dimension_id = dimension["dimension_id"]
        label = dimension["label"]
        if not isinstance(dimension_id, str) or not dimension_id or dimension_id in dimension_ids:
            raise PersonaReviewPacketError("umbrella Persona dimension IDs must be unique strings")
        if not isinstance(label, str) or not label:
            raise PersonaReviewPacketError("umbrella Persona dimension labels must be non-empty")
        dimension_ids.add(dimension_id)
        raw_anchors = dimension["anchors"]
        if not isinstance(raw_anchors, dict):
            raise PersonaReviewPacketError("umbrella Persona anchors must be a mapping")
        anchors: dict[str, str] = {}
        for raw_key, text in raw_anchors.items():
            if isinstance(raw_key, bool):
                raise PersonaReviewPacketError("boolean anchor keys are forbidden")
            if isinstance(raw_key, int) and raw_key in {0, 1, 2}:
                key = str(raw_key)
            elif isinstance(raw_key, str) and raw_key in {"0", "1", "2"}:
                key = raw_key
            else:
                raise PersonaReviewPacketError("anchor keys must normalize exactly to 0/1/2")
            if key in anchors or not isinstance(text, str) or not text:
                raise PersonaReviewPacketError("anchor text must be unique-keyed and non-empty")
            anchors[key] = text
        if set(anchors) != {"0", "1", "2"}:
            raise PersonaReviewPacketError("every umbrella Persona dimension needs exact 0/1/2 anchors")
        normalized.append(
            {"dimension_id": dimension_id, "label": label, "anchors": anchors}
        )
    return normalized


def _validate_umbrella_contract(
    umbrella: Mapping[str, Any],
    *,
    implementation_config_sha256: str,
    sampling_contract: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Require the umbrella method and Persona implementation to agree exactly."""

    if umbrella.get("protocol_status") != "preparation":
        raise PersonaReviewPacketError("umbrella G1 Phase-2 contract must remain preparation")
    persona = umbrella.get("persona_review")
    if not isinstance(persona, dict):
        raise PersonaReviewPacketError("umbrella persona_review contract is missing")
    if persona.get("implementation_contract_file_sha256") != implementation_config_sha256:
        raise PersonaReviewPacketError("umbrella Persona implementation hash binding is stale")
    packet = persona.get("packet_sampling", {})
    if packet.get("algorithm_id") != sampling_contract["algorithm_id"]:
        raise PersonaReviewPacketError("umbrella Persona sampling algorithm differs")
    if packet.get("seed_sha256") != sampling_contract["seed_sha256"]:
        raise PersonaReviewPacketError("umbrella Persona sampling seed differs")
    _normalized_rubric_dimensions(persona.get("rubric_dimensions"))
    pair_review = persona.get("pair_relation_review")
    exact_labels = [
        "distinct_traits",
        "related_but_distinct_traits",
        "opposite_poles_of_one_axis",
        "same_trait_or_near_duplicate",
        "insufficient_evidence",
    ]
    if not isinstance(pair_review, dict):
        raise PersonaReviewPacketError("umbrella pair_relation_review is missing")
    if pair_review.get("unordered_pair_count") != 276:
        raise PersonaReviewPacketError("all 276 unordered Persona pairs are required")
    if pair_review.get("all_unordered_pairs_of_24_required") is not True:
        raise PersonaReviewPacketError("pair review cannot be limited to scalar survivors")
    if pair_review.get("labels") != exact_labels:
        raise PersonaReviewPacketError("umbrella Persona pair labels differ from frozen five-label set")
    return persona


def _read_source_statement(source_root: Path, trait: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    path = source_root / trait["source_path"]
    if not path.is_file():
        raise PersonaReviewPacketError(f"missing locked source file: {path}")
    lines = path.read_bytes().splitlines()
    line_number = item["source_line_number"]
    if isinstance(line_number, bool) or not isinstance(line_number, int):
        raise PersonaReviewPacketError("source_line_number must be an integer")
    try:
        raw_line = lines[line_number - 1]
    except IndexError as exc:
        raise PersonaReviewPacketError(f"source line is out of range: {path}:{line_number}") from exc
    if sha256_bytes(raw_line) != item["raw_line_sha256"]:
        raise PersonaReviewPacketError(f"raw source line hash mismatch: {path}:{line_number}")
    try:
        record = json.loads(raw_line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PersonaReviewPacketError(f"invalid source JSON: {path}:{line_number}") from exc
    statement = record.get("statement")
    if not isinstance(statement, str) or not statement:
        raise PersonaReviewPacketError(f"source statement is invalid: {path}:{line_number}")
    if sha256_bytes(statement.encode("utf-8")) != item["statement_sha256"]:
        raise PersonaReviewPacketError(f"statement hash mismatch: {path}:{line_number}")
    normalized_sha = sha256_bytes(normalize_statement(statement).encode("utf-8"))
    if normalized_sha != item["normalized_statement_sha256"]:
        raise PersonaReviewPacketError(f"normalized statement hash mismatch: {path}:{line_number}")
    matching = record.get("answer_matching_behavior")
    not_matching = record.get("answer_not_matching_behavior")
    if matching != item["answer_matching_behavior"] or not_matching != item["answer_not_matching_behavior"]:
        raise PersonaReviewPacketError(f"response-direction mismatch: {path}:{line_number}")
    if {matching, not_matching} != {" Yes", " No"}:
        raise PersonaReviewPacketError(f"source response choices are not Yes/No: {path}:{line_number}")
    return statement


def select_review_items(
    trait: Mapping[str, Any],
    sampling_contract: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    """Select 48 upstream matching-Yes and 48 matching-No items by frozen rank."""

    trait_id = trait["candidate_trait_id"]
    selected: list[Mapping[str, Any]] = []
    for response, required in (
        (" Yes", sampling_contract["matching_yes_per_candidate"]),
        (" No", sampling_contract["matching_no_per_candidate"]),
    ):
        eligible = [
            item
            for item in trait["source_items"]
            if item.get("g1_candidate_item_status") == sampling_contract["eligible_item_status"]
            and item.get("answer_matching_behavior") == response
        ]
        ranked = sorted(
            eligible,
            key=lambda item: (
                sampling_rank(
                    trait_id,
                    response.strip(),
                    item["stable_source_item_id"],
                    sampling_contract,
                ),
                item["stable_source_item_id"],
            ),
        )
        if len(ranked) < required:
            raise PersonaReviewPacketError(
                f"{trait_id} has only {len(ranked)} eligible matching-{response.strip()} items; "
                f"requires {required}"
            )
        selected.extend(ranked[:required])
    return sorted(
        selected,
        key=lambda item: (
            sampling_rank(
                trait_id,
                item["answer_matching_behavior"].strip(),
                item["stable_source_item_id"],
                sampling_contract,
            ),
            item["stable_source_item_id"],
        ),
    )


def validate_future_persona_item_roles(
    exposed_source_item_ids: Iterable[str],
    proposed_rows: Sequence[Mapping[str, Any]],
) -> None:
    """Fail closed if a semantic-review item is reused outside definition."""

    exposed = set(exposed_source_item_ids)
    if len(exposed) == 0:
        raise PersonaReviewPacketError("exposure set must not be empty")
    for index, row in enumerate(proposed_rows, start=1):
        source_id = row.get("source_item_id")
        role = row.get("role")
        if not isinstance(source_id, str) or not isinstance(role, str):
            raise PersonaReviewPacketError(
                f"future item-role row {index} requires string source_item_id and role"
            )
        if source_id in exposed and role != ALLOWED_ROLE:
            raise PersonaReviewPacketError(
                f"semantic-review-exposed item {source_id} cannot receive role {role}"
            )


def _rubric_payload(
    config: Mapping[str, Any],
    config_sha256: str,
    umbrella_persona: Mapping[str, Any],
    contract_projection: Mapping[str, Any],
    contract_projection_sha256: str,
) -> dict[str, Any]:
    dimensions = _normalized_rubric_dimensions(umbrella_persona["rubric_dimensions"])
    pair_review = dict(umbrella_persona["pair_relation_review"])
    pair_review["status"] = "NOT_RUN_REQUIRED_BEFORE_FINAL_CATALOG"
    pair_review["candidate_scope"] = "ALL_24_CANDIDATES_REGARDLESS_OF_SCALAR_REVIEW_DECISION"
    return {
        "schema_id": "lps-v2.3-g1-persona-adjudication-rubric-v1",
        "implementation_status": PREPARATION_STATUS,
        "g1_gate_status": "OPEN_NOT_G1_PASS",
        "execution_authorized": False,
        "contains_target_model_data": False,
        "selection_outcome_blind": True,
        "rubric_id": RUBRIC_ID,
        "config_sha256": config_sha256,
        "umbrella_relevant_contract_projection_schema_id": (
            PERSONA_RELEVANT_CONTRACT_PROJECTION_SCHEMA
        ),
        "umbrella_relevant_contract_projection_sha256": contract_projection_sha256,
        "umbrella_relevant_contract_projection": contract_projection,
        "redistribution_notice": config["redistribution_notice"],
        "score_scale": dict(umbrella_persona["score_scale"]),
        "rubric_dimensions": dimensions,
        "criterion_code_map": {
            f"P{index}": item["dimension_id"]
            for index, item in enumerate(dimensions, start=1)
        },
        "primary_rating_panel": {
            "required_raters": 3,
            "distinct_base_model_families_required": 3,
            "identity_assignment_status": "NOT_ASSIGNED",
            "slots": [
                {
                    "slot_id": slot_id,
                    "model_id": None,
                    "base_model_family_id": None,
                    "model_revision": None,
                    "assignment_status": "UNASSIGNED",
                    "ratings_status": "NOT_RUN",
                }
                for slot_id in PERSONA_PRIMARY_SLOTS
            ],
        },
        "adjudication_panel": {
            "required_adjudicators": 1,
            "fourth_distinct_base_model_family_required": True,
            "identity_assignment_status": "NOT_ASSIGNED",
            "slots": [
                {
                    "slot_id": PERSONA_ADJUDICATOR_SLOT,
                    "model_id": None,
                    "base_model_family_id": None,
                    "model_revision": None,
                    "assignment_status": "UNASSIGNED",
                    "ratings_status": "NOT_RUN",
                }
            ],
            "required_trigger_conditions": [
                "primary accept recommendations are not unanimous",
                "any primary score differs by two scale points on one criterion",
                "candidate is at an acceptance boundary after primary aggregation",
            ],
        },
        "per_rater_total": dict(umbrella_persona["per_rater_total"]),
        "provisional_decision_rules": dict(umbrella_persona["provisional_decision_rules"]),
        "agreement_rules": dict(umbrella_persona["agreement_rules"]),
        "pair_relation_review": pair_review,
        "family_adjudication": dict(umbrella_persona["family_adjudication"]),
        "rating_record_status": "NO_RATINGS_IN_THIS_ASSET",
        "g1_passed": False,
    }


def _yaml_bytes(payload: Mapping[str, Any]) -> bytes:
    return yaml.safe_dump(
        dict(payload), allow_unicode=True, sort_keys=False, width=100
    ).encode("utf-8")


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for row in rows
    )


def _write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def build_persona_review_assets(
    *,
    project_root: Path,
    output_root: Path | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Build the frozen 2,304-row blinded packet and its exposure ledger."""

    project_root = project_root.resolve()
    output_root = project_root if output_root is None else output_root.resolve()
    config_path = (
        project_root / "configs" / CONFIG_FILENAME
        if config_path is None
        else config_path.resolve()
    )
    config_raw = config_path.read_bytes()
    config = _load_yaml(config_path)
    _validate_config(config)
    config_sha = sha256_bytes(config_raw)
    umbrella_path = project_root / "configs" / UMBRELLA_CONFIG_FILENAME
    umbrella = _load_yaml(umbrella_path)
    umbrella_persona = _validate_umbrella_contract(
        umbrella,
        implementation_config_sha256=config_sha,
        sampling_contract=config["sampling_contract"],
    )
    contract_projection = persona_relevant_contract_projection(umbrella)
    contract_projection_sha = canonical_data_sha256(contract_projection)
    license_evidence_bindings = _license_evidence_bindings(project_root)

    contract_binding = {
        "umbrella_relevant_contract_projection_schema_id": (
            PERSONA_RELEVANT_CONTRACT_PROJECTION_SCHEMA
        ),
        "umbrella_relevant_contract_projection_sha256": contract_projection_sha,
        "umbrella_relevant_contract_projection": contract_projection,
    }

    candidate_lock = config["input_locks"]["candidate_pool"]
    candidate_path = project_root / candidate_lock["path"]
    candidate_raw = _verify_file(
        candidate_path, candidate_lock["file_sha256"], "candidate pool"
    )
    pool = yaml.safe_load(candidate_raw)
    if pool.get("source_revision") != SOURCE_COMMIT:
        raise PersonaReviewPacketError("candidate source revision is not locked commit")
    if pool.get("candidate_trait_count") != 24:
        raise PersonaReviewPacketError("candidate pool must contain 24 traits")
    duplicate_lock = config["input_locks"]["duplicate_audit"]
    duplicate_path = project_root / duplicate_lock["path"]
    duplicate_raw = _verify_file(
        duplicate_path, duplicate_lock["file_sha256"], "duplicate audit"
    )
    duplicate_audit = json.loads(duplicate_raw)
    if duplicate_audit["summary"]["retained_globally_unique_candidate_rows"] != 23_685:
        raise PersonaReviewPacketError("globally unique candidate count is not frozen")

    source_root = project_root / config["input_locks"]["source_checkout"]["path"]
    sampling_contract = config["sampling_contract"]
    packet_rows: list[dict[str, Any]] = []
    exposure_rows: list[dict[str, Any]] = []
    candidate_map: list[dict[str, Any]] = []
    used_source_ids: set[str] = set()
    used_anonymous_ids: set[str] = set()

    # Never preserve upstream/source-trait order in the rater-facing JSONL. A
    # separately domain-separated hash freezes a pseudorandom group order.
    traits = sorted(
        pool["candidate_traits"],
        key=lambda item: (
            candidate_display_rank(item["candidate_trait_id"], sampling_contract),
            item["candidate_trait_id"],
        ),
    )
    for trait in traits:
        trait_id = trait["candidate_trait_id"]
        anonymous_trait = anonymous_candidate_id(trait_id, sampling_contract)
        selected = select_review_items(trait, sampling_contract)
        direction_counts = Counter()
        candidate_map.append(
            {
                "candidate_anonymous_id": anonymous_trait,
                "candidate_trait_id": trait_id,
                "candidate_family_id": trait["candidate_family_id"],
                "source_trait_slug": trait["source_trait_slug"],
                "source_path": trait["source_path"],
                "source_revision": trait["source_revision"],
            }
        )
        for display_order, item in enumerate(selected, start=1):
            source_item_id = item["stable_source_item_id"]
            if source_item_id in used_source_ids:
                raise PersonaReviewPacketError(f"sampled source item is not global-unique: {source_item_id}")
            used_source_ids.add(source_item_id)
            review_item_id = anonymous_review_item_id(source_item_id, sampling_contract)
            if review_item_id in used_anonymous_ids:
                raise PersonaReviewPacketError(f"anonymous item ID collision: {review_item_id}")
            used_anonymous_ids.add(review_item_id)
            statement = _read_source_statement(source_root, trait, item)
            direction = item["answer_matching_behavior"].strip()
            direction_counts[direction] += 1
            packet_rows.append(
                {
                    "schema_id": PACKET_SCHEMA_ID,
                    "candidate_anonymous_id": anonymous_trait,
                    "review_item_anonymous_id": review_item_id,
                    "display_order_within_candidate": display_order,
                    "review_question": "Would a persona matching this candidate be likely to endorse this statement?",
                    "statement": statement,
                    "response_options": ["Yes", "No"],
                    "persona_consistent_response": direction,
                    "rubric_id": RUBRIC_ID,
                    "exposure_status": EXPOSURE_STATUS,
                }
            )
            exposure_rows.append(
                {
                    "stable_source_item_id": source_item_id,
                    "candidate_trait_id": trait_id,
                    "candidate_anonymous_id": anonymous_trait,
                    "review_item_anonymous_id": review_item_id,
                    "statement_sha256": item["statement_sha256"],
                    "normalized_statement_sha256": item["normalized_statement_sha256"],
                    "source_path": trait["source_path"],
                    "source_line_number": item["source_line_number"],
                    "persona_consistent_response": direction,
                    "exposure_status": EXPOSURE_STATUS,
                    "allowed_future_persona_item_roles": [ALLOWED_ROLE],
                    "forbidden_future_persona_item_roles": sorted(FORBIDDEN_ROLES),
                }
            )
        if direction_counts != {"Yes": 48, "No": 48}:
            raise PersonaReviewPacketError(
                f"{trait_id} sample balance differs from 48 matching-Yes / 48 matching-No"
            )

    expected_rows = sampling_contract["candidates"] * sampling_contract["items_per_candidate"]
    if len(packet_rows) != expected_rows or len(exposure_rows) != expected_rows:
        raise PersonaReviewPacketError("packet/exposure row count does not equal 2,304")
    forbidden_packet_keys = {
        "candidate_trait_id", "candidate_family_id", "family_id", "source_trait_slug",
        "trait_slug", "source_path", "source_revision", "source_line_number",
        "stable_source_item_id", "raw_line_sha256",
    }
    if any(forbidden_packet_keys.intersection(row) for row in packet_rows):
        raise PersonaReviewPacketError("rater-facing packet leaks a source identity field")

    rubric = _rubric_payload(
        config,
        config_sha,
        umbrella_persona,
        contract_projection,
        contract_projection_sha,
    )
    validate_persona_relevant_contract_binding(rubric, umbrella)
    rubric_bytes = _yaml_bytes(rubric)
    packet_bytes = _jsonl_bytes(packet_rows)
    packet_manifest = {
        "schema_id": "lps-v2.3-g1-persona-semantic-review-packet-manifest-v1",
        "implementation_status": PREPARATION_STATUS,
        "g1_gate_status": "OPEN_NOT_G1_PASS",
        "execution_authorized": False,
        "contains_target_model_data": False,
        "selection_outcome_blind": True,
        "config_sha256": config_sha,
        **contract_binding,
        "candidate_pool_sha256": sha256_bytes(candidate_raw),
        "duplicate_audit_sha256": sha256_bytes(duplicate_raw),
        "rubric_sha256": sha256_bytes(rubric_bytes),
        "blinded_packet_path": config["output_paths"]["blinded_packet"],
        "blinded_packet_sha256": sha256_bytes(packet_bytes),
        "blinded_packet_schema_id": PACKET_SCHEMA_ID,
        "candidate_count": len(candidate_map),
        "rows_per_candidate": sampling_contract["items_per_candidate"],
        "row_count": len(packet_rows),
        "candidate_group_order": "domain-separated SHA256 rank; not source-trait order",
        "rater_facing_identity_fields_present": False,
        "ratings_present": False,
        "rater_model_identities_present": False,
        "redistribution_notice": config["redistribution_notice"],
        "license_evidence_bindings": license_evidence_bindings,
        "g1_passed": False,
    }
    validate_persona_relevant_contract_binding(packet_manifest, umbrella)
    packet_manifest_bytes = _yaml_bytes(packet_manifest)
    exposure = {
        "schema_id": "lps-v2.3-g1-persona-semantic-review-exposure-v1",
        "implementation_status": PREPARATION_STATUS,
        "g1_gate_status": "OPEN_NOT_G1_PASS",
        "execution_authorized": False,
        "contains_target_model_data": False,
        "selection_outcome_blind": True,
        "config_sha256": config_sha,
        **contract_binding,
        "candidate_pool_sha256": sha256_bytes(candidate_raw),
        "duplicate_audit_sha256": sha256_bytes(duplicate_raw),
        "rubric_sha256": sha256_bytes(rubric_bytes),
        "packet_manifest_sha256": sha256_bytes(packet_manifest_bytes),
        "blinded_packet_sha256": sha256_bytes(packet_bytes),
        "redistribution_notice": config["redistribution_notice"],
        "access_boundary": {
            "rater_facing_packet_contains_this_mapping": False,
            "do_not_supply_this_ledger_to_semantic_raters": True,
            "reason": "preserve candidate trait/source/family blinding",
        },
        "sampling_contract": sampling_contract,
        "exposure_status": EXPOSURE_STATUS,
        "permanent_allowed_future_persona_item_roles": [ALLOWED_ROLE],
        "permanent_forbidden_future_persona_item_roles": sorted(FORBIDDEN_ROLES),
        "candidate_count": len(candidate_map),
        "exposed_item_count": len(exposure_rows),
        "candidate_identity_map": candidate_map,
        "exposed_items": exposure_rows,
        "ratings_present": False,
        "rater_model_identities_present": False,
        "g1_passed": False,
    }
    validate_persona_relevant_contract_binding(exposure, umbrella)
    exposure_bytes = _yaml_bytes(exposure)
    audit = {
        "schema_id": "lps-v2.3-g1-persona-semantic-review-packet-audit-v1",
        "implementation_status": PREPARATION_STATUS,
        "overall_status": "PACKET_PREPARED_REVIEWS_NOT_RUN",
        "g1_ready": False,
        "execution_authorized": False,
        "target_model_outcomes_observed": False,
        "config_sha256": config_sha,
        **contract_binding,
        "input_sha256": {
            "candidate_pool": sha256_bytes(candidate_raw),
            "duplicate_audit": sha256_bytes(duplicate_raw),
        },
        "output_sha256": {
            "rubric": sha256_bytes(rubric_bytes),
            "packet_manifest": sha256_bytes(packet_manifest_bytes),
            "exposure_ledger": sha256_bytes(exposure_bytes),
            "blinded_packet": sha256_bytes(packet_bytes),
        },
        "counts": {
            "candidate_traits": len(candidate_map),
            "items_per_candidate": sampling_contract["items_per_candidate"],
            "matching_yes_per_candidate": sampling_contract["matching_yes_per_candidate"],
            "matching_no_per_candidate": sampling_contract["matching_no_per_candidate"],
            "blinded_packet_rows": len(packet_rows),
            "exposed_definition_only_items": len(exposure_rows),
            "primary_rater_slots_unassigned": 3,
            "adjudicator_slots_unassigned": 1,
            "ratings_present": 0,
        },
        "packet_identity_field_audit": {
            "forbidden_keys": sorted(forbidden_packet_keys),
            "rows_with_forbidden_keys": 0,
            "result": "PASS",
        },
        "redistribution_notice_present": True,
        "remaining_before_persona_catalog_freeze": [
            "assign three primary raters from distinct base-model families",
            "assign a fourth distinct-base-model-family adjudicator",
            "collect blinded scalar reviews without target-model outcomes",
            "run the frozen pairwise relation audit",
            "apply acceptance, family-size, and shortfall/amendment rules",
        ],
    }
    validate_persona_relevant_contract_binding(audit, umbrella)
    audit_bytes = _json_bytes(audit)
    paths = config["output_paths"]
    outputs = {
        output_root / paths["rubric"]: rubric_bytes,
        output_root / paths["packet_manifest"]: packet_manifest_bytes,
        output_root / paths["exposure_ledger"]: exposure_bytes,
        output_root / paths["blinded_packet"]: packet_bytes,
        output_root / paths["build_audit"]: audit_bytes,
    }
    for path, value in outputs.items():
        _write(path, value)
    return {
        "implementation_status": PREPARATION_STATUS,
        "g1_ready": False,
        "candidate_count": len(candidate_map),
        "packet_rows": len(packet_rows),
        "matching_yes_rows": sum(row["persona_consistent_response"] == "Yes" for row in packet_rows),
        "matching_no_rows": sum(row["persona_consistent_response"] == "No" for row in packet_rows),
        "outputs": {
            str(path.relative_to(output_root)): sha256_bytes(value)
            for path, value in outputs.items()
        },
    }


def verify_tracked_persona_review_assets(project_root: Path) -> dict[str, Any]:
    """Fail closed unless tracked Persona assets and scoped contract agree."""

    project_root = project_root.resolve()
    config_path = project_root / "configs" / CONFIG_FILENAME
    config_raw = config_path.read_bytes()
    config = _load_yaml(config_path)
    _validate_config(config)
    config_sha = sha256_bytes(config_raw)
    umbrella = _load_yaml(project_root / "configs" / UMBRELLA_CONFIG_FILENAME)
    _validate_umbrella_contract(
        umbrella,
        implementation_config_sha256=config_sha,
        sampling_contract=config["sampling_contract"],
    )
    paths = config["output_paths"]
    rubric_path = project_root / paths["rubric"]
    packet_manifest_path = project_root / paths["packet_manifest"]
    exposure_path = project_root / paths["exposure_ledger"]
    packet_path = project_root / paths["blinded_packet"]
    audit_path = project_root / paths["build_audit"]
    rubric = _load_yaml(rubric_path)
    packet_manifest = _load_yaml(packet_manifest_path)
    exposure = _load_yaml(exposure_path)
    audit = json.loads(audit_path.read_bytes())
    if not isinstance(audit, dict):
        raise PersonaReviewPacketError("Persona packet audit must be a mapping")
    for payload in (rubric, packet_manifest, exposure, audit):
        if payload.get("implementation_status") != PREPARATION_STATUS:
            raise PersonaReviewPacketError("tracked Persona asset is not PREPARATION")
        validate_persona_relevant_contract_binding(payload, umbrella)
    expected_license_bindings = _license_evidence_bindings(project_root)
    if packet_manifest.get("license_evidence_bindings") != expected_license_bindings:
        raise PersonaReviewPacketError("Persona packet license-evidence binding mismatch")
    rubric_sha = sha256_bytes(rubric_path.read_bytes())
    packet_manifest_sha = sha256_bytes(packet_manifest_path.read_bytes())
    exposure_sha = sha256_bytes(exposure_path.read_bytes())
    packet_sha = sha256_bytes(packet_path.read_bytes())
    expected_hashes = (
        (packet_manifest.get("rubric_sha256"), rubric_sha, "manifest rubric"),
        (
            packet_manifest.get("blinded_packet_sha256"),
            packet_sha,
            "manifest blinded packet",
        ),
        (exposure.get("rubric_sha256"), rubric_sha, "exposure rubric"),
        (
            exposure.get("packet_manifest_sha256"),
            packet_manifest_sha,
            "exposure packet manifest",
        ),
        (exposure.get("blinded_packet_sha256"), packet_sha, "exposure packet"),
        (
            audit.get("output_sha256", {}).get("exposure_ledger"),
            exposure_sha,
            "audit exposure ledger",
        ),
        (
            audit.get("output_sha256", {}).get("packet_manifest"),
            packet_manifest_sha,
            "audit packet manifest",
        ),
    )
    for expected, observed, label in expected_hashes:
        if expected != observed:
            raise PersonaReviewPacketError(f"tracked {label} SHA256 mismatch")
    packet_rows = sum(1 for line in packet_path.read_bytes().splitlines() if line)
    if packet_rows != 2_304 or packet_manifest.get("row_count") != 2_304:
        raise PersonaReviewPacketError("tracked Persona packet row count mismatch")
    return {
        "implementation_status": PREPARATION_STATUS,
        "g1_ready": False,
        "verified_only": True,
        "candidate_count": packet_manifest.get("candidate_count"),
        "packet_rows": packet_rows,
        "contract_projection_sha256": canonical_data_sha256(
            persona_relevant_contract_projection(umbrella)
        ),
    }


__all__ = [
    "ALLOWED_ROLE", "AUDIT_FILENAME", "CONFIG_FILENAME", "EXPOSURE_FILENAME",
    "EXPOSURE_STATUS", "FORBIDDEN_ROLES", "PACKET_FILENAME", "PREPARATION_STATUS",
    "PACKET_MANIFEST_FILENAME", "PersonaReviewPacketError", "RUBRIC_FILENAME", "anonymous_candidate_id",
    "anonymous_review_item_id", "build_persona_review_assets", "sampling_rank",
    "candidate_display_rank", "select_review_items", "validate_future_persona_item_roles",
    "persona_relevant_contract_projection",
    "validate_persona_relevant_contract_binding",
    "verify_tracked_persona_review_assets",
    "PERSONA_RELEVANT_CONTRACT_PROJECTION_SCHEMA",
    "THIRD_PARTY_NOTICE_PATH", "ANTHROPIC_LICENSE_EVIDENCE_PATH",
    "EXPECTED_THIRD_PARTY_NOTICE_SHA256",
    "EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256",
]
