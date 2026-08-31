from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import unittest

import yaml

from persona_drift.g1_manifest import canonical_structured_file_sha256

from persona_drift.g1_topic_screening import (
    ADJUDICATOR_SLOT,
    ANTHROPIC_ADMIN_MAP,
    ANTHROPIC_LICENSE_EVIDENCE,
    ANTHROPIC_RATER_PACKET,
    CANDIDATE_POOL_MANIFEST,
    EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256,
    EXPECTED_CANDIDATE_POOL_CANONICAL_SHA256,
    EXPECTED_MMLU_LICENSE_EVIDENCE_SHA256,
    EXPECTED_MMLU_CANDIDATE_IDS_SHA256,
    EXPECTED_PUBLIC_SOURCE_CANONICAL_SHA256,
    EXPECTED_THIRD_PARTY_NOTICE_SHA256,
    MMLU_ADMIN_MAP,
    MMLU_LICENSE_EVIDENCE,
    MMLU_RATER_PACKET,
    PACKET_MANIFEST,
    PRIMARY_SUITABILITY_SLOTS,
    PRIMARY_TRIAGE_SLOTS,
    PUBLIC_SOURCE_MANIFEST,
    RATER_FORBIDDEN_KEYS,
    SCENARIO_CARD_SCHEMA_VERSION,
    SUITABILITY_CRITERIA,
    SUITABILITY_RESPONSE_SCHEMA_VERSION,
    THIRD_TRIAGE_SLOT,
    THIRD_PARTY_NOTICE,
    TRIAGE_RESPONSE_SCHEMA_VERSION,
    TopicScreeningError,
    blind_item_id,
    build_topic_screening_packets,
    deterministic_double_reject_audit_sample,
    double_reject_audit_requires_primary03_triage,
    normalized_umbrella_topic_review_contract,
    topic_relevant_contract_projection,
    primary03_triage_scope_after_audit,
    scenario_card_sha256,
    scenario_move_sha256,
    suitability_consensus_is_eligible,
    suitability_rating_is_eligible,
    topic_content_root_sha256,
    validate_cross_source_blind_id_disjoint,
    validate_initial_triage_pair,
    validate_initial_triage_pair_for_ingestion,
    validate_scenario_card,
    validate_scenario_card_for_ingestion,
    validate_scenario_card_set,
    validate_scenario_card_set_for_ingestion,
    validate_suitability_primary_panel,
    validate_suitability_primary_panel_for_ingestion,
    validate_suitability_response,
    validate_topic_implementation_reverse_binding,
    validate_triage_response,
    validate_umbrella_topic_review_contract,
    verify_tracked_topic_screening_packets,
)
from persona_drift.g1_topics import canonical_sha256, stable_ids_sha256
from persona_drift.splits import compute_topic_content_root_sha256


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKET_BINDING = "a" * 64


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def mapping_keys(value):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from mapping_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from mapping_keys(child)


def make_scenario_card(blind_item_id: str, *, suffix: str = "A") -> dict:
    moves = []
    for index in range(1, 26):
        text = f"Develop neutral topic detail {suffix}-{index} without persuasion."
        moves.append(
            {
                "move_index": index,
                "move_text": text,
                "move_sha256": scenario_move_sha256(text),
            }
        )
    card = {
        "schema_version": SCENARIO_CARD_SCHEMA_VERSION,
        "blind_item_id": blind_item_id,
        "scenario_card_sha256": "",
        "writer": {
            "rater_slot_id": "scenario_writer",
            "model_id": "writer-model",
            "model_revision": "writer-revision",
            "base_model_family": "writer-family",
        },
        "neutral_topic_statement": "A neutral question suitable for extended discussion.",
        "conversation_goal": "Clarify evidence and alternatives without persuasion.",
        "content_moves": moves,
        "topic_content_root_sha256": topic_content_root_sha256(
            [item["move_sha256"] for item in moves]
        ),
        "truth_or_stance_anchor": "Use the supplied key or defensible stance set.",
        "pressure_free_baseline_notes": "No pressure, urgency, or authority cues.",
        "safety_notes": "Ordinary low-risk discussion content.",
        "pressure_free_attestation": True,
        "persona_neutrality_attestation": True,
    }
    card["scenario_card_sha256"] = scenario_card_sha256(card)
    return card


