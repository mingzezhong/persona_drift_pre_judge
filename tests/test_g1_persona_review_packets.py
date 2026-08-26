from __future__ import annotations

from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from persona_drift.g1_persona_review import (
    ALLOWED_ROLE,
    ANTHROPIC_LICENSE_EVIDENCE_PATH,
    AUDIT_FILENAME,
    EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256,
    EXPECTED_THIRD_PARTY_NOTICE_SHA256,
    THIRD_PARTY_NOTICE_PATH,
    CONFIG_FILENAME,
    EXPOSURE_FILENAME,
    EXPOSURE_STATUS,
    FORBIDDEN_ROLES,
    PACKET_MANIFEST_FILENAME,
    PACKET_FILENAME,
    PREPARATION_STATUS,
    PersonaReviewPacketError,
    RUBRIC_FILENAME,
    anonymous_candidate_id,
    anonymous_review_item_id,
    build_persona_review_assets,
    candidate_display_rank,
    _normalized_rubric_dimensions,
    persona_relevant_contract_projection,
    sampling_rank,
    select_review_items,
    validate_future_persona_item_roles,
    validate_persona_relevant_contract_binding,
    verify_tracked_persona_review_assets,
)
from persona_drift.g1_personas import UNIQUE_ITEM_STATUS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / CONFIG_FILENAME


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def all_mapping_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from all_mapping_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from all_mapping_keys(nested)


class PersonaReviewSamplingUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["sampling_contract"]

    def test_domain_separated_ids_and_ranks_are_stable(self) -> None:
        candidate = "ae-persona-risk-averse"
        source = "anthropic-evals-example-item"
        self.assertEqual(anonymous_candidate_id(candidate, self.contract), anonymous_candidate_id(candidate, self.contract))
        self.assertEqual(anonymous_review_item_id(source, self.contract), anonymous_review_item_id(source, self.contract))
        self.assertNotEqual(
            sampling_rank(candidate, "Yes", source, self.contract),
            sampling_rank(candidate, "No", source, self.contract),
        )
        self.assertNotIn("risk-averse", anonymous_candidate_id(candidate, self.contract))
        self.assertNotIn("anthropic", anonymous_review_item_id(source, self.contract))

    def test_selection_is_order_invariant_and_exactly_48_plus_48(self) -> None:
        items = []
        for response in (" Yes", " No"):
            for index in range(60):
                items.append(
                    {
                        "stable_source_item_id": f"source-{response.strip().lower()}-{index:03d}",
                        "answer_matching_behavior": response,
                        "g1_candidate_item_status": UNIQUE_ITEM_STATUS,
                    }
                )
        items.append(
            {
                "stable_source_item_id": "excluded-duplicate",
                "answer_matching_behavior": " Yes",
                "g1_candidate_item_status": "EXCLUDED_NORMALIZED_DUPLICATE",
            }
        )
        forward = {"candidate_trait_id": "trait-test", "source_items": items}
        reverse = {"candidate_trait_id": "trait-test", "source_items": list(reversed(items))}
        first = select_review_items(forward, self.contract)
        second = select_review_items(reverse, self.contract)
        self.assertEqual(
            [item["stable_source_item_id"] for item in first],
            [item["stable_source_item_id"] for item in second],
        )
        self.assertEqual(Counter(item["answer_matching_behavior"] for item in first), {" Yes": 48, " No": 48})
        self.assertNotIn("excluded-duplicate", {item["stable_source_item_id"] for item in first})

    def test_exposure_validator_forbids_vector_and_heldout_reuse(self) -> None:
        exposed = {"item-a", "item-b"}
        validate_future_persona_item_roles(
            exposed,
            [
                {"source_item_id": "item-a", "role": ALLOWED_ROLE},
                {"source_item_id": "unexposed", "role": "persona_vector_extraction"},
            ],
        )
        for forbidden in FORBIDDEN_ROLES:
            with self.assertRaisesRegex(PersonaReviewPacketError, "cannot receive role"):
                validate_future_persona_item_roles(
                    exposed,
                    [{"source_item_id": "item-a", "role": forbidden}],
                )

    def test_anchor_key_normalization_is_format_tolerant_but_content_strict(self) -> None:
        dimensions = [
            {
                "dimension_id": f"d{index}",
                "label": f"Dimension {index}",
                "anchors": {0: "zero", "1": "one", 2: "two"},
            }
            for index in range(7)
        ]
        normalized = _normalized_rubric_dimensions(dimensions)
        self.assertEqual(normalized[0]["anchors"], {"0": "zero", "1": "one", "2": "two"})
        dimensions[0]["anchors"] = {0: "zero", 1: "one", 3: "three"}
        with self.assertRaisesRegex(PersonaReviewPacketError, "exactly to 0/1/2"):
            _normalized_rubric_dimensions(dimensions)


class GeneratedPersonaReviewPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        cls.rubric_path = PROJECT_ROOT / "data/manifests" / RUBRIC_FILENAME
        cls.packet_manifest_path = PROJECT_ROOT / "data/manifests" / PACKET_MANIFEST_FILENAME
        cls.exposure_path = PROJECT_ROOT / "data/manifests" / EXPOSURE_FILENAME
        cls.packet_path = PROJECT_ROOT / "data/reviews" / PACKET_FILENAME
        cls.audit_path = PROJECT_ROOT / "data/reports" / AUDIT_FILENAME
        cls.rubric = yaml.safe_load(cls.rubric_path.read_text(encoding="utf-8"))
        cls.packet_manifest = yaml.safe_load(cls.packet_manifest_path.read_text(encoding="utf-8"))
        cls.exposure = yaml.safe_load(cls.exposure_path.read_text(encoding="utf-8"))
        cls.packet_rows = read_jsonl(cls.packet_path)
        cls.audit = json.loads(cls.audit_path.read_text(encoding="utf-8"))

    def test_packet_has_24_by_96_with_balanced_persona_consistent_directions(self) -> None:
        self.assertEqual(len(self.packet_rows), 2_304)
        by_candidate = defaultdict(list)
        for row in self.packet_rows:
            by_candidate[row["candidate_anonymous_id"]].append(row)
            self.assertEqual(row["response_options"], ["Yes", "No"])
            self.assertIn(row["persona_consistent_response"], {"Yes", "No"})
            self.assertEqual(row["exposure_status"], EXPOSURE_STATUS)
        self.assertEqual(len(by_candidate), 24)
        for rows in by_candidate.values():
            self.assertEqual(len(rows), 96)
            self.assertEqual(Counter(row["persona_consistent_response"] for row in rows), {"Yes": 48, "No": 48})
            self.assertEqual([row["display_order_within_candidate"] for row in rows], list(range(1, 97)))
        self.assertEqual(len({row["review_item_anonymous_id"] for row in self.packet_rows}), 2_304)

    def test_rater_facing_rows_are_source_and_family_blinded(self) -> None:
        forbidden = {
            "candidate_trait_id", "candidate_family_id", "family_id", "source_trait_slug",
            "trait_slug", "source_path", "source_revision", "source_line_number",
            "stable_source_item_id", "raw_line_sha256",
        }
        for row in self.packet_rows:
            self.assertTrue(forbidden.isdisjoint(all_mapping_keys(row)))
            serialized = json.dumps(row, ensure_ascii=False)
            self.assertNotIn("anthropic-evals-84fcc677-persona-", serialized)
        self.assertFalse(self.exposure["access_boundary"]["rater_facing_packet_contains_this_mapping"])
        self.assertTrue(self.exposure["access_boundary"]["do_not_supply_this_ledger_to_semantic_raters"])

    def test_candidate_group_order_uses_separate_anonymous_rank_not_source_order(self) -> None:
        pool = yaml.safe_load(
            (PROJECT_ROOT / "data/manifests/persona_candidate_pool_v2_3.yaml").read_text(encoding="utf-8")
        )
        source_order = sorted(trait["candidate_trait_id"] for trait in pool["candidate_traits"])
        expected_source_ids = sorted(
            source_order,
            key=lambda trait_id: (
                candidate_display_rank(trait_id, self.config["sampling_contract"]),
                trait_id,
            ),
        )
        identity_by_anonymous = {
            row["candidate_anonymous_id"]: row["candidate_trait_id"]
            for row in self.exposure["candidate_identity_map"]
        }
        first_seen_anonymous = list(
            dict.fromkeys(row["candidate_anonymous_id"] for row in self.packet_rows)
        )
        observed_source_ids = [identity_by_anonymous[item] for item in first_seen_anonymous]
        self.assertEqual(observed_source_ids, expected_source_ids)
        self.assertNotEqual(observed_source_ids, source_order)
        self.assertEqual(
            self.packet_manifest["candidate_group_order"],
            "domain-separated SHA256 rank; not source-trait order",
        )

    def test_exposure_is_permanent_definition_only_and_source_ids_are_unique(self) -> None:
        rows = self.exposure["exposed_items"]
        self.assertEqual(self.exposure["exposed_item_count"], 2_304)
        self.assertEqual(len(rows), 2_304)
        self.assertEqual(len({row["stable_source_item_id"] for row in rows}), 2_304)
        self.assertEqual(len({row["normalized_statement_sha256"] for row in rows}), 2_304)
        for row in rows:
            self.assertEqual(row["exposure_status"], EXPOSURE_STATUS)
            self.assertEqual(row["allowed_future_persona_item_roles"], [ALLOWED_ROLE])
            self.assertEqual(set(row["forbidden_future_persona_item_roles"]), FORBIDDEN_ROLES)
        validate_future_persona_item_roles(
            (row["stable_source_item_id"] for row in rows),
            [{"source_item_id": rows[0]["stable_source_item_id"], "role": ALLOWED_ROLE}],
        )

    def test_rubric_and_unassigned_four_distinct_base_panel_are_frozen(self) -> None:
        self.assertEqual(self.rubric["implementation_status"], PREPARATION_STATUS)
        dimensions = self.rubric["rubric_dimensions"]
        self.assertEqual(len(dimensions), 7)
        self.assertEqual(
            self.rubric["criterion_code_map"],
            {f"P{index}": item["dimension_id"] for index, item in enumerate(dimensions, start=1)},
        )
        primary = self.rubric["primary_rating_panel"]
        adjudication = self.rubric["adjudication_panel"]
        self.assertEqual(primary["required_raters"], 3)
        self.assertEqual(primary["distinct_base_model_families_required"], 3)
        self.assertTrue(adjudication["fourth_distinct_base_model_family_required"])
        slots = primary["slots"] + adjudication["slots"]
        self.assertEqual(len(slots), 4)
        self.assertEqual(
            [slot["slot_id"] for slot in slots],
            ["primary_01", "primary_02", "primary_03", "adjudicator_04"],
        )
        for slot in slots:
            self.assertIsNone(slot["model_id"])
            self.assertIsNone(slot["base_model_family_id"])
            self.assertIsNone(slot["model_revision"])
            self.assertEqual(slot["ratings_status"], "NOT_RUN")
        self.assertEqual(self.rubric["rating_record_status"], "NO_RATINGS_IN_THIS_ASSET")

    def test_rubric_anchors_and_all_pair_relations_exactly_mirror_umbrella_contract(self) -> None:
        umbrella_path = PROJECT_ROOT / "configs/g1_phase2_v2_3.yaml"
        umbrella = yaml.safe_load(umbrella_path.read_text(encoding="utf-8"))
        persona = umbrella["persona_review"]
        projection = persona_relevant_contract_projection(umbrella)
        for payload in (
            self.rubric,
            self.packet_manifest,
            self.exposure,
            self.audit,
        ):
            self.assertEqual(
                payload["umbrella_relevant_contract_projection"], projection
            )
            validate_persona_relevant_contract_binding(payload, umbrella)
        self.assertEqual(self.rubric["score_scale"], persona["score_scale"])
        self.assertNotIn("anchors", self.rubric["score_scale"])
        normalized_expected = [
            {
                "dimension_id": item["dimension_id"],
                "label": item["label"],
                "anchors": {str(key): value for key, value in item["anchors"].items()},
            }
            for item in persona["rubric_dimensions"]
        ]
        self.assertEqual(self.rubric["rubric_dimensions"], normalized_expected)
        for expected, observed in zip(
            normalized_expected, self.rubric["rubric_dimensions"]
        ):
            self.assertEqual(set(observed["anchors"]), {"0", "1", "2"})
            self.assertEqual(observed["anchors"], expected["anchors"])
        self.assertEqual(
            self.rubric["provisional_decision_rules"],
            persona["provisional_decision_rules"],
        )
        pair = self.rubric["pair_relation_review"]
        for key, value in persona["pair_relation_review"].items():
            self.assertEqual(pair[key], value)
        self.assertEqual(pair["unordered_pair_count"], 276)
        self.assertTrue(pair["all_unordered_pairs_of_24_required"])
        self.assertEqual(
            pair["labels"],
            [
                "distinct_traits",
                "related_but_distinct_traits",
                "opposite_poles_of_one_axis",
                "same_trait_or_near_duplicate",
                "insufficient_evidence",
            ],
        )
        self.assertEqual(
            pair["candidate_scope"],
            "ALL_24_CANDIDATES_REGARDLESS_OF_SCALAR_REVIEW_DECISION",
        )

    def test_relevant_projection_is_fail_closed_but_topic_changes_are_invariant(self) -> None:
        umbrella = yaml.safe_load(
            (PROJECT_ROOT / "configs/g1_phase2_v2_3.yaml").read_text(
                encoding="utf-8"
            )
        )
        projection = persona_relevant_contract_projection(umbrella)
        self.assertNotIn("topic_review", projection)
        self.assertNotIn("topic_packet_hides", projection["blinding"])
        self.assertEqual(
            [
                slot["reviewer_slot_id"]
                for slot in projection["reviewer_registry"]["slots"]
            ],
            ["primary_01", "primary_02", "primary_03", "adjudicator_04"],
        )
        self.assertNotIn(
            "scenario_writer",
            {
                slot["reviewer_slot_id"]
                for slot in projection["reviewer_registry"]["slots"]
            },
        )

        topic_only = copy.deepcopy(umbrella)
        topic_only["topic_review"]["implementation_contract_file_sha256"] = "f" * 64
        topic_only["blinding"]["topic_packet_hides"].append("topic-only-test")
        for slot in topic_only["reviewer_registry"]["slots"]:
            if slot["reviewer_slot_id"] == "scenario_writer":
                slot["model_id"] = "topic-only-writer"
        topic_only["authorization_guard"]["topic_catalog_and_scenarios_frozen"] = True
        self.assertEqual(persona_relevant_contract_projection(topic_only), projection)

        relevant_mutations = []
        persona_changed = copy.deepcopy(umbrella)
        persona_changed["persona_review"]["candidate_count"] = 25
        relevant_mutations.append(persona_changed)
        registry_changed = copy.deepcopy(umbrella)
        registry_changed["reviewer_registry"]["slots"][0]["model_id"] = "assigned"
        relevant_mutations.append(registry_changed)
        guard_changed = copy.deepcopy(umbrella)
        guard_changed["authorization_guard"]["rater_facing_export_frozen"] = True
        relevant_mutations.append(guard_changed)
        boundary_changed = copy.deepcopy(umbrella)
        boundary_changed["review_execution_boundary"]["status"] = "frozen"
        relevant_mutations.append(boundary_changed)
        output_changed = copy.deepcopy(umbrella)
        output_changed["outputs"]["immutable_raw_ratings_required"] = False
        relevant_mutations.append(output_changed)
        blinding_changed = copy.deepcopy(umbrella)
        blinding_changed["blinding"]["reviewer_outputs_are_immutable_append_only"] = False
        relevant_mutations.append(blinding_changed)
        for mutated in relevant_mutations:
            self.assertNotEqual(persona_relevant_contract_projection(mutated), projection)
            with self.assertRaisesRegex(PersonaReviewPacketError, "projection differs"):
                validate_persona_relevant_contract_binding(self.rubric, mutated)

    def test_cc_by_provenance_change_notice_and_fail_closed_status_are_explicit(self) -> None:
        for payload in (self.config, self.rubric, self.packet_manifest, self.exposure):
            notice = payload["redistribution_notice"]
            self.assertEqual(notice["source_license_spdx"], "CC-BY-4.0")
            self.assertEqual(
                notice["source_license_file_sha256"],
                "7e7170e3cebf88a9f60c7b8421418323c09304da1af4d5e90f4da1dc1c8a2661",
            )
            self.assertEqual(notice["source_revision"], "84fcc677e52e1902d696c32cd1a6b663e70d3993")
            self.assertIn("Anthropic", notice["attribution"])
            self.assertIn("anonymous IDs", notice["changes_made"])
        bindings = self.packet_manifest["license_evidence_bindings"]
        self.assertEqual(
            bindings["third_party_notice"],
            {
                "path": THIRD_PARTY_NOTICE_PATH.as_posix(),
                "file_sha256": EXPECTED_THIRD_PARTY_NOTICE_SHA256,
            },
        )
        self.assertEqual(
            bindings["anthropic_cc_by_license"],
            {
                "path": ANTHROPIC_LICENSE_EVIDENCE_PATH.as_posix(),
                "file_sha256": EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256,
            },
        )
        for path, expected_sha256 in (
            (THIRD_PARTY_NOTICE_PATH, EXPECTED_THIRD_PARTY_NOTICE_SHA256),
            (ANTHROPIC_LICENSE_EVIDENCE_PATH, EXPECTED_ANTHROPIC_LICENSE_EVIDENCE_SHA256),
        ):
            self.assertEqual(
                hashlib.sha256((PROJECT_ROOT / path).read_bytes()).hexdigest(),
                expected_sha256,
            )
        self.assertEqual(self.config["implementation_status"], PREPARATION_STATUS)
        self.assertFalse(self.config["execution_authorized"])
        self.assertFalse(self.config["readiness"]["g1_passed"])
        self.assertEqual(self.audit["overall_status"], "PACKET_PREPARED_REVIEWS_NOT_RUN")
        self.assertFalse(self.audit["g1_ready"])
        self.assertEqual(self.audit["counts"]["ratings_present"], 0)

    def test_cross_file_hashes_and_byte_deterministic_rebuild(self) -> None:
        verified = verify_tracked_persona_review_assets(PROJECT_ROOT)
        self.assertTrue(verified["verified_only"])
        self.assertEqual(verified["packet_rows"], 2_304)
        self.assertEqual(
            self.exposure["rubric_sha256"],
            hashlib.sha256(self.rubric_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.exposure["packet_manifest_sha256"],
            hashlib.sha256(self.packet_manifest_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.exposure["blinded_packet_sha256"],
            hashlib.sha256(self.packet_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.audit["output_sha256"]["exposure_ledger"],
            hashlib.sha256(self.exposure_path.read_bytes()).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            summary = build_persona_review_assets(project_root=PROJECT_ROOT, output_root=output_root)
            self.assertEqual(summary["packet_rows"], 2_304)
            for relative, expected_sha in summary["outputs"].items():
                generated = output_root / relative
                tracked = PROJECT_ROOT / relative
                self.assertEqual(generated.read_bytes(), tracked.read_bytes())
                self.assertEqual(hashlib.sha256(generated.read_bytes()).hexdigest(), expected_sha)


if __name__ == "__main__":
    unittest.main()
