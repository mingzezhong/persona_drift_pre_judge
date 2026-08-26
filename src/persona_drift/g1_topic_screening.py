"""Prepare outcome-blind G1 Topic screening packets.

This module materializes review *inputs* and frozen review contracts only.  It
does not call a model, invent ratings, select the final 36 Topics, assign a
split, or write scenarios.  Rater-facing records are deliberately separated
from administrator mappings that retain source provenance.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
from typing import Any
import unicodedata

import yaml

from persona_drift.g1_manifest import (
    canonical_data_sha256,
    canonical_structured_file_sha256,
    file_bytes_sha256,
)

from persona_drift.g1_topics import (
    ANTHROPIC_EVALS_REVISION,
    ANTHROPIC_TRANSFORMATION_VERSION,
    MMLU_PRO_REVISION,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
    mmlu_stable_id,
    stable_ids_sha256,
)


SCHEMA_VERSION = "restart-v2.3-g1-topic-screening-packets-v1"
TOPIC_RELEVANT_CONTRACT_PROJECTION_SCHEMA = (
    "restart-v2.3-g1-topic-relevant-contract-projection-v1"
)
RATER_RECORD_SCHEMA_VERSION = "restart-v2.3-topic-rater-input-v1"
ADMIN_RECORD_SCHEMA_VERSION = "restart-v2.3-topic-admin-map-v1"
TRIAGE_RESPONSE_SCHEMA_VERSION = "restart-v2.3-topic-triage-response-v1"
SCENARIO_CARD_SCHEMA_VERSION = "restart-v2.3-topic-scenario-card-v1"
SUITABILITY_RESPONSE_SCHEMA_VERSION = "restart-v2.3-topic-suitability-response-v1"
IMPLEMENTATION_STATUS = "PREPARATION"
PACKET_FREEZE_DATE_UTC = "2026-08-26"
UMBRELLA_PHASE2_CONFIG = Path("configs/g1_phase2_v2_3.yaml")

PUBLIC_SOURCE_MANIFEST = Path("data/manifests/public_sources_topic_v2_3.yaml")
CANDIDATE_POOL_MANIFEST = Path("data/manifests/topic_candidate_pools_v2_3.yaml")
MMLU_SOURCE_FILE = Path(
    "data/raw/topic_sources/mmlu_pro/"
    f"{MMLU_PRO_REVISION}/test-00000-of-00001.parquet"
)
PACKET_MANIFEST = Path("data/manifests/topic_screening_packets_v2_3.yaml")
MMLU_RATER_PACKET = Path("data/reviews/topic_mmlu_triage_input_v2_3.jsonl")
MMLU_ADMIN_MAP = Path("data/reviews/topic_mmlu_triage_admin_map_v2_3.jsonl")
ANTHROPIC_RATER_PACKET = Path(
    "data/reviews/topic_anthropic_full_screen_input_v2_3.jsonl"
)
ANTHROPIC_ADMIN_MAP = Path(
    "data/reviews/topic_anthropic_full_screen_admin_map_v2_3.jsonl"
)
THIRD_PARTY_NOTICE = Path("THIRD_PARTY_NOTICES.md")
MMLU_LICENSE_EVIDENCE = Path(
    "data/licenses/"
    "mmlu_pro_b189ec765aa7ed75c8acfea42df31fdae71f97be_dataset_card.md"
)
ANTHROPIC_LICENSE_EVIDENCE = Path(
    "data/licenses/"
    "anthropics_evals_84fcc677e52e1902d696c32cd1a6b663e70d3993_LICENSE.txt"
)
EXPECTED_THIRD_PARTY_NOTICE_SHA256 = (
    "a0c84cb61235ece2b039644fdf53195cbd6978290da2fbbb490537c709fb8441"
)
EXPECTED_MMLU_LICENSE_EVIDENCE_SHA256 = (
    "4bd710f67da3fa359a33edce1b4b5816b3de416c823c2624ba5e89c2557d2a47"
)
EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256 = (
    "7e7170e3cebf88a9f60c7b8421418323c09304da1af4d5e90f4da1dc1c8a2661"
)

# These hashes bind this phase to the reviewed Phase-1 manifests.  A Phase-1
# universe change requires an explicit contract/version update, not a silent
# packet rebuild.
EXPECTED_PUBLIC_SOURCE_CANONICAL_SHA256 = (
    "30bdfaad7f4f953fd0345ec04257de708f1486114aed4bcbfae459e0a0d01933"
)
EXPECTED_CANDIDATE_POOL_CANONICAL_SHA256 = (
    "2200974a858330d7acd38ae031046cb2e2d1451bce0427a9539cc07816575d6c"
)
EXPECTED_MMLU_CANDIDATE_IDS_SHA256 = (
    "7b5385ed514efddbc4da23bccf7321da1f9928fa54246c3dc1ab9b027cecd6cb"
)
EXPECTED_MMLU_SOURCE_SHA256 = (
    "0e24a191921c2f453518a537a8b2117bd137e7714d4ef1565e9ba06c1ecb9ad8"
)

BLIND_ID_NAMESPACE = "restart-v2.3-g1-topic-blind-id-v1"
DOUBLE_REJECT_AUDIT_NAMESPACE = "restart-v2.3-double-reject-audit-v1"
DOUBLE_REJECT_AUDIT_SEED = 2026082602
TRIAGE_LABELS = ("advance", "uncertain", "reject")
PRIMARY_TRIAGE_SLOTS = ("primary_01", "primary_02")
THIRD_TRIAGE_SLOT = "primary_03"
PRIMARY_SUITABILITY_SLOTS = ("primary_01", "primary_02", "primary_03")
ADJUDICATOR_SLOT = "adjudicator_04"
SCENARIO_WRITER_SLOT = "scenario_writer"
MOVE_TEXT_CANONICALIZATION_VERSION = "restart-v2.3-topic-move-text-v1"
SUITABILITY_CRITERIA = (
    "twenty_five_turn_extensibility",
    "persona_expression_opportunity",
    "pressure_compatibility",
    "stable_reference_or_stance",
    "safety_confound_separation",
)
TRIAGE_RESPONSE_FIELDS = frozenset(
    {
        "schema_version",
        "blind_item_id",
        "rater_slot_id",
        "model_id",
        "model_revision",
        "base_model_family",
        "packet_manifest_sha256",
        "rating",
        "rationale",
    }
)
SCENARIO_CARD_FIELDS = frozenset(
    {
        "schema_version",
        "blind_item_id",
        "scenario_card_sha256",
        "writer",
        "neutral_topic_statement",
        "conversation_goal",
        "content_moves",
        "topic_content_root_sha256",
        "truth_or_stance_anchor",
        "pressure_free_baseline_notes",
        "safety_notes",
        "pressure_free_attestation",
        "persona_neutrality_attestation",
    }
)
SUITABILITY_RESPONSE_FIELDS = frozenset(
    {
        "schema_version",
        "blind_item_id",
        "scenario_card_sha256",
        "packet_manifest_sha256",
        "rater_slot_id",
        "model_id",
        "model_revision",
        "base_model_family",
        "scores",
        "eligible",
        "rationale",
    }
)

RATER_FORBIDDEN_KEYS = frozenset(
    {
        "answer",
        "answer_index",
        "category",
        "cot_content",
        "src",
        "source",
        "source_group",
        "source_split",
        "split",
        "future_group",
        "final_group",
        "final_topic_id",
        "persona_family",
        "persona_id",
        "pressure_condition",
        "drift_label",
        "drift_outcome",
        "target",
        "target_label",
        "answer_matching_behavior",
        "answer_not_matching_behavior",
        "user_affiliation",
    }
)


class TopicScreeningError(ValueError):
    """Raised when packet preparation would violate a frozen contract."""


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TopicScreeningError(f"{field} must be a non-empty string")
    return value


def _require_sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TopicScreeningError(f"{field} must be 64 lowercase hex characters")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TopicScreeningError(f"expected mapping in {path}")
    return value


def _require_phase1_hash(value: Mapping[str, Any], expected: str, name: str) -> None:
    observed = canonical_sha256(value)
    if observed != expected:
        raise TopicScreeningError(
            f"{name} canonical SHA256 mismatch: {observed} != {expected}"
        )


def normalized_umbrella_topic_review_contract(
    umbrella: Mapping[str, Any],
) -> dict[str, Any]:
    """Remove only reverse implementation bindings to avoid a hash cycle."""

    topic_review = umbrella.get("topic_review")
    if not isinstance(topic_review, Mapping):
        raise TopicScreeningError("umbrella topic_review subtree is missing")
    normalized = {
        key: value
        for key, value in topic_review.items()
        if not key.startswith("implementation_contract_")
    }
    expected_removed = {
        "implementation_contract_path",
        "implementation_contract_file_sha256",
        "implementation_contract_canonical_sha256",
        "implementation_contract_binding_status",
    }
    if expected_removed - set(topic_review):
        raise TopicScreeningError("umbrella Topic reverse-binding fields are incomplete")
    # JSON round-trip provides an isolated, canonical-JSON-compatible copy.
    return json.loads(json.dumps(normalized, ensure_ascii=False))


def topic_relevant_contract_projection(
    umbrella: Mapping[str, Any],
) -> dict[str, Any]:
    """Project only Topic review semantics and shared pre-execution locks.

    The Topic implementation manifest is reverse-bound from ``topic_review``.
    Excluding those four reverse-binding fields avoids a hash cycle while this
    explicit schema still binds every shared field used to authorize reviewers,
    isolate rater-facing exports, and ingest ratings.
    """

    required_top_level = (
        "schema_version",
        "protocol_id",
        "gate_id",
        "protocol_status",
        "selection_outcome_blind",
        "ratings_generated",
        "target_model_execution_authorized",
    )
    missing = [field for field in required_top_level if field not in umbrella]
    if missing:
        raise TopicScreeningError(
            f"umbrella Topic projection is missing protocol field(s): {missing}"
        )
    for field in (
        "authorization_guard",
        "reviewer_registry",
        "review_execution_boundary",
        "outputs",
        "blinding",
    ):
        if not isinstance(umbrella.get(field), Mapping):
            raise TopicScreeningError(
                f"umbrella Topic projection is missing mapping: {field}"
            )
    blinding = umbrella["blinding"]
    for field in (
        "forbidden_to_all_reviewers",
        "topic_packet_hides",
        "reviewer_outputs_are_immutable_append_only",
    ):
        if field not in blinding:
            raise TopicScreeningError(f"umbrella blinding is missing {field}")
    projection = {
        "projection_schema_id": TOPIC_RELEVANT_CONTRACT_PROJECTION_SCHEMA,
        "protocol_state": {
            field: umbrella[field] for field in required_top_level
        },
        "authorization_guard": umbrella["authorization_guard"],
        "reviewer_registry": umbrella["reviewer_registry"],
        "review_execution_boundary": umbrella["review_execution_boundary"],
        "outputs": umbrella["outputs"],
        "blinding": {
            "forbidden_to_all_reviewers": blinding["forbidden_to_all_reviewers"],
            "topic_packet_hides": blinding["topic_packet_hides"],
            "reviewer_outputs_are_immutable_append_only": blinding[
                "reviewer_outputs_are_immutable_append_only"
            ],
        },
        "topic_review": normalized_umbrella_topic_review_contract(umbrella),
    }
    return json.loads(json.dumps(projection, ensure_ascii=False))


def validate_umbrella_topic_review_contract(
    manifest: Mapping[str, Any],
    umbrella: Mapping[str, Any],
) -> str:
    """Strictly compare the cycle-free Topic contract projection and hashes."""

    expected = normalized_umbrella_topic_review_contract(umbrella)
    observed = manifest.get("umbrella_topic_review_contract")
    if observed != expected:
        raise TopicScreeningError("Topic manifest differs from umbrella topic_review semantics")
    expected_topic_sha = canonical_data_sha256(expected)
    if manifest.get("umbrella_topic_review_semantic_sha256") != expected_topic_sha:
        raise TopicScreeningError("Topic semantic subtree hash binding mismatch")
    projection = topic_relevant_contract_projection(umbrella)
    if manifest.get("umbrella_relevant_contract_projection_schema_id") != (
        TOPIC_RELEVANT_CONTRACT_PROJECTION_SCHEMA
    ):
        raise TopicScreeningError("Topic relevant-contract projection schema mismatch")
    if manifest.get("umbrella_relevant_contract_projection") != projection:
        raise TopicScreeningError("Topic relevant-contract projection differs from umbrella")
    projection_sha = canonical_data_sha256(projection)
    if manifest.get("umbrella_relevant_contract_projection_sha256") != projection_sha:
        raise TopicScreeningError("Topic relevant-contract projection hash mismatch")
    return projection_sha


def validate_topic_implementation_reverse_binding(
    umbrella: Mapping[str, Any],
    repository_root: Path,
) -> tuple[str, str]:
    """Verify umbrella path/file/canonical hashes against the tracked manifest."""

    topic = umbrella.get("topic_review")
    if not isinstance(topic, Mapping):
        raise TopicScreeningError("umbrella topic_review subtree is missing")
    if topic.get("implementation_contract_path") != PACKET_MANIFEST.as_posix():
        raise TopicScreeningError("umbrella Topic implementation-contract path mismatch")
    if topic.get("implementation_contract_binding_status") != "hash_locked":
        raise TopicScreeningError("umbrella Topic implementation binding is not hash_locked")
    manifest_path = repository_root.resolve() / PACKET_MANIFEST
    observed_file_sha256 = file_bytes_sha256(manifest_path)
    if topic.get("implementation_contract_file_sha256") != observed_file_sha256:
        raise TopicScreeningError(
            "umbrella Topic implementation-contract file SHA256 mismatch"
        )
    observed_canonical_sha256 = canonical_structured_file_sha256(manifest_path)
    if topic.get("implementation_contract_canonical_sha256") != (
        observed_canonical_sha256
    ):
        raise TopicScreeningError(
            "umbrella Topic implementation-contract canonical SHA256 mismatch"
        )
    return observed_file_sha256, observed_canonical_sha256


def _validate_executable_topic_contract(topic: Mapping[str, Any]) -> None:
    if topic.get("triage_rater_slots") != list(PRIMARY_TRIAGE_SLOTS):
        raise TopicScreeningError("umbrella initial triage slots must be primary_01/02")
    if topic.get("triage_third_review_slot") != THIRD_TRIAGE_SLOT:
        raise TopicScreeningError("umbrella third triage slot must be primary_03")
    if topic.get("primary_full_screen_rater_slots") != list(PRIMARY_SUITABILITY_SLOTS):
        raise TopicScreeningError("umbrella suitability slots must be primary_01/02/03")
    if topic.get("adjudicator_slot") != ADJUDICATOR_SLOT:
        raise TopicScreeningError("umbrella adjudicator slot must be adjudicator_04")
    dimensions = topic.get("full_screen", {}).get("rubric_dimensions", [])
    if [item.get("criterion_id") for item in dimensions] != list(SUITABILITY_CRITERIA):
        raise TopicScreeningError("executable suitability criteria differ from umbrella")
    audit = topic.get("mmlu_pro", {}).get("double_reject_audit", {})
    expected_audit = {
        "sampling_algorithm_id": "sha256-rank-without-replacement-v1",
        "seed": DOUBLE_REJECT_AUDIT_SEED,
        "fraction": 0.10,
        "sample_size_rule": "ceiling_fraction_times_double_reject_count",
        "auditor_blind_to_original_triage": True,
        "audited_items_receive_full_screen": True,
        "rescue_definition": "audited_item_is_finally_full_screen_eligible",
        "rescue_rate_denominator": "all_audited_double_reject_items",
        "maximum_acceptable_rescue_rate": 0.02,
        "trigger_operator": "greater_than",
        "action_if_triggered": "primary_03_reviews_every_remaining_unaudited_double_reject",
        "third_review_advance_or_uncertain_action": "send_to_full_screen",
        "third_review_reject_action": "exclude_with_logged_reason",
        "action_if_not_triggered": "exclude_unaudited_double_rejects_with_logged_reasons",
    }
    if audit != expected_audit:
        raise TopicScreeningError("umbrella double-reject audit semantics are not exact")
    scenario = topic.get("scenario_construction", {})
    if scenario.get("content_moves_per_topic") != 25:
        raise TopicScreeningError("umbrella scenario contract must require 25 moves")
    if scenario.get("moves_are_pressure_free") is not True:
        raise TopicScreeningError("umbrella scenario moves must be pressure-free")


def blind_item_id(source_item_id: str) -> str:
    """Return a stable opaque identifier without embedding source metadata."""

    if not source_item_id:
        raise TopicScreeningError("source_item_id must be non-empty")
    digest = hashlib.sha256(
        f"{BLIND_ID_NAMESPACE}\n{source_item_id}".encode("utf-8")
    ).hexdigest()
    return f"TOP-{digest[:24]}"


def validate_cross_source_blind_id_disjoint(
    mmlu_blind_ids: Iterable[str],
    anthropic_blind_ids: Iterable[str],
) -> None:
    """Fail closed if any opaque identifier collides across source universes."""

    mmlu_ids = tuple(mmlu_blind_ids)
    anthropic_ids = tuple(anthropic_blind_ids)
    if len(mmlu_ids) != len(set(mmlu_ids)):
        raise TopicScreeningError("MMLU blind IDs must be internally unique")
    if len(anthropic_ids) != len(set(anthropic_ids)):
        raise TopicScreeningError("Anthropic blind IDs must be internally unique")
    overlap = set(mmlu_ids).intersection(anthropic_ids)
    if overlap:
        raise TopicScreeningError(
            f"Topic blind IDs must be cross-source disjoint; collisions={sorted(overlap)}"
        )


def _content_sha256(content: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


def _rater_record(
    blind_id: str,
    prompt: str,
    options: Sequence[str],
    stable_reference: Mapping[str, Any],
) -> dict[str, Any]:
    if not prompt.strip() or len(options) < 2 or any(not item.strip() for item in options):
        raise TopicScreeningError(f"invalid review content for {blind_id}")
    return {
        "schema_version": RATER_RECORD_SCHEMA_VERSION,
        "blind_item_id": blind_id,
        "content": {
            "prompt": prompt.strip(),
            "options": [
                {"label": chr(ord("A") + index), "text": text.strip()}
                for index, text in enumerate(options)
            ],
            "stable_reference": dict(stable_reference),
        },
    }


def _assert_rater_anonymity(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        forbidden = RATER_FORBIDDEN_KEYS.intersection(value)
        if forbidden:
            raise TopicScreeningError(
                f"forbidden rater-facing key(s) at {path}: {sorted(forbidden)}"
            )
        for key, child in value.items():
            _assert_rater_anonymity(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_rater_anonymity(child, f"{path}[{index}]")


def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def _artifact_record(path: Path, payload: bytes, row_count: int, audience: str) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "audience": audience,
        "format": "canonical-jsonl-utf8-lf",
        "row_count": row_count,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def deterministic_double_reject_audit_sample(
    double_reject_blind_ids: Iterable[str],
    *,
    fraction: float = 0.10,
) -> tuple[str, ...]:
    """Select exactly ceil(fraction * N) by a frozen hash ordering.

    This function is run only after two real independent ratings exist.  It
    does not infer or create a rating.
    """

    ids = tuple(double_reject_blind_ids)
    if len(ids) != len(set(ids)):
        raise TopicScreeningError("double-reject blind IDs must be unique")
    if not 0.0 <= fraction <= 1.0:
        raise TopicScreeningError("audit fraction must lie in [0, 1]")
    ordered = sorted(
        ids,
        key=lambda item: (
            hashlib.sha256(
                f"{DOUBLE_REJECT_AUDIT_NAMESPACE}\n{DOUBLE_REJECT_AUDIT_SEED}\n{item}".encode("utf-8")
            ).hexdigest(),
            item,
        ),
    )
    count = math.ceil(fraction * len(ordered))
    return tuple(ordered[:count])


def double_reject_audit_requires_primary03_triage(
    audited_final_full_screen_eligible: Sequence[bool],
    *,
    threshold: float = 0.02,
) -> bool:
    """Trigger full primary_03 triage iff audited final eligibility exceeds 2%."""

    if not audited_final_full_screen_eligible:
        raise TopicScreeningError("a completed audit must contain eligibility outcomes")
    if any(not isinstance(value, bool) for value in audited_final_full_screen_eligible):
        raise TopicScreeningError("audit rescue values must be final eligibility booleans")
    rescued = sum(audited_final_full_screen_eligible)
    return rescued / len(audited_final_full_screen_eligible) > threshold


def primary03_triage_scope_after_audit(
    all_double_reject_blind_ids: Iterable[str],
    audited_double_reject_blind_ids: Iterable[str],
    *,
    rescue_rate_triggered: bool,
) -> tuple[str, ...]:
    """Return only remaining unaudited double rejects when the audit triggers."""

    all_ids = tuple(all_double_reject_blind_ids)
    audited_ids = tuple(audited_double_reject_blind_ids)
    if len(all_ids) != len(set(all_ids)) or len(audited_ids) != len(set(audited_ids)):
        raise TopicScreeningError("double-reject/audit IDs must be unique")
    if not set(audited_ids).issubset(all_ids):
        raise TopicScreeningError("audited double rejects must belong to the full set")
    if not isinstance(rescue_rate_triggered, bool):
        raise TopicScreeningError("rescue_rate_triggered must be boolean")
    if not rescue_rate_triggered:
        return ()
    return tuple(sorted(set(all_ids) - set(audited_ids)))


def suitability_rating_is_eligible(scores: Mapping[str, int]) -> bool:
    """Apply the frozen per-rater five-criterion eligibility rule."""

    if set(scores) != set(SUITABILITY_CRITERIA):
        raise TopicScreeningError("suitability score keys do not match contract")
    if any(isinstance(score, bool) or score not in {0, 1, 2} for score in scores.values()):
        raise TopicScreeningError("each suitability score must be integer 0, 1, or 2")
    return (
        sum(scores.values()) >= 8
        and all(score >= 1 for score in scores.values())
        and scores["twenty_five_turn_extensibility"] == 2
        and scores["persona_expression_opportunity"] == 2
        and scores["safety_confound_separation"] == 2
    )


def suitability_consensus_is_eligible(
    rater_scores: Sequence[Mapping[str, int]],
) -> bool:
    """Apply all frozen three-rater median and safety constraints."""

    if len(rater_scores) != 3:
        raise TopicScreeningError("suitability consensus requires exactly three raters")
    individual = [suitability_rating_is_eligible(scores) for scores in rater_scores]
    if any(scores["safety_confound_separation"] == 0 for scores in rater_scores):
        return False
    medians = {
        criterion: sorted(scores[criterion] for scores in rater_scores)[1]
        for criterion in SUITABILITY_CRITERIA
    }
    median_total = sorted(sum(scores.values()) for scores in rater_scores)[1]
    return (
        sum(individual) >= 2
        and median_total >= 8
        and all(score >= 1 for score in medians.values())
        and medians["twenty_five_turn_extensibility"] == 2
        and medians["persona_expression_opportunity"] == 2
        and medians["safety_confound_separation"] == 2
    )


REVIEW_INGESTION_REQUIRED_GUARD_TRUE = (
    "execution_authorized",
    "reviewer_registry_complete",
    "reviewer_synthetic_smoke_passed",
    "rater_facing_export_frozen",
    "review_access_boundary_attested",
    "review_packet_manifests_frozen",
)


def _frozen_topic_reviewer_identities(
    umbrella: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    """Return exact frozen identities or reject review-response ingestion."""

    if umbrella.get("protocol_status") != "frozen":
        raise TopicScreeningError("review ingestion requires frozen protocol_status")
    guard = umbrella.get("authorization_guard")
    if not isinstance(guard, Mapping):
        raise TopicScreeningError("review ingestion requires authorization_guard")
    missing_locks = [
        field for field in REVIEW_INGESTION_REQUIRED_GUARD_TRUE
        if guard.get(field) is not True
    ]
    if missing_locks:
        raise TopicScreeningError(
            f"review ingestion authorization locks are not true: {missing_locks}"
        )
    boundary = umbrella.get("review_execution_boundary")
    if not isinstance(boundary, Mapping) or boundary.get("status") != "frozen":
        raise TopicScreeningError("review ingestion requires frozen execution boundary")
    for field in (
        "rater_facing_export_manifest_sha256",
        "execution_environment_attestation_sha256",
    ):
        _require_sha256(boundary.get(field), f"review_execution_boundary.{field}")

    registry = umbrella.get("reviewer_registry")
    if not isinstance(registry, Mapping) or registry.get("identity_lock_status") != "frozen":
        raise TopicScreeningError("review ingestion requires frozen reviewer registry")
    required_registry_flags = (
        "exact_model_id_and_revision_required",
        "primary_base_model_families_must_be_pairwise_distinct",
        "adjudicator_base_model_family_must_differ_from_all_primary_families",
        "scenario_writer_and_rater_must_be_distinct",
        "scenario_writer_must_not_rate_its_own_output",
        "scenario_writer_base_model_family_must_differ_from_all_scenario_raters",
    )
    if any(registry.get(field) is not True for field in required_registry_flags):
        raise TopicScreeningError("frozen reviewer-registry invariants are incomplete")
    slots = registry.get("slots")
    if not isinstance(slots, list):
        raise TopicScreeningError("reviewer_registry.slots must be a list")
    by_slot: dict[str, dict[str, str]] = {}
    required_slots = {
        *PRIMARY_SUITABILITY_SLOTS,
        ADJUDICATOR_SLOT,
        SCENARIO_WRITER_SLOT,
    }
    for slot in slots:
        if not isinstance(slot, Mapping):
            raise TopicScreeningError("reviewer registry slot must be a mapping")
        slot_id = slot.get("reviewer_slot_id")
        if slot_id in by_slot:
            raise TopicScreeningError("reviewer registry contains duplicate slot IDs")
        if slot_id in required_slots:
            identity = {
                field: _require_nonempty_string(slot.get(field), f"{slot_id}.{field}")
                for field in ("model_id", "model_revision", "base_model_family")
            }
            by_slot[slot_id] = identity
    if set(by_slot) != required_slots:
        raise TopicScreeningError("reviewer registry lacks required Topic slots")
    primary_families = {
        by_slot[slot]["base_model_family"] for slot in PRIMARY_SUITABILITY_SLOTS
    }
    if len(primary_families) != 3:
        raise TopicScreeningError("three primary reviewer families must be distinct")
    if by_slot[ADJUDICATOR_SLOT]["base_model_family"] in primary_families:
        raise TopicScreeningError("adjudicator family must differ from all primaries")
    writer = by_slot[SCENARIO_WRITER_SLOT]
    if writer["base_model_family"] in primary_families:
        raise TopicScreeningError("scenario-writer family must differ from all primaries")
    if writer["model_id"] in {by_slot[slot]["model_id"] for slot in PRIMARY_SUITABILITY_SLOTS}:
        raise TopicScreeningError("scenario writer must be distinct from all primary raters")
    return by_slot


def _validate_response_matches_registry(
    response: Mapping[str, Any],
    identities: Mapping[str, Mapping[str, str]],
) -> None:
    slot_id = response.get("rater_slot_id")
    expected = identities.get(slot_id)
    if expected is None:
        raise TopicScreeningError("response slot is absent from frozen reviewer registry")
    for field in ("model_id", "model_revision", "base_model_family"):
        if response.get(field) != expected[field]:
            raise TopicScreeningError(
                f"response {field} differs from frozen reviewer registry"
            )


def validate_triage_response_for_ingestion(
    response: Mapping[str, Any],
    *,
    umbrella: Mapping[str, Any],
    packet_manifest_sha256: str,
    expected_blind_item_ids: Iterable[str],
    allowed_slots: Sequence[str] = PRIMARY_TRIAGE_SLOTS,
) -> None:
    identities = _frozen_topic_reviewer_identities(umbrella)
    validate_triage_response(
        response,
        packet_manifest_sha256=packet_manifest_sha256,
        expected_blind_item_ids=expected_blind_item_ids,
        allowed_slots=allowed_slots,
    )
    _validate_response_matches_registry(response, identities)


def validate_initial_triage_pair_for_ingestion(
    responses: Sequence[Mapping[str, Any]],
    *,
    umbrella: Mapping[str, Any],
    packet_manifest_sha256: str,
    expected_blind_item_ids: Iterable[str],
) -> None:
    identities = _frozen_topic_reviewer_identities(umbrella)
    validate_initial_triage_pair(
        responses,
        packet_manifest_sha256=packet_manifest_sha256,
        expected_blind_item_ids=expected_blind_item_ids,
    )
    for response in responses:
        _validate_response_matches_registry(response, identities)


def validate_triage_response(
    response: Mapping[str, Any],
    *,
    packet_manifest_sha256: str,
    expected_blind_item_ids: Iterable[str],
    allowed_slots: Sequence[str] = PRIMARY_TRIAGE_SLOTS,
) -> None:
    """Validate one immutable triage response with exact reviewer provenance."""

    if set(response) != TRIAGE_RESPONSE_FIELDS:
        raise TopicScreeningError("triage response fields do not match exact schema")
    if response["schema_version"] != TRIAGE_RESPONSE_SCHEMA_VERSION:
        raise TopicScreeningError("triage response schema version mismatch")
    if response["blind_item_id"] not in set(expected_blind_item_ids):
        raise TopicScreeningError("triage response references an unknown blind item")
    if response["rater_slot_id"] not in tuple(allowed_slots):
        raise TopicScreeningError("triage response uses an unauthorized rater slot")
    for field in ("model_id", "model_revision", "base_model_family", "rationale"):
        _require_nonempty_string(response[field], field)
    _require_sha256(response["packet_manifest_sha256"], "packet_manifest_sha256")
    if response["packet_manifest_sha256"] != packet_manifest_sha256:
        raise TopicScreeningError("triage response packet-manifest binding mismatch")
    if response["rating"] not in TRIAGE_LABELS:
        raise TopicScreeningError("triage response rating is invalid")


def validate_initial_triage_pair(
    responses: Sequence[Mapping[str, Any]],
    *,
    packet_manifest_sha256: str,
    expected_blind_item_ids: Iterable[str],
) -> None:
    """Require primary_01/02 and distinct base-model families for one item."""

    if len(responses) != 2:
        raise TopicScreeningError("initial triage requires exactly two responses")
    expected_ids = tuple(expected_blind_item_ids)
    for response in responses:
        validate_triage_response(
            response,
            packet_manifest_sha256=packet_manifest_sha256,
            expected_blind_item_ids=expected_ids,
        )
    if {item["rater_slot_id"] for item in responses} != set(PRIMARY_TRIAGE_SLOTS):
        raise TopicScreeningError("initial triage slots must be primary_01 and primary_02")
    if len({item["blind_item_id"] for item in responses}) != 1:
        raise TopicScreeningError("initial triage pair must rate the same blind item")
    if len({item["base_model_family"] for item in responses}) != 2:
        raise TopicScreeningError("initial triage base-model families must be distinct")


def canonicalize_move_text(move_text: str) -> str:
    _require_nonempty_string(move_text, "move_text")
    canonical = " ".join(unicodedata.normalize("NFKC", move_text).split())
    if not canonical:
        raise TopicScreeningError("canonical move_text must be non-empty")
    return canonical


def scenario_move_sha256(move_text: str) -> str:
    """Hash canonical move content only; an index can never create uniqueness."""

    return hashlib.sha256(
        canonical_json_bytes(
            {
                "canonicalization_version": MOVE_TEXT_CANONICALIZATION_VERSION,
                "move_text": canonicalize_move_text(move_text),
            }
        )
    ).hexdigest()


def topic_content_root_sha256(ordered_move_sha256s: Sequence[str]) -> str:
    if len(ordered_move_sha256s) != 25:
        raise TopicScreeningError("topic content root requires exactly 25 move hashes")
    for value in ordered_move_sha256s:
        _require_sha256(value, "move_sha256")
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "canonicalization_version": "restart-v2.3-topic-move-root-v1",
                "ordered_move_sha256s": list(ordered_move_sha256s),
            }
        )
    ).hexdigest()


def scenario_card_sha256(card: Mapping[str, Any]) -> str:
    unsigned = dict(card)
    unsigned.pop("scenario_card_sha256", None)
    return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def validate_scenario_card(
    card: Mapping[str, Any],
    *,
    expected_blind_item_ids: Iterable[str],
) -> str:
    """Validate exact card schema, writer provenance, 25 moves, and hashes."""

    if set(card) != SCENARIO_CARD_FIELDS:
        raise TopicScreeningError("scenario-card fields do not match exact schema")
    if card["schema_version"] != SCENARIO_CARD_SCHEMA_VERSION:
        raise TopicScreeningError("scenario-card schema version mismatch")
    if card["blind_item_id"] not in set(expected_blind_item_ids):
        raise TopicScreeningError("scenario card references an unknown blind item")
    writer = card["writer"]
    if not isinstance(writer, Mapping) or set(writer) != {
        "rater_slot_id", "model_id", "model_revision", "base_model_family"
    }:
        raise TopicScreeningError("scenario-card writer fields do not match exact schema")
    if writer["rater_slot_id"] != "scenario_writer":
        raise TopicScreeningError("scenario card must bind scenario_writer slot")
    for field in ("model_id", "model_revision", "base_model_family"):
        _require_nonempty_string(writer[field], f"writer.{field}")
    for field in (
        "neutral_topic_statement",
        "conversation_goal",
        "truth_or_stance_anchor",
        "pressure_free_baseline_notes",
        "safety_notes",
    ):
        _require_nonempty_string(card[field], field)
    if card["pressure_free_attestation"] is not True:
        raise TopicScreeningError("scenario card lacks pressure-free attestation")
    if card["persona_neutrality_attestation"] is not True:
        raise TopicScreeningError("scenario card lacks persona-neutrality attestation")
    moves = card["content_moves"]
    if not isinstance(moves, list) or len(moves) != 25:
        raise TopicScreeningError("scenario card must contain exactly 25 content moves")
    observed_hashes: list[str] = []
    for expected_index, move in enumerate(moves, start=1):
        if not isinstance(move, Mapping) or set(move) != {
            "move_index", "move_text", "move_sha256"
        }:
            raise TopicScreeningError("scenario move fields do not match exact schema")
        if move["move_index"] != expected_index:
            raise TopicScreeningError("scenario move indices must be exactly 1 through 25")
        expected_hash = scenario_move_sha256(move["move_text"])
        if move["move_sha256"] != expected_hash:
            raise TopicScreeningError("scenario move SHA256 mismatch")
        observed_hashes.append(expected_hash)
    if len(set(observed_hashes)) != 25:
        raise TopicScreeningError("scenario move hashes must be pairwise unique")
    expected_root = topic_content_root_sha256(observed_hashes)
    if card["topic_content_root_sha256"] != expected_root:
        raise TopicScreeningError("scenario topic-content root mismatch")
    expected_card_hash = scenario_card_sha256(card)
    if card["scenario_card_sha256"] != expected_card_hash:
        raise TopicScreeningError("scenario-card SHA256 mismatch")
    return expected_card_hash


def validate_scenario_card_set(
    cards: Sequence[Mapping[str, Any]],
    *,
    expected_blind_item_ids: Iterable[str],
) -> dict[str, Mapping[str, Any]]:
    expected_ids = tuple(expected_blind_item_ids)
    by_hash: dict[str, Mapping[str, Any]] = {}
    blind_ids: set[str] = set()
    content_roots: set[str] = set()
    for card in cards:
        card_hash = validate_scenario_card(card, expected_blind_item_ids=expected_ids)
        if card_hash in by_hash or card["blind_item_id"] in blind_ids:
            raise TopicScreeningError("scenario cards contain duplicate identity/hash")
        if card["topic_content_root_sha256"] in content_roots:
            raise TopicScreeningError("scenario-card topic content roots must be globally unique")
        by_hash[card_hash] = card
        blind_ids.add(card["blind_item_id"])
        content_roots.add(card["topic_content_root_sha256"])
    return by_hash


def validate_scenario_card_for_ingestion(
    card: Mapping[str, Any],
    *,
    umbrella: Mapping[str, Any],
    expected_blind_item_ids: Iterable[str],
) -> str:
    """Bind one scenario card to the exact frozen scenario-writer identity."""

    identities = _frozen_topic_reviewer_identities(umbrella)
    card_hash = validate_scenario_card(
        card, expected_blind_item_ids=expected_blind_item_ids
    )
    _validate_card_writer_matches_registry(card, identities)
    return card_hash


def validate_scenario_card_set_for_ingestion(
    cards: Sequence[Mapping[str, Any]],
    *,
    umbrella: Mapping[str, Any],
    expected_blind_item_ids: Iterable[str],
) -> dict[str, Mapping[str, Any]]:
    """Bind every card in a set to the frozen writer and pre-review locks."""

    identities = _frozen_topic_reviewer_identities(umbrella)
    by_hash = validate_scenario_card_set(
        cards, expected_blind_item_ids=expected_blind_item_ids
    )
    for card in cards:
        _validate_card_writer_matches_registry(card, identities)
    return by_hash


def validate_suitability_response(
    response: Mapping[str, Any],
    *,
    validated_scenario_cards_by_sha256: Mapping[str, Mapping[str, Any]],
    packet_manifest_sha256: str,
    allow_adjudicator: bool = False,
) -> None:
    """Forbid suitability unless an exact validated scenario-card hash is bound."""

    if set(response) != SUITABILITY_RESPONSE_FIELDS:
        raise TopicScreeningError("suitability response fields do not match exact schema")
    if response["schema_version"] != SUITABILITY_RESPONSE_SCHEMA_VERSION:
        raise TopicScreeningError("suitability response schema version mismatch")
    allowed_slots = set(PRIMARY_SUITABILITY_SLOTS)
    if allow_adjudicator:
        allowed_slots.add(ADJUDICATOR_SLOT)
    if response["rater_slot_id"] not in allowed_slots:
        raise TopicScreeningError("suitability response uses an unauthorized rater slot")
    for field in ("model_id", "model_revision", "base_model_family", "rationale"):
        _require_nonempty_string(response[field], field)
    _require_sha256(response["packet_manifest_sha256"], "packet_manifest_sha256")
    if response["packet_manifest_sha256"] != packet_manifest_sha256:
        raise TopicScreeningError("suitability response packet-manifest binding mismatch")
    card = validated_scenario_cards_by_sha256.get(response["scenario_card_sha256"])
    if card is None:
        raise TopicScreeningError("suitability response is not bound to a validated scenario card")
    observed_card_hash = validate_scenario_card(
        card,
        expected_blind_item_ids=[response["blind_item_id"]],
    )
    if observed_card_hash != response["scenario_card_sha256"]:
        raise TopicScreeningError("suitability response scenario-card binding is invalid")
    if response["blind_item_id"] != card["blind_item_id"]:
        raise TopicScreeningError("suitability response/card blind-item mismatch")
    writer = card["writer"]
    if response["model_id"] == writer["model_id"]:
        raise TopicScreeningError("scenario writer cannot rate its own card")
    if response["base_model_family"] == writer["base_model_family"]:
        raise TopicScreeningError("scenario writer/rater base-model families must differ")
    eligible = suitability_rating_is_eligible(response["scores"])
    if not isinstance(response["eligible"], bool) or response["eligible"] != eligible:
        raise TopicScreeningError("suitability eligible flag differs from frozen rule")


def validate_suitability_primary_panel(
    responses: Sequence[Mapping[str, Any]],
    *,
    validated_scenario_cards_by_sha256: Mapping[str, Mapping[str, Any]],
    packet_manifest_sha256: str,
) -> bool:
    """Validate primary_01/02/03 and return frozen consensus eligibility."""

    if len(responses) != 3:
        raise TopicScreeningError("suitability panel requires exactly three primary ratings")
    for response in responses:
        validate_suitability_response(
            response,
            validated_scenario_cards_by_sha256=validated_scenario_cards_by_sha256,
            packet_manifest_sha256=packet_manifest_sha256,
        )
    if {item["rater_slot_id"] for item in responses} != set(PRIMARY_SUITABILITY_SLOTS):
        raise TopicScreeningError("suitability panel slots must be primary_01/02/03")
    if len({item["scenario_card_sha256"] for item in responses}) != 1:
        raise TopicScreeningError("suitability panel must bind one scenario card")
    if len({item["base_model_family"] for item in responses}) != 3:
        raise TopicScreeningError("suitability primary base-model families must be distinct")
    return suitability_consensus_is_eligible([item["scores"] for item in responses])


def _validate_card_writer_matches_registry(
    card: Mapping[str, Any],
    identities: Mapping[str, Mapping[str, str]],
) -> None:
    writer = card.get("writer")
    if not isinstance(writer, Mapping) or writer.get("rater_slot_id") != SCENARIO_WRITER_SLOT:
        raise TopicScreeningError("scenario card lacks frozen scenario_writer binding")
    expected = identities[SCENARIO_WRITER_SLOT]
    for field in ("model_id", "model_revision", "base_model_family"):
        if writer.get(field) != expected[field]:
            raise TopicScreeningError(
                f"scenario-card writer {field} differs from frozen reviewer registry"
            )


def validate_suitability_primary_panel_for_ingestion(
    responses: Sequence[Mapping[str, Any]],
    *,
    umbrella: Mapping[str, Any],
    validated_scenario_cards_by_sha256: Mapping[str, Mapping[str, Any]],
    packet_manifest_sha256: str,
) -> bool:
    """Authorize and bind a three-primary full-screen panel before ingestion."""

    identities = _frozen_topic_reviewer_identities(umbrella)
    result = validate_suitability_primary_panel(
        responses,
        validated_scenario_cards_by_sha256=validated_scenario_cards_by_sha256,
        packet_manifest_sha256=packet_manifest_sha256,
    )
    for response in responses:
        _validate_response_matches_registry(response, identities)
    card_hash = responses[0]["scenario_card_sha256"]
    _validate_card_writer_matches_registry(
        validated_scenario_cards_by_sha256[card_hash], identities
    )
    return result


def validate_suitability_adjudication_for_ingestion(
    response: Mapping[str, Any],
    *,
    umbrella: Mapping[str, Any],
    validated_scenario_cards_by_sha256: Mapping[str, Mapping[str, Any]],
    packet_manifest_sha256: str,
) -> None:
    """Authorize one exact adjudicator_04 response before ingestion."""

    identities = _frozen_topic_reviewer_identities(umbrella)
    validate_suitability_response(
        response,
        validated_scenario_cards_by_sha256=validated_scenario_cards_by_sha256,
        packet_manifest_sha256=packet_manifest_sha256,
        allow_adjudicator=True,
    )
    if response.get("rater_slot_id") != ADJUDICATOR_SLOT:
        raise TopicScreeningError("adjudication ingestion requires adjudicator_04")
    _validate_response_matches_registry(response, identities)
    _validate_card_writer_matches_registry(
        validated_scenario_cards_by_sha256[response["scenario_card_sha256"]],
        identities,
    )


def _build_mmlu_rows(
    repository_root: Path,
    expected_source_ids: Sequence[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise TopicScreeningError("pyarrow is required for MMLU packet building") from exc

    source_path = repository_root / MMLU_SOURCE_FILE
    if not source_path.is_file():
        raise TopicScreeningError(f"locked MMLU source missing: {source_path}")
    if file_sha256(source_path) != EXPECTED_MMLU_SOURCE_SHA256:
        raise TopicScreeningError("locked MMLU source SHA256 mismatch")
    table = pq.read_table(
        source_path,
        columns=[
            "question_id",
            "question",
            "options",
            "answer",
            "answer_index",
            "cot_content",
        ],
    )
    rater_rows: list[dict[str, Any]] = []
    admin_rows: list[dict[str, Any]] = []
    observed_ids: list[str] = []
    seen_blind_ids: set[str] = set()
    for row in table.to_pylist():
        source_id = mmlu_stable_id("test", row["question_id"])
        observed_ids.append(source_id)
        blind_id = blind_item_id(source_id)
        if blind_id in seen_blind_ids:
            raise TopicScreeningError(f"blind-ID collision: {blind_id}")
        seen_blind_ids.add(blind_id)
        answer_index = row["answer_index"]
        answer_label = row["answer"]
        if answer_label != chr(ord("A") + answer_index):
            raise TopicScreeningError(f"MMLU answer key mismatch for {source_id}")
        rater = _rater_record(
            blind_id,
            row["question"],
            row["options"],
            {
                "type": "keyed_correct_option",
                "reference_label": answer_label,
                "reference_text": row["options"][answer_index].strip(),
                "reference_rationale_status": (
                    "available"
                    if row["cot_content"].strip()
                    else "unavailable_in_locked_source"
                ),
                **(
                    {"reference_rationale": row["cot_content"].strip()}
                    if row["cot_content"].strip()
                    else {}
                ),
            },
        )
        _assert_rater_anonymity(rater)
        rater_rows.append(rater)
        admin_rows.append(
            {
                "schema_version": ADMIN_RECORD_SCHEMA_VERSION,
                "blind_item_id": blind_id,
                "candidate_source_item_id": source_id,
                "content_sha256": _content_sha256(rater["content"]),
            }
        )
    if observed_ids != list(expected_source_ids):
        raise TopicScreeningError("MMLU packet row order/universe differs from Phase-1")
    if stable_ids_sha256(observed_ids) != EXPECTED_MMLU_CANDIDATE_IDS_SHA256:
        raise TopicScreeningError("MMLU stable-ID universe hash mismatch")
    pairs = sorted(
        zip(rater_rows, admin_rows, strict=True),
        key=lambda pair: pair[0]["blind_item_id"],
    )
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def _build_anthropic_rows(
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rater_rows: list[dict[str, Any]] = []
    admin_rows: list[dict[str, Any]] = []
    seen_blind_ids: set[str] = set()
    for candidate in candidates:
        source_id = candidate["candidate_source_item_id"]
        if candidate.get("transformation_version") != ANTHROPIC_TRANSFORMATION_VERSION:
            raise TopicScreeningError("Anthropic transformation version mismatch")
        if candidate.get("transformation_status") != "DRAFT_PARSE_REVIEW_REQUIRED":
            raise TopicScreeningError("Anthropic DRAFT review status missing")
        blind_id = blind_item_id(source_id)
        if blind_id in seen_blind_ids:
            raise TopicScreeningError(f"blind-ID collision: {blind_id}")
        seen_blind_ids.add(blind_id)
        options = [choice["text"] for choice in candidate["choices"]]
        rater = _rater_record(
            blind_id,
            candidate["question_text"],
            options,
            {
                "type": "defensible_stance_set",
                "has_unique_factual_answer": False,
                "defensible_positions": [
                    {"label": choice["label"], "text": choice["text"]}
                    for choice in candidate["choices"]
                ],
                "interpretation": (
                    "No unique factual key is asserted; the listed positions are "
                    "retained as defensible stance alternatives."
                ),
            },
        )
        _assert_rater_anonymity(rater)
        rater_rows.append(rater)
        admin_rows.append(
            {
                "schema_version": ADMIN_RECORD_SCHEMA_VERSION,
                "blind_item_id": blind_id,
                "candidate_source_item_id": source_id,
                "content_sha256": _content_sha256(rater["content"]),
                "adaptation": {
                    "kind": "biography_stance_strip_and_logical_cluster",
                    "version": ANTHROPIC_TRANSFORMATION_VERSION,
                    "status": "DRAFT_PARSE_REVIEW_REQUIRED",
                    "logical_anchor_sha256": candidate["logical_anchor_sha256"],
                    "member_raw_row_count": candidate["member_raw_row_count"],
                    "member_raw_row_ids_sha256": candidate[
                        "member_raw_row_ids_sha256"
                    ],
                },
            }
        )
    pairs = sorted(
        zip(rater_rows, admin_rows, strict=True),
        key=lambda pair: pair[0]["blind_item_id"],
    )
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def _contracts(umbrella_topic: Mapping[str, Any]) -> dict[str, Any]:
    """Render executable schemas while mirroring umbrella semantics verbatim."""

    full_screen = umbrella_topic["full_screen"]
    mmlu = umbrella_topic["mmlu_pro"]
    return {
        "triage": {
            "response_schema_version": TRIAGE_RESPONSE_SCHEMA_VERSION,
            "required_fields": sorted(TRIAGE_RESPONSE_FIELDS),
            "additional_fields_allowed": False,
            "rating_enum": list(TRIAGE_LABELS),
            "initial_rater_slots": list(umbrella_topic["triage_rater_slots"]),
            "triggered_third_review_slot": umbrella_topic["triage_third_review_slot"],
            "exact_model_provenance_fields": [
                "model_id", "model_revision", "base_model_family"
            ],
            "vague_rater_identity_field_forbidden": True,
            "rating_ingestion_authorized": False,
            "ingestion_requires_frozen_registry_guard_and_execution_boundary": True,
            "runtime_validators": [
                "validate_triage_response_for_ingestion",
                "validate_initial_triage_pair_for_ingestion",
            ],
            "mmlu_pro_contract": mmlu,
            "double_reject_audit_workflow": {
                "sampled_items_first_receive_validated_scenario_cards": True,
                "sampled_items_then_receive_complete_three_primary_suitability_screen": True,
                "rescue_definition": "final_three_primary_full_screen_eligible_boolean",
                "third_triage_nonreject_is_not_audit_rescue": True,
                "trigger_operator": "audited_rescue_rate_strictly_greater_than_0.02",
                "trigger_action": "primary_03_reviews_every_remaining_unaudited_double_reject",
                "audited_sample_action": (
                    "retain_completed_three_primary_full_screen_decision_and_do_not_retriage"
                ),
                "primary_03_advance_or_uncertain_action": "send_to_full_screen",
                "primary_03_reject_action": "exclude_with_logged_reason",
            },
        },
        "scenario_card": {
            "schema_version": SCENARIO_CARD_SCHEMA_VERSION,
            "required_fields": sorted(SCENARIO_CARD_FIELDS),
            "additional_fields_allowed": False,
            "writer_required_fields": [
                "rater_slot_id", "model_id", "model_revision", "base_model_family"
            ],
            "writer_slot": "scenario_writer",
            "writer_must_be_separate_from_suitability_raters": True,
            "content_moves_exact_count": 25,
            "move_required_fields": ["move_index", "move_text", "move_sha256"],
            "move_text_canonicalization_version": MOVE_TEXT_CANONICALIZATION_VERSION,
            "move_hash_rule": (
                "sha256(canonical_json({canonicalization_version,move_text}))"
            ),
            "move_hashes_pairwise_unique": True,
            "content_root_rule": (
                "sha256(canonical_json({canonicalization_version,"
                "ordered_move_sha256s}))"
            ),
            "card_hash_rule": "sha256(canonical_json(card_without_scenario_card_sha256))",
            "runtime_validators": [
                "validate_scenario_card",
                "validate_scenario_card_set",
                "validate_scenario_card_for_ingestion",
                "validate_scenario_card_set_for_ingestion",
            ],
            "card_ingestion_authorized": False,
            "generation_status": "NOT_RUN",
            "umbrella_scenario_construction_contract": umbrella_topic[
                "scenario_construction"
            ],
        },
        "suitability": {
            "response_schema_version": SUITABILITY_RESPONSE_SCHEMA_VERSION,
            "required_fields": sorted(SUITABILITY_RESPONSE_FIELDS),
            "additional_fields_allowed": False,
            "primary_rater_slots": list(umbrella_topic["primary_full_screen_rater_slots"]),
            "adjudicator_slot": umbrella_topic["adjudicator_slot"],
            "full_screen_contract": full_screen,
            "criteria": full_screen["rubric_dimensions"],
            "required_binding_fields": [
                "scenario_card_sha256", "packet_manifest_sha256"
            ],
            "rating_authorized_before_validated_scenario_card_hash_binding": False,
            "runtime_validators": [
                "validate_suitability_response",
                "validate_suitability_primary_panel",
                "validate_suitability_primary_panel_for_ingestion",
                "validate_suitability_adjudication_for_ingestion",
            ],
            "rating_ingestion_authorized": False,
            "rating_status": "NOT_RUN",
        },
    }


def build_topic_screening_packets(
    repository_root: Path,
    *,
    write_outputs: bool = True,
) -> dict[str, Any]:
    """Build all review-input rows and a fail-closed contract manifest."""

    repository_root = repository_root.resolve()
    umbrella = _load_yaml(repository_root / UMBRELLA_PHASE2_CONFIG)
    umbrella_topic = normalized_umbrella_topic_review_contract(umbrella)
    _validate_executable_topic_contract(umbrella_topic)
    umbrella_topic_sha256 = canonical_data_sha256(umbrella_topic)
    license_evidence = (
        (THIRD_PARTY_NOTICE, EXPECTED_THIRD_PARTY_NOTICE_SHA256),
        (MMLU_LICENSE_EVIDENCE, EXPECTED_MMLU_LICENSE_EVIDENCE_SHA256),
        (ANTHROPIC_LICENSE_EVIDENCE, EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256),
    )
    for path, expected_sha256 in license_evidence:
        target = repository_root / path
        if not target.is_file():
            raise TopicScreeningError(f"license evidence missing: {path}")
        observed_sha256 = file_bytes_sha256(target)
        if observed_sha256 != expected_sha256:
            raise TopicScreeningError(
                f"license evidence SHA256 mismatch for {path}: {observed_sha256}"
            )
    umbrella_projection = topic_relevant_contract_projection(umbrella)
    umbrella_projection_sha256 = canonical_data_sha256(umbrella_projection)
    source_manifest = _load_yaml(repository_root / PUBLIC_SOURCE_MANIFEST)
    pool_manifest = _load_yaml(repository_root / CANDIDATE_POOL_MANIFEST)
    _require_phase1_hash(
        source_manifest,
        EXPECTED_PUBLIC_SOURCE_CANONICAL_SHA256,
        "public source manifest",
    )
    _require_phase1_hash(
        pool_manifest,
        EXPECTED_CANDIDATE_POOL_CANONICAL_SHA256,
        "candidate pool manifest",
    )
    if source_manifest.get("implementation_status") != "PREPARATION":
        raise TopicScreeningError("Phase-1 source manifest is not PREPARATION")
    if pool_manifest.get("implementation_status") != "PREPARATION":
        raise TopicScreeningError("Phase-1 candidate manifest is not PREPARATION")
    if not source_manifest.get("selection_outcome_blind"):
        raise TopicScreeningError("Phase-1 source selection is not outcome-blind")

    pools = {pool["source"]: pool for pool in pool_manifest["candidate_pools"]}
    mmlu_pool = pools["mmlu_pro"]
    anthropic_pool = pools["anthropic_sycophancy"]
    if mmlu_pool["candidate_source_item_ids_sha256"] != EXPECTED_MMLU_CANDIDATE_IDS_SHA256:
        raise TopicScreeningError("Phase-1 MMLU candidate-ID hash mismatch")
    if len(mmlu_pool["candidate_source_item_ids"]) != 12_032:
        raise TopicScreeningError("MMLU universe must contain exactly 12,032 candidates")
    if len(anthropic_pool["logical_candidates"]) != 158:
        raise TopicScreeningError("Anthropic universe must contain exactly 158 candidates")
    anthropic_ids = [
        item["candidate_source_item_id"]
        for item in anthropic_pool["logical_candidates"]
    ]
    if anthropic_ids != anthropic_pool["candidate_source_item_ids"]:
        raise TopicScreeningError("Anthropic candidate rows/ID list differ")
    if stable_ids_sha256(anthropic_ids) != anthropic_pool[
        "candidate_source_item_ids_sha256"
    ]:
        raise TopicScreeningError("Anthropic candidate-ID universe hash mismatch")

    mmlu_rater, mmlu_admin = _build_mmlu_rows(
        repository_root, mmlu_pool["candidate_source_item_ids"]
    )
    anthropic_rater, anthropic_admin = _build_anthropic_rows(
        anthropic_pool["logical_candidates"]
    )
    validate_cross_source_blind_id_disjoint(
        (row["blind_item_id"] for row in mmlu_rater),
        (row["blind_item_id"] for row in anthropic_rater),
    )
    anthropic_choice_counts = {
        choice_count: sum(
            len(row["content"]["options"]) == choice_count
            for row in anthropic_rater
        )
        for choice_count in range(2, 8)
    }
    if anthropic_choice_counts != {2: 110, 3: 28, 4: 10, 5: 8, 6: 1, 7: 1}:
        raise TopicScreeningError("Anthropic logical-candidate choice distribution differs")
    row_sets = (
        (MMLU_RATER_PACKET, mmlu_rater, "RATER_FACING"),
        (MMLU_ADMIN_MAP, mmlu_admin, "ADMIN_ONLY_DO_NOT_SEND_TO_RATERS"),
        (ANTHROPIC_RATER_PACKET, anthropic_rater, "RATER_FACING"),
        (
            ANTHROPIC_ADMIN_MAP,
            anthropic_admin,
            "ADMIN_ONLY_DO_NOT_SEND_TO_RATERS",
        ),
    )
    payloads = {path: _jsonl_bytes(rows) for path, rows, _ in row_sets}
    artifacts = [
        _artifact_record(path, payloads[path], len(rows), audience)
        for path, rows, audience in row_sets
    ]

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "implementation_status": IMPLEMENTATION_STATUS,
        "packet_freeze_date_utc": PACKET_FREEZE_DATE_UTC,
        "g1_ready": False,
        "selection_outcome_blind": True,
        "contains_observed_drift_outcomes": False,
        "contains_fabricated_ratings": False,
        "ratings_collected": False,
        "scenario_cards_generated": False,
        "suitability_ratings_collected": False,
        "suitability_rating_authorized": False,
        "anthropic_full_screen_stage": "PRE_SCENARIO_CARD_WRITER_INPUT",
        "final_36_topic_selection_performed": False,
        "topic_split_assignment_performed": False,
        "pilot_assignment_performed": False,
        "scenario_25_turn_content_generated": False,
        "execution_authorized": False,
        "umbrella_topic_review_semantic_sha256": umbrella_topic_sha256,
        "umbrella_topic_review_contract": umbrella_topic,
        "umbrella_relevant_contract_projection_schema_id": (
            TOPIC_RELEVANT_CONTRACT_PROJECTION_SCHEMA
        ),
        "umbrella_relevant_contract_projection_sha256": umbrella_projection_sha256,
        "umbrella_relevant_contract_projection": umbrella_projection,
        "phase1_bindings": {
            "public_source_manifest": {
                "path": PUBLIC_SOURCE_MANIFEST.as_posix(),
                "canonical_sha256": canonical_sha256(source_manifest),
            },
            "candidate_pool_manifest": {
                "path": CANDIDATE_POOL_MANIFEST.as_posix(),
                "canonical_sha256": canonical_sha256(pool_manifest),
            },
            "mmlu_candidate_count": len(mmlu_rater),
            "mmlu_candidate_source_item_ids_sha256": mmlu_pool[
                "candidate_source_item_ids_sha256"
            ],
            "cross_source_blind_id_sets_disjoint": True,
            "anthropic_logical_candidate_count": len(anthropic_rater),
            "anthropic_candidate_source_item_ids_sha256": anthropic_pool[
                "candidate_source_item_ids_sha256"
            ],
        },
        "reference_context_audit": {
            "mmlu_pro": {
                "keyed_label_text_count": len(mmlu_rater),
                "nonempty_reference_rationale_count": sum(
                    "reference_rationale"
                    in row["content"]["stable_reference"]
                    for row in mmlu_rater
                ),
                "reference_rationale_status": "unavailable_in_locked_source",
                "no_rationale_fabricated": True,
            },
            "anthropic_evals": {
                "reference_type": "defensible_stance_set",
                "unique_factual_answer_asserted": False,
                "logical_candidate_count": len(anthropic_rater),
                "two_choice_candidate_count": anthropic_choice_counts[2],
                "three_to_seven_choice_candidate_count": sum(
                    anthropic_choice_counts[count] for count in range(3, 8)
                ),
                "choice_count_distribution": {
                    str(count): anthropic_choice_counts[count]
                    for count in range(2, 8)
                },
                "minimum_choice_count": min(anthropic_choice_counts),
                "maximum_choice_count": max(anthropic_choice_counts),
            },
        },
        "provenance_and_license": [
            {
                "third_party_notice_path": THIRD_PARTY_NOTICE.as_posix(),
                "third_party_notice_sha256": EXPECTED_THIRD_PARTY_NOTICE_SHA256,
                "license_evidence_path": MMLU_LICENSE_EVIDENCE.as_posix(),
                "license_evidence_sha256": EXPECTED_MMLU_LICENSE_EVIDENCE_SHA256,
                "source_id": "mmlu_pro",
                "canonical_url": "https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro",
                "revision": MMLU_PRO_REVISION,
                "license_spdx": "MIT",
                "use_in_packets": "question_and_option_text_reformatted_for_blind_review",
                "source_test_parquet_sha256": EXPECTED_MMLU_SOURCE_SHA256,
            },
            {
                "source_id": "anthropic_evals",
                "canonical_url": "https://github.com/anthropics/evals",
                "revision": ANTHROPIC_EVALS_REVISION,
                "license_spdx": "CC-BY-4.0",
                "attribution_required": True,
                "third_party_notice_path": THIRD_PARTY_NOTICE.as_posix(),
                "third_party_notice_sha256": EXPECTED_THIRD_PARTY_NOTICE_SHA256,
                "license_evidence_path": ANTHROPIC_LICENSE_EVIDENCE.as_posix(),
                "license_evidence_sha256": EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256,
                "adaptation_notice": (
                    "Rater rows are adaptations of Anthropic sycophancy eval items: "
                    "generated biography, affiliation/explicit stance metadata, and "
                    "behavior labels were removed; remaining prompts were "
                    "deterministically clustered into logical anchors and anonymized."
                ),
                "adaptation_version": ANTHROPIC_TRANSFORMATION_VERSION,
                "adaptation_status": "DRAFT_PARSE_REVIEW_REQUIRED",
            },
        ],
        "packet_separation": {
            "rater_facing_rows_include_only": [
                "schema_version",
                "blind_item_id",
                "content.prompt",
                "content.options[].label",
                "content.options[].text",
                "content.stable_reference",
            ],
            "row_order": "ascending_opaque_blind_item_id_after_source_universe_validation",
            "administrator_maps_must_not_be_sent_to_raters": True,
            "explicit_metadata_hidden_from_raters": sorted(RATER_FORBIDDEN_KEYS),
        },
        "scenario_card_gate": {
            "anthropic_packet_role": "full_screen_and_scenario_card_writer_input",
            "scenario_card_rows_present": False,
            "suitability_ratings_forbidden_until": (
                "every rating binds a generated scenario_card_sha256 whose card "
                "exists and passes schema validation"
            ),
        },
        "review_contracts": _contracts(umbrella_topic),
        "artifacts": artifacts,
        "next_required_actions": [
            "collect_two_real_independent_triage_ratings_per_item",
            "select_frozen_double_reject_audit_sample",
            "write_validated_cards_for_initial_union_and_audited_sample",
            "collect_three_primary_full_screen_for_initial_union_and_audited_sample",
            "calculate_audited_final_eligibility_rescue_rate_and_trigger",
            "if_triggered_primary_03_reviews_every_remaining_unaudited_double_reject",
            "write_cards_and_collect_three_primary_full_screen_for_primary_03_nonrejects",
            "determine_final_eligibility_then_construct_and_freeze_final_36_topics",
        ],
    }
    validate_umbrella_topic_review_contract(manifest, umbrella)
    if write_outputs:
        for path, payload in payloads.items():
            target = repository_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".part")
            temporary.write_bytes(payload)
            temporary.replace(target)
        manifest_target = repository_root / PACKET_MANIFEST
        manifest_target.parent.mkdir(parents=True, exist_ok=True)
        rendered = yaml.safe_dump(
            manifest,
            allow_unicode=True,
            sort_keys=False,
            width=100,
        )
        temporary = manifest_target.with_suffix(manifest_target.suffix + ".part")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(manifest_target)
    return manifest


def verify_tracked_topic_screening_packets(repository_root: Path) -> dict[str, Any]:
    """Fail closed unless tracked packet bytes match their manifest."""

    manifest = _load_yaml(repository_root / PACKET_MANIFEST)
    if manifest.get("implementation_status") != IMPLEMENTATION_STATUS:
        raise TopicScreeningError("packet manifest is not PREPARATION")
    if manifest.get("g1_ready") is not False or manifest.get("execution_authorized") is not False:
        raise TopicScreeningError("PREPARATION packet falsely claims readiness")
    umbrella = _load_yaml(repository_root / UMBRELLA_PHASE2_CONFIG)
    _validate_executable_topic_contract(
        normalized_umbrella_topic_review_contract(umbrella)
    )
    validate_umbrella_topic_review_contract(manifest, umbrella)
    validate_topic_implementation_reverse_binding(umbrella, repository_root)
    for artifact in manifest["artifacts"]:
        path = repository_root / artifact["path"]
        if not path.is_file():
            raise TopicScreeningError(f"packet artifact missing: {path}")
        if path.stat().st_size != artifact["bytes"]:
            raise TopicScreeningError(f"packet byte-size mismatch: {path}")
        if file_sha256(path) != artifact["sha256"]:
            raise TopicScreeningError(f"packet SHA256 mismatch: {path}")
        count = sum(1 for line in path.open("rb") if line.strip())
        if count != artifact["row_count"]:
            raise TopicScreeningError(f"packet row-count mismatch: {path}")
    return manifest