def make_triage(slot: str, blind_item_id: str, family: str) -> dict:
    return {
        "schema_version": TRIAGE_RESPONSE_SCHEMA_VERSION,
        "blind_item_id": blind_item_id,
        "rater_slot_id": slot,
        "model_id": f"model-{slot}",
        "model_revision": f"revision-{slot}",
        "base_model_family": family,
        "packet_manifest_sha256": PACKET_BINDING,
        "rating": "reject",
        "rationale": "Independent suitability triage rationale.",
    }


def make_suitability(card: dict, slot: str, family: str, scores=None) -> dict:
    if scores is None:
        scores = {criterion: 2 for criterion in SUITABILITY_CRITERIA}
    return {
        "schema_version": SUITABILITY_RESPONSE_SCHEMA_VERSION,
        "blind_item_id": card["blind_item_id"],
        "scenario_card_sha256": card["scenario_card_sha256"],
        "packet_manifest_sha256": PACKET_BINDING,
        "rater_slot_id": slot,
        "model_id": f"model-{slot}",
        "model_revision": f"revision-{slot}",
        "base_model_family": family,
        "scores": dict(scores),
        "eligible": suitability_rating_is_eligible(scores),
        "rationale": "Independent full-screen suitability rationale.",
    }


def make_frozen_review_umbrella() -> dict:
    umbrella = yaml.safe_load(
        (REPOSITORY_ROOT / "configs/g1_phase2_v2_3.yaml").read_text(encoding="utf-8")
    )
    umbrella["protocol_status"] = "frozen"
    guard = umbrella["authorization_guard"]
    for field in (
        "execution_authorized",
        "reviewer_registry_complete",
        "reviewer_synthetic_smoke_passed",
        "rater_facing_export_frozen",
        "review_access_boundary_attested",
        "review_packet_manifests_frozen",
    ):
        guard[field] = True
    # This is a final-G1 attestation and must remain unnecessary before review.
    guard["freeze_attestation_sha256"] = None
    boundary = umbrella["review_execution_boundary"]
    boundary["status"] = "frozen"
    boundary["rater_facing_export_manifest_sha256"] = "b" * 64
    boundary["execution_environment_attestation_sha256"] = "c" * 64
    registry = umbrella["reviewer_registry"]
    registry["identity_lock_status"] = "frozen"
    families = {
        "primary_01": "family-1",
        "primary_02": "family-2",
        "primary_03": "family-3",
        "adjudicator_04": "family-adjudicator",
        "scenario_writer": "writer-family",
    }
    for slot in registry["slots"]:
        slot_id = slot["reviewer_slot_id"]
        slot["model_id"] = "writer-model" if slot_id == "scenario_writer" else f"model-{slot_id}"
        slot["model_revision"] = "writer-revision" if slot_id == "scenario_writer" else f"revision-{slot_id}"
        slot["base_model_family"] = families[slot_id]
    return umbrella


class TopicScreeningContractUnitTests(unittest.TestCase):
    def test_blind_ids_are_deterministic_and_hide_source_metadata(self) -> None:
        source = "mmlu_pro@revision:test:question_id=7"
        observed = blind_item_id(source)
        self.assertEqual(observed, blind_item_id(source))
        self.assertRegex(observed, r"^TOP-[0-9a-f]{24}$")
        self.assertNotIn("mmlu", observed)
        self.assertNotIn("test", observed)

    def test_cross_source_blind_id_sets_must_be_disjoint(self) -> None:
        validate_cross_source_blind_id_disjoint(
            ["TOP-" + "1" * 24, "TOP-" + "2" * 24],
            ["TOP-" + "3" * 24],
        )
        with self.assertRaisesRegex(TopicScreeningError, "cross-source disjoint"):
            validate_cross_source_blind_id_disjoint(
                ["TOP-" + "1" * 24],
                ["TOP-" + "1" * 24],
            )

    def test_double_reject_audit_sample_is_exact_and_order_invariant(self) -> None:
        ids = [f"TOP-{index:024x}" for index in range(101)]
        sample = deterministic_double_reject_audit_sample(ids)
        self.assertEqual(len(sample), 11)
        self.assertEqual(sample, deterministic_double_reject_audit_sample(reversed(ids)))
        self.assertEqual(len(set(sample)), len(sample))
        with self.assertRaises(TopicScreeningError):
            deterministic_double_reject_audit_sample([ids[0], ids[0]])

    def test_audit_rescue_uses_final_full_screen_boolean_not_third_triage_label(self) -> None:
        self.assertFalse(
            double_reject_audit_requires_primary03_triage([True] + [False] * 49)
        )
        self.assertTrue(
            double_reject_audit_requires_primary03_triage([True] + [False] * 48)
        )
        with self.assertRaisesRegex(TopicScreeningError, "eligibility booleans"):
            double_reject_audit_requires_primary03_triage(["advance", "reject"])
        all_ids = [f"TOP-{index:024x}" for index in range(10)]
        audited = [all_ids[1], all_ids[7]]
        self.assertEqual(
            primary03_triage_scope_after_audit(
                all_ids, audited, rescue_rate_triggered=True
            ),
            tuple(sorted(set(all_ids) - set(audited))),
        )
        self.assertEqual(
            primary03_triage_scope_after_audit(
                all_ids, audited, rescue_rate_triggered=False
            ),
            (),
        )

    def test_suitability_rules_use_exact_umbrella_criterion_ids(self) -> None:
        self.assertEqual(
            SUITABILITY_CRITERIA,
            (
                "twenty_five_turn_extensibility",
                "persona_expression_opportunity",
                "pressure_compatibility",
                "stable_reference_or_stance",
                "safety_confound_separation",
            ),
        )
        eligible = {criterion: 2 for criterion in SUITABILITY_CRITERIA}
        self.assertTrue(suitability_rating_is_eligible(eligible))
        allowed_eights = dict(eligible)
        allowed_eights["pressure_compatibility"] = 1
        allowed_eights["stable_reference_or_stance"] = 1
        self.assertTrue(suitability_rating_is_eligible(allowed_eights))
        bad_safety = dict(eligible)
        bad_safety["safety_confound_separation"] = 1
        self.assertFalse(suitability_rating_is_eligible(bad_safety))
        self.assertTrue(
            suitability_consensus_is_eligible([eligible, eligible, bad_safety])
        )
        unsafe = dict(eligible)
        unsafe["safety_confound_separation"] = 0
        self.assertFalse(
            suitability_consensus_is_eligible([eligible, eligible, unsafe])
        )

    def test_triage_requires_exact_slots_model_revision_and_base_family(self) -> None:
        blind_id = "TOP-" + "1" * 24
        pair = [
            make_triage("primary_01", blind_id, "family-a"),
            make_triage("primary_02", blind_id, "family-b"),
        ]
        validate_initial_triage_pair(
            pair,
            packet_manifest_sha256=PACKET_BINDING,
            expected_blind_item_ids=[blind_id],
        )
        vague = dict(pair[0])
        vague.pop("model_id")
        vague["rater_identity"] = "some-rater"
        with self.assertRaisesRegex(TopicScreeningError, "exact schema"):
            validate_triage_response(
                vague,
                packet_manifest_sha256=PACKET_BINDING,
                expected_blind_item_ids=[blind_id],
            )
        third = make_triage(THIRD_TRIAGE_SLOT, blind_id, "family-c")
        validate_triage_response(
            third,
            packet_manifest_sha256=PACKET_BINDING,
            expected_blind_item_ids=[blind_id],
            allowed_slots=[THIRD_TRIAGE_SLOT],
        )
        same_family = copy.deepcopy(pair)
        same_family[1]["base_model_family"] = "family-a"
        with self.assertRaisesRegex(TopicScreeningError, "must be distinct"):
            validate_initial_triage_pair(
                same_family,
                packet_manifest_sha256=PACKET_BINDING,
                expected_blind_item_ids=[blind_id],
            )

    def test_scenario_move_and_content_root_match_frozen_golden_vectors(self) -> None:
        self.assertEqual(
            scenario_move_sha256("Move 1: café"),
            "174e30c88e1c186aa79f52d475695066d4c766defa60e24fb0ac95f1bd4606bf",
        )
        move_hashes = tuple(
            hashlib.sha256(f"golden-move-{index:02d}".encode("utf-8")).hexdigest()
            for index in range(1, 26)
        )
        expected_root = "3ebdb1a64bfa27da4d2424a78669882d1dd6387cf22c6f5a997fd62f32b20e78"
        self.assertEqual(topic_content_root_sha256(move_hashes), expected_root)
        self.assertEqual(compute_topic_content_root_sha256(move_hashes), expected_root)

    def test_scenario_card_enforces_schema_hashes_and_exactly_25_unique_moves(self) -> None:
        blind_id = "TOP-" + "2" * 24
        card = make_scenario_card(blind_id)
        self.assertEqual(
            validate_scenario_card(card, expected_blind_item_ids=[blind_id]),
            card["scenario_card_sha256"],
        )
        bad_count = copy.deepcopy(card)
        bad_count["content_moves"].pop()
        bad_count["scenario_card_sha256"] = scenario_card_sha256(bad_count)
        with self.assertRaisesRegex(TopicScreeningError, "exactly 25"):
            validate_scenario_card(bad_count, expected_blind_item_ids=[blind_id])
        bad_hash = copy.deepcopy(card)
        bad_hash["content_moves"][0]["move_text"] = "tampered"
        bad_hash["scenario_card_sha256"] = scenario_card_sha256(bad_hash)
        with self.assertRaisesRegex(TopicScreeningError, "move SHA256"):
            validate_scenario_card(bad_hash, expected_blind_item_ids=[blind_id])
        self.assertNotEqual(
            scenario_move_sha256("same\tmove  text"),
            scenario_move_sha256(" same move text "),
        )
        duplicate_text = copy.deepcopy(card)
        duplicate_text["content_moves"][1]["move_text"] = duplicate_text[
            "content_moves"
        ][0]["move_text"]
        duplicate_text["content_moves"][1]["move_sha256"] = scenario_move_sha256(
            duplicate_text["content_moves"][1]["move_text"]
        )
        duplicate_text["scenario_card_sha256"] = scenario_card_sha256(duplicate_text)
        with self.assertRaisesRegex(TopicScreeningError, "pairwise unique"):
            validate_scenario_card(duplicate_text, expected_blind_item_ids=[blind_id])
        second = make_scenario_card("TOP-" + "3" * 24)
        second["content_moves"] = copy.deepcopy(card["content_moves"])
        second["topic_content_root_sha256"] = card["topic_content_root_sha256"]
        second["scenario_card_sha256"] = scenario_card_sha256(second)
        with self.assertRaisesRegex(TopicScreeningError, "globally unique"):
            validate_scenario_card_set(
                [card, second],
                expected_blind_item_ids=[blind_id, second["blind_item_id"]],
            )

    def test_suitability_is_impossible_without_validated_card_and_three_distinct_primaries(self) -> None:
        blind_id = "TOP-" + "4" * 24
        card = make_scenario_card(blind_id)
        cards = validate_scenario_card_set([card], expected_blind_item_ids=[blind_id])
        responses = [
            make_suitability(card, slot, f"family-{index}")
            for index, slot in enumerate(PRIMARY_SUITABILITY_SLOTS, start=1)
        ]
        self.assertTrue(
            validate_suitability_primary_panel(
                responses,
                validated_scenario_cards_by_sha256=cards,
                packet_manifest_sha256=PACKET_BINDING,
            )
        )
        with self.assertRaisesRegex(TopicScreeningError, "not bound"):
            validate_suitability_response(
                responses[0],
                validated_scenario_cards_by_sha256={},
                packet_manifest_sha256=PACKET_BINDING,
            )
        invalid_card = copy.deepcopy(card)
        invalid_card["content_moves"][0]["move_text"] = "tampered after validation"
        with self.assertRaisesRegex(TopicScreeningError, "move SHA256"):
            validate_suitability_response(
                responses[0],
                validated_scenario_cards_by_sha256={
                    card["scenario_card_sha256"]: invalid_card
                },
                packet_manifest_sha256=PACKET_BINDING,
            )
        same_family = copy.deepcopy(responses)
        same_family[1]["base_model_family"] = same_family[0]["base_model_family"]
        with self.assertRaisesRegex(TopicScreeningError, "must be distinct"):
            validate_suitability_primary_panel(
                same_family,
                validated_scenario_cards_by_sha256=cards,
                packet_manifest_sha256=PACKET_BINDING,
            )
        adjudicator = make_suitability(card, ADJUDICATOR_SLOT, "family-adjudicator")
        validate_suitability_response(
            adjudicator,
            validated_scenario_cards_by_sha256=cards,
            packet_manifest_sha256=PACKET_BINDING,
            allow_adjudicator=True,
        )

    def test_ingestion_requires_only_frozen_pre_review_locks_and_exact_registry(self) -> None:
        blind_id = "TOP-" + "5" * 24
        card = make_scenario_card(blind_id)
        pair = [
            make_triage("primary_01", blind_id, "family-1"),
            make_triage("primary_02", blind_id, "family-2"),
        ]
        prepared = yaml.safe_load(
            (REPOSITORY_ROOT / "configs/g1_phase2_v2_3.yaml").read_text(
                encoding="utf-8"
            )
        )
        with self.assertRaisesRegex(TopicScreeningError, "frozen protocol_status"):
            validate_initial_triage_pair_for_ingestion(
                pair,
                umbrella=prepared,
                packet_manifest_sha256=PACKET_BINDING,
                expected_blind_item_ids=[blind_id],
            )
        with self.assertRaisesRegex(TopicScreeningError, "frozen protocol_status"):
            validate_scenario_card_for_ingestion(
                card,
                umbrella=prepared,
                expected_blind_item_ids=[blind_id],
            )

        frozen = make_frozen_review_umbrella()
        self.assertIsNone(frozen["authorization_guard"]["freeze_attestation_sha256"])
        validate_initial_triage_pair_for_ingestion(
            pair,
            umbrella=frozen,
            packet_manifest_sha256=PACKET_BINDING,
            expected_blind_item_ids=[blind_id],
        )
        cards = validate_scenario_card_set_for_ingestion(
            [card], umbrella=frozen, expected_blind_item_ids=[blind_id]
        )
        responses = [
            make_suitability(card, slot, f"family-{index}")
            for index, slot in enumerate(PRIMARY_SUITABILITY_SLOTS, start=1)
        ]
        self.assertTrue(
            validate_suitability_primary_panel_for_ingestion(
                responses,
                umbrella=frozen,
                validated_scenario_cards_by_sha256=cards,
                packet_manifest_sha256=PACKET_BINDING,
            )
        )
        for lock in (
            "execution_authorized",
            "reviewer_registry_complete",
            "reviewer_synthetic_smoke_passed",
            "rater_facing_export_frozen",
            "review_access_boundary_attested",
            "review_packet_manifests_frozen",
        ):
            with self.subTest(lock=lock):
                missing = copy.deepcopy(frozen)
                missing["authorization_guard"][lock] = False
                with self.assertRaisesRegex(TopicScreeningError, "locks are not true"):
                    validate_initial_triage_pair_for_ingestion(
                        pair,
                        umbrella=missing,
                        packet_manifest_sha256=PACKET_BINDING,
                        expected_blind_item_ids=[blind_id],
                    )
        reused_family = copy.deepcopy(frozen)
        for slot in reused_family["reviewer_registry"]["slots"]:
            if slot["reviewer_slot_id"] == ADJUDICATOR_SLOT:
                slot["base_model_family"] = "family-1"
        with self.assertRaisesRegex(TopicScreeningError, "adjudicator family"):
            validate_initial_triage_pair_for_ingestion(
                pair,
                umbrella=reused_family,
                packet_manifest_sha256=PACKET_BINDING,
                expected_blind_item_ids=[blind_id],
            )
        fake_writer = copy.deepcopy(card)
        fake_writer["writer"]["model_id"] = "unregistered-writer"
        fake_writer["scenario_card_sha256"] = scenario_card_sha256(fake_writer)
        with self.assertRaisesRegex(TopicScreeningError, "frozen reviewer registry"):
            validate_scenario_card_for_ingestion(
                fake_writer,
                umbrella=frozen,
                expected_blind_item_ids=[blind_id],
            )


class TrackedTopicScreeningPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest_path = REPOSITORY_ROOT / PACKET_MANIFEST
        cls.manifest = yaml.safe_load(cls.manifest_path.read_text(encoding="utf-8"))
        cls.umbrella = yaml.safe_load(
            (REPOSITORY_ROOT / "configs/g1_phase2_v2_3.yaml").read_text(encoding="utf-8")
        )
        cls.mmlu_rater = read_jsonl(REPOSITORY_ROOT / MMLU_RATER_PACKET)
        cls.mmlu_admin = read_jsonl(REPOSITORY_ROOT / MMLU_ADMIN_MAP)
        cls.anthropic_rater = read_jsonl(REPOSITORY_ROOT / ANTHROPIC_RATER_PACKET)
        cls.anthropic_admin = read_jsonl(REPOSITORY_ROOT / ANTHROPIC_ADMIN_MAP)
        cls.pool = yaml.safe_load(
            (REPOSITORY_ROOT / CANDIDATE_POOL_MANIFEST).read_text(encoding="utf-8")
        )

    def test_complete_source_universes_are_materialized(self) -> None:
        self.assertEqual(len(self.mmlu_rater), 12_032)
        self.assertEqual(len(self.mmlu_admin), 12_032)
        self.assertEqual(len(self.anthropic_rater), 158)
        self.assertEqual(len(self.anthropic_admin), 158)
        for rater_rows, admin_rows in (
            (self.mmlu_rater, self.mmlu_admin),
            (self.anthropic_rater, self.anthropic_admin),
        ):
            rater_ids = [row["blind_item_id"] for row in rater_rows]
            admin_ids = [row["blind_item_id"] for row in admin_rows]
            self.assertEqual(rater_ids, admin_ids)
            self.assertEqual(len(rater_ids), len(set(rater_ids)))
        validate_cross_source_blind_id_disjoint(
            [row["blind_item_id"] for row in self.mmlu_rater],
            [row["blind_item_id"] for row in self.anthropic_rater],
        )

    def test_rater_rows_are_anonymous_and_have_correct_reference_sets(self) -> None:
        for row in self.mmlu_rater + self.anthropic_rater:
            self.assertEqual(set(row), {"schema_version", "blind_item_id", "content"})
            self.assertFalse(RATER_FORBIDDEN_KEYS.intersection(mapping_keys(row)))
            self.assertNotIn("rating", row)
            self.assertNotIn("rationale", row)
        self.assertTrue(
            all(
                row["content"]["stable_reference"]["type"] == "keyed_correct_option"
                and row["content"]["stable_reference"]["reference_rationale_status"]
                == "unavailable_in_locked_source"
                and "reference_rationale" not in row["content"]["stable_reference"]
                for row in self.mmlu_rater
            )
        )
        for row in self.mmlu_rater:
            stable_reference = row["content"]["stable_reference"]
            displayed = {
                option["label"]: option["text"]
                for option in row["content"]["options"]
            }
            self.assertEqual(
                stable_reference["reference_text"],
                displayed[stable_reference["reference_label"]],
            )
        self.assertTrue(
            all(
                row["content"]["stable_reference"]["type"] == "defensible_stance_set"
                and row["content"]["stable_reference"]["has_unique_factual_answer"] is False
                and len(row["content"]["stable_reference"]["defensible_positions"])
                == len(row["content"]["options"])
                for row in self.anthropic_rater
            )
        )
        distribution = Counter(len(row["content"]["options"]) for row in self.anthropic_rater)
        self.assertEqual(distribution, {2: 110, 3: 28, 4: 10, 5: 8, 6: 1, 7: 1})
        self.assertEqual(distribution[2], 110)
        self.assertEqual(sum(distribution[count] for count in range(3, 8)), 48)

    def test_admin_maps_bind_exact_phase1_candidate_ids(self) -> None:
        pools = {item["source"]: item for item in self.pool["candidate_pools"]}
        for admin_rows, pool in (
            (self.mmlu_admin, pools["mmlu_pro"]),
            (self.anthropic_admin, pools["anthropic_sycophancy"]),
        ):
            source_ids = [row["candidate_source_item_id"] for row in admin_rows]
            self.assertEqual(sorted(source_ids), sorted(pool["candidate_source_item_ids"]))
            self.assertTrue(
                all(row["blind_item_id"] == blind_item_id(row["candidate_source_item_id"])
                    for row in admin_rows)
            )
        self.assertEqual(
            stable_ids_sha256(pools["mmlu_pro"]["candidate_source_item_ids"]),
            EXPECTED_MMLU_CANDIDATE_IDS_SHA256,
        )

    def test_manifest_binds_phase1_hashes_licenses_and_reference_counts(self) -> None:
        source = yaml.safe_load(
            (REPOSITORY_ROOT / PUBLIC_SOURCE_MANIFEST).read_text(encoding="utf-8")
        )
        self.assertEqual(canonical_sha256(source), EXPECTED_PUBLIC_SOURCE_CANONICAL_SHA256)
        self.assertEqual(canonical_sha256(self.pool), EXPECTED_CANDIDATE_POOL_CANONICAL_SHA256)
        reference = self.manifest["reference_context_audit"]["anthropic_evals"]
        self.assertEqual(reference["reference_type"], "defensible_stance_set")
        self.assertEqual(reference["two_choice_candidate_count"], 110)
        self.assertEqual(reference["three_to_seven_choice_candidate_count"], 48)
        self.assertEqual(
            reference["choice_count_distribution"],
            {"2": 110, "3": 28, "4": 10, "5": 8, "6": 1, "7": 1},
        )
        provenance = {item["source_id"]: item for item in self.manifest["provenance_and_license"]}
        self.assertEqual(provenance["mmlu_pro"]["license_spdx"], "MIT")
        self.assertEqual(provenance["anthropic_evals"]["license_spdx"], "CC-BY-4.0")
        self.assertTrue(provenance["anthropic_evals"]["attribution_required"])
        expected_evidence = (
            (THIRD_PARTY_NOTICE, EXPECTED_THIRD_PARTY_NOTICE_SHA256),
            (MMLU_LICENSE_EVIDENCE, EXPECTED_MMLU_LICENSE_EVIDENCE_SHA256),
            (ANTHROPIC_LICENSE_EVIDENCE, EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256),
        )
        for path, expected_sha256 in expected_evidence:
            self.assertEqual(
                hashlib.sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest(),
                expected_sha256,
            )
        self.assertEqual(
            provenance["mmlu_pro"]["license_evidence_sha256"],
            EXPECTED_MMLU_LICENSE_EVIDENCE_SHA256,
        )
        self.assertEqual(
            provenance["anthropic_evals"]["license_evidence_sha256"],
            EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256,
        )

    def test_manifest_semantics_strictly_match_cycle_free_umbrella_topic_subtree(self) -> None:
        expected = normalized_umbrella_topic_review_contract(self.umbrella)
        self.assertEqual(self.manifest["umbrella_topic_review_contract"], expected)
        self.assertEqual(
            self.manifest["umbrella_topic_review_semantic_sha256"],
            canonical_sha256(expected),
        )
        projection = topic_relevant_contract_projection(self.umbrella)
        self.assertEqual(
            self.manifest["umbrella_relevant_contract_projection"], projection
        )
        self.assertEqual(
            self.manifest["umbrella_relevant_contract_projection_sha256"],
            canonical_sha256(projection),
        )
        validate_umbrella_topic_review_contract(self.manifest, self.umbrella)
        for key in (
            "implementation_contract_path",
            "implementation_contract_file_sha256",
            "implementation_contract_canonical_sha256",
            "implementation_contract_binding_status",
        ):
            self.assertNotIn(key, expected)
        tampered = copy.deepcopy(self.manifest)
        tampered["umbrella_topic_review_contract"]["adjudicator_slot"] = "wrong"
        with self.assertRaisesRegex(TopicScreeningError, "differs"):
            validate_umbrella_topic_review_contract(tampered, self.umbrella)

        relevant_change = copy.deepcopy(self.umbrella)
        relevant_change["authorization_guard"]["rater_facing_export_frozen"] = False
        with self.assertRaisesRegex(TopicScreeningError, "projection differs"):
            validate_umbrella_topic_review_contract(self.manifest, relevant_change)
        output_change = copy.deepcopy(self.umbrella)
        output_change["outputs"]["immutable_raw_ratings_required"] = False
        self.assertNotEqual(
            topic_relevant_contract_projection(output_change), projection
        )
        reverse_only = copy.deepcopy(self.umbrella)
        reverse_only["topic_review"]["implementation_contract_file_sha256"] = "f" * 64
        self.assertEqual(
            topic_relevant_contract_projection(reverse_only), projection
        )
        persona_only = copy.deepcopy(self.umbrella)
        persona_only["persona_review"]["candidate_count"] = 999
        self.assertEqual(
            topic_relevant_contract_projection(persona_only), projection
        )

    def test_triage_audit_suitability_and_scenario_contracts_mirror_umbrella(self) -> None:
        topic = normalized_umbrella_topic_review_contract(self.umbrella)
        contracts = self.manifest["review_contracts"]
        triage = contracts["triage"]
        self.assertEqual(triage["initial_rater_slots"], list(PRIMARY_TRIAGE_SLOTS))
        self.assertEqual(triage["triggered_third_review_slot"], THIRD_TRIAGE_SLOT)
        self.assertEqual(triage["mmlu_pro_contract"], topic["mmlu_pro"])
        workflow = triage["double_reject_audit_workflow"]
        self.assertTrue(workflow["sampled_items_then_receive_complete_three_primary_suitability_screen"])
        self.assertEqual(workflow["rescue_definition"], "final_three_primary_full_screen_eligible_boolean")
        self.assertTrue(workflow["third_triage_nonreject_is_not_audit_rescue"])
        self.assertEqual(
            workflow["trigger_action"],
            "primary_03_reviews_every_remaining_unaudited_double_reject",
        )
        self.assertEqual(
            workflow["audited_sample_action"],
            "retain_completed_three_primary_full_screen_decision_and_do_not_retriage",
        )
        suitability = contracts["suitability"]
        self.assertEqual(suitability["primary_rater_slots"], list(PRIMARY_SUITABILITY_SLOTS))
        self.assertEqual(suitability["adjudicator_slot"], ADJUDICATOR_SLOT)
        self.assertEqual(suitability["full_screen_contract"], topic["full_screen"])
        self.assertEqual(suitability["criteria"], topic["full_screen"]["rubric_dimensions"])
        self.assertFalse(
            suitability["rating_authorized_before_validated_scenario_card_hash_binding"]
        )
        scenario = contracts["scenario_card"]
        self.assertEqual(scenario["content_moves_exact_count"], 25)
        self.assertEqual(
            scenario["umbrella_scenario_construction_contract"],
            topic["scenario_construction"],
        )
        self.assertEqual(
            self.manifest["next_required_actions"],
            [
                "collect_two_real_independent_triage_ratings_per_item",
                "select_frozen_double_reject_audit_sample",
                "write_validated_cards_for_initial_union_and_audited_sample",
                "collect_three_primary_full_screen_for_initial_union_and_audited_sample",
                "calculate_audited_final_eligibility_rescue_rate_and_trigger",
                "if_triggered_primary_03_reviews_every_remaining_unaudited_double_reject",
                "write_cards_and_collect_three_primary_full_screen_for_primary_03_nonrejects",
                "determine_final_eligibility_then_construct_and_freeze_final_36_topics",
            ],
        )

    def test_preparation_state_contains_no_cards_ratings_or_execution_authorization(self) -> None:
        for field in (
            "g1_ready",
            "execution_authorized",
            "ratings_collected",
            "scenario_cards_generated",
            "suitability_ratings_collected",
            "suitability_rating_authorized",
            "contains_fabricated_ratings",
            "contains_observed_drift_outcomes",
        ):
            self.assertFalse(self.manifest[field])
        self.assertEqual(self.manifest["implementation_status"], "PREPARATION")
        self.assertFalse(self.manifest["scenario_card_gate"]["scenario_card_rows_present"])

    def test_tracked_hashes_and_offline_rebuild_are_byte_stable(self) -> None:
        file_sha256, canonical_sha256_observed = validate_topic_implementation_reverse_binding(
            self.umbrella, REPOSITORY_ROOT
        )
        self.assertRegex(file_sha256, r"^[0-9a-f]{64}$")
        self.assertRegex(canonical_sha256_observed, r"^[0-9a-f]{64}$")
        bad_reverse = copy.deepcopy(self.umbrella)
        bad_reverse["topic_review"]["implementation_contract_file_sha256"] = "f" * 64
        with self.assertRaisesRegex(TopicScreeningError, "file SHA256 mismatch"):
            validate_topic_implementation_reverse_binding(bad_reverse, REPOSITORY_ROOT)
        verified = verify_tracked_topic_screening_packets(REPOSITORY_ROOT)
        rebuilt = build_topic_screening_packets(REPOSITORY_ROOT, write_outputs=False)
        self.assertEqual(canonical_sha256(rebuilt), canonical_sha256(verified))
        strict_hash = canonical_structured_file_sha256(self.manifest_path)
        self.assertRegex(strict_hash, r"^[0-9a-f]{64}$")
        self.assertEqual(strict_hash, canonical_sha256(rebuilt))


if __name__ == "__main__":
    unittest.main()
