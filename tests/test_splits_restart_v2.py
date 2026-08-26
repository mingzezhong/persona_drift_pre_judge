from collections import Counter
from dataclasses import replace
import hashlib
import unittest

from persona_drift.protocol import ProtocolValidationError
from persona_drift.splits import (
    SharedCoreKind,
    TopicAnchor,
    TopicCandidatePoolManifest,
    TopicScenarioManifest,
    TopicScope,
    TopicSource,
    TopicSplitPlan,
    TopicSuitabilityScore,
    TopicSuitabilityRubricManifest,
    compute_topic_content_root_sha256,
    validate_anchor_catalog,
    validate_no_root_leakage,
    validate_topic_scenario_catalog,
    validate_topic_family_access,
)


FAMILIES = tuple(f"family-{index}" for index in range(4))
CRITERIA = ("criterion-a", "criterion-b")


def suitability(value=1.0):
    return tuple(
        TopicSuitabilityScore(criterion_id=criterion_id, score=value)
        for criterion_id in CRITERIA
    )


def move_hashes(topic_id):
    return tuple(
        hashlib.sha256(
            f"{topic_id}:move:{turn}".encode("utf-8")
        ).hexdigest()
        for turn in range(1, 26)
    )


def make_rubric():
    return TopicSuitabilityRubricManifest(
        rubric_id="topic-rubric-v1",
        criterion_ids=CRITERIA,
        manifest_sha256="b" * 64,
        scoring_rule_sha256="1" * 64,
        aggregation_rule_sha256="2" * 64,
        rater_protocol_sha256="3" * 64,
        decision_rule_sha256="4" * 64,
    )


def make_candidate_pools():
    mmlu_items = tuple(
        f"public-shared-{index}" for index in range(6)
    ) + tuple(
        f"public-{family}-topic-{index}"
        for family in FAMILIES
        for index in range(6)
    )
    anthropic_items = tuple(
        f"public-shared-{index}" for index in range(6, 12)
    )
    return (
        TopicCandidatePoolManifest(
            source=TopicSource.MMLU_PRO,
            manifest_id="mmlu-pool-v1",
            source_revision="frozen-revision",
            source_group_ids=("economics",) + tuple(
                f"candidate-category-{index}" for index in range(13)
            ),
            candidate_source_item_ids=mmlu_items,
            candidate_items_sha256="5" * 64,
            exclusion_log_sha256="6" * 64,
            suitability_rubric_sha256="b" * 64,
        ),
        TopicCandidatePoolManifest(
            source=TopicSource.ANTHROPIC_SYCOPHANCY,
            manifest_id="anthropic-pool-v1",
            source_revision="frozen-revision",
            source_group_ids=("opinion", "other-candidate-group"),
            candidate_source_item_ids=anthropic_items,
            candidate_items_sha256="7" * 64,
            exclusion_log_sha256="8" * 64,
            suitability_rubric_sha256="b" * 64,
        ),
    )


def catalog_kwargs():
    return {
        "known_behavioral_family_ids": FAMILIES,
        "source_candidate_pool_manifests": make_candidate_pools(),
        "suitability_rubric_manifest": make_rubric(),
    }


def provenance(topic_id, source):
    return {
        "source_url": "https://example.invalid/frozen-source",
        "source_revision": "frozen-revision",
        "source_license": "verified-license",
        "source_file_sha256": hashlib.sha256(
            ("file:" + topic_id).encode()
        ).hexdigest(),
        "source_item_sha256": hashlib.sha256(
            ("item:" + topic_id).encode()
        ).hexdigest(),
        "scenario_template_sha256": "a" * 64,
        "scenario_manifest_sha256": hashlib.sha256(
            ("scenario-manifest:" + topic_id).encode("utf-8")
        ).hexdigest(),
        "topic_content_root_sha256": (
            compute_topic_content_root_sha256(move_hashes(topic_id))
        ),
        "suitability_screen_manifest_sha256": "b" * 64,
        "selection_review_sha256": "c" * 64,
        "suitability_scores": suitability(),
        "native_stance_policy": (
            "not_applicable"
            if source is TopicSource.MMLU_PRO
            else "remove_or_standardize"
        ),
    }


def make_anchor(
    topic_id,
    *,
    scope,
    target=None,
    shared_kind=None,
    source=TopicSource.MMLU_PRO,
):
    return TopicAnchor(
        topic_id=topic_id,
        topic_scope=scope,
        scenario_family_id=(
            f"scenario-{target}" if target is not None else "shared-core"
        ),
        eligible_behavioral_family_id=target,
        scenario_subtype=f"subtype-{topic_id}",
        shared_core_kind=shared_kind,
        source=source,
        source_item_id=f"public-{topic_id}",
        source_group=(
            "economics"
            if source is TopicSource.MMLU_PRO
            else "opinion"
        ),
        conversion_template_id="discussion-v23",
        scenario_version="scenario-v23",
        **provenance(topic_id, source),
    )


def make_catalog():
    anchors = []
    for index in range(12):
        kind = (
            SharedCoreKind.EVIDENCE
            if index < 6
            else SharedCoreKind.OPINION
        )
        source = (
            TopicSource.MMLU_PRO
            if kind is SharedCoreKind.EVIDENCE
            else TopicSource.ANTHROPIC_SYCOPHANCY
        )
        anchors.append(
            make_anchor(
                f"shared-{index}",
                scope=TopicScope.SHARED_CORE,
                shared_kind=kind,
                source=source,
            )
        )
    for family_id in FAMILIES:
        for index in range(6):
            anchors.append(
                make_anchor(
                    f"{family_id}-topic-{index}",
                    scope=TopicScope.FAMILY_SPECIFIC,
                    target=family_id,
                )
            )
    return tuple(anchors)


def make_split():
    shared = tuple(f"shared-{index}" for index in range(12))
    by_family = {
        family: tuple(f"{family}-topic-{index}" for index in range(6))
        for family in FAMILIES
    }
    development = shared[:6] + tuple(
        topic for family in FAMILIES for topic in by_family[family][:3]
    )
    calibration = shared[6:8] + tuple(
        by_family[family][3] for family in FAMILIES
    )
    untouched = shared[8:12] + tuple(
        topic for family in FAMILIES for topic in by_family[family][4:]
    )
    pilot = shared[:2] + tuple(by_family[family][0] for family in FAMILIES)
    return TopicSplitPlan(
        split_algorithm_id="scenario-stratified-split",
        split_algorithm_version="v1",
        split_seed=23,
        balance_diagnostics_sha256="9" * 64,
        manifest_sha256="8" * 64,
        assignment_outcome_blind=True,
        development=development,
        calibration=calibration,
        untouched_test=untouched,
        pilot=pilot,
    )


def make_scenarios(catalog=None):
    catalog = make_catalog() if catalog is None else tuple(catalog)
    return tuple(
        TopicScenarioManifest(
            topic_id=anchor.topic_id,
            scenario_version=anchor.scenario_version,
            scenario_template_sha256=anchor.scenario_template_sha256,
            manifest_sha256=anchor.scenario_manifest_sha256,
            topic_content_root_sha256=anchor.topic_content_root_sha256,
            ordered_topic_move_ids=tuple(
                f"{anchor.topic_id}-move-{turn}" for turn in range(1, 26)
            ),
            ordered_topic_move_sha256s=move_hashes(anchor.topic_id),
            pressure_slot_ids=tuple(
                f"{anchor.topic_id}-pressure-slot-{turn}"
                for turn in range(1, 26)
            ),
        )
        for anchor in catalog
    )


class TopicSplitTests(unittest.TestCase):
    def test_valid_hierarchy_split_and_pilot(self):
        catalog = validate_anchor_catalog(
            make_catalog(), **catalog_kwargs()
        )
        plan = make_split()
        plan.validate_against_catalog(
            catalog, **catalog_kwargs()
        )
        self.assertEqual(len(plan.all_main_topics), 36)
        self.assertEqual(plan.partition_for("shared-0"), "development")
        self.assertNotEqual(
            catalog[0].conversion_template_id,
            catalog[0].scenario_version,
        )

    def test_partitions_are_disjoint_and_pilot_is_development(self):
        plan = make_split()
        with self.assertRaisesRegex(ProtocolValidationError, "overlap"):
            replace(
                plan,
                calibration=(plan.development[0],) + plan.calibration[1:],
            )
        with self.assertRaisesRegex(ProtocolValidationError, "subset of development"):
            replace(
                plan,
                pilot=plan.untouched_test[:6],
            )

    def test_split_manifest_provenance_is_fail_closed(self):
        plan = make_split()
        self.assertTrue(plan.assignment_outcome_blind)
        self.assertEqual(plan.split_seed, 23)
        with self.assertRaisesRegex(ProtocolValidationError, "split_seed"):
            replace(plan, split_seed=True)
        with self.assertRaisesRegex(ProtocolValidationError, "outcome-blind"):
            replace(plan, assignment_outcome_blind=False)
        with self.assertRaisesRegex(ProtocolValidationError, "64 lowercase"):
            replace(plan, balance_diagnostics_sha256="bad")

    def test_scope_target_contract_is_fail_closed(self):
        base = make_catalog()[0]
        with self.assertRaisesRegex(ProtocolValidationError, "cannot bind"):
            replace(base, eligible_behavioral_family_id=FAMILIES[0])
        family_topic = make_catalog()[12]
        with self.assertRaisesRegex(ProtocolValidationError, "require an eligible"):
            replace(family_topic, eligible_behavioral_family_id=None)
        catalog = list(make_catalog())
        catalog[12] = replace(
            catalog[12], eligible_behavioral_family_id="unknown-family"
        )
        with self.assertRaisesRegex(ProtocolValidationError, "unknown eligible families"):
            validate_anchor_catalog(
                catalog, **catalog_kwargs()
            )

    def test_suitability_is_generic_manifest_bound_and_outcome_blind(self):
        base = make_catalog()[0]
        catalog = list(make_catalog())
        catalog[0] = replace(
            base, suitability_scores=base.suitability_scores[:-1]
        )
        with self.assertRaisesRegex(ProtocolValidationError, "frozen rubric"):
            validate_anchor_catalog(catalog, **catalog_kwargs())
        with self.assertRaisesRegex(ProtocolValidationError, "outcome-blind"):
            replace(base, selection_outcome_blind=False)
        # The executable rubric may have any number of named criteria and scale.
        replace(base, suitability_scores=suitability(7.5))

    def test_mmlu_categories_are_candidate_pool_not_quota(self):
        catalog = validate_anchor_catalog(
            make_catalog(), **catalog_kwargs()
        )
        selected_categories = Counter(
            item.source_group for item in catalog
            if item.source is TopicSource.MMLU_PRO
        )
        self.assertEqual(set(selected_categories), {"economics"})
        mmlu_pool, _ = make_candidate_pools()
        self.assertEqual(len(mmlu_pool.source_group_ids), 14)
        with self.assertRaisesRegex(ProtocolValidationError, "quota"):
            replace(mmlu_pool, selected_group_quota=2)

    def test_both_source_candidate_universes_are_required_and_bound(self):
        catalog = list(make_catalog())
        pools = make_candidate_pools()
        with self.assertRaisesRegex(ProtocolValidationError, "each topic source"):
            validate_anchor_catalog(
                catalog,
                known_behavioral_family_ids=FAMILIES,
                source_candidate_pool_manifests=(pools[0],),
                suitability_rubric_manifest=make_rubric(),
            )
        with self.assertRaisesRegex(ProtocolValidationError, "each topic source"):
            validate_anchor_catalog(
                catalog,
                known_behavioral_family_ids=FAMILIES,
                source_candidate_pool_manifests=(pools[0], pools[0]),
                suitability_rubric_manifest=make_rubric(),
            )
        anthropic_index = next(
            index for index, anchor in enumerate(catalog)
            if anchor.source is TopicSource.ANTHROPIC_SYCOPHANCY
        )
        catalog[anthropic_index] = replace(
            catalog[anthropic_index],
            source_item_id="not-in-frozen-candidate-universe",
        )
        with self.assertRaisesRegex(ProtocolValidationError, "source_item_id"):
            validate_anchor_catalog(catalog, **catalog_kwargs())
        catalog = list(make_catalog())
        catalog[anthropic_index] = replace(
            catalog[anthropic_index],
            source_revision="different-revision",
        )
        with self.assertRaisesRegex(ProtocolValidationError, "revision"):
            validate_anchor_catalog(catalog, **catalog_kwargs())
        with self.assertRaisesRegex(ProtocolValidationError, "outcome-blind"):
            replace(pools[1], selection_outcome_blind=False)

    def test_split_and_pilot_composition_are_enforced(self):
        catalog = make_catalog()
        plan = make_split()
        bad_development = (
            plan.development[:-1] + (plan.untouched_test[0],)
        )
        bad_untouched = (
            (plan.development[-1],) + plan.untouched_test[1:]
        )
        bad_plan = replace(
            plan,
            development=bad_development,
            untouched_test=bad_untouched,
        )
        with self.assertRaisesRegex(ProtocolValidationError, "composition"):
            bad_plan.validate_against_catalog(
                catalog, **catalog_kwargs()
            )
        bad_pilot = plan.development[:3] + tuple(
            f"{family}-topic-0" for family in FAMILIES[:3]
        )
        bad_plan = replace(plan, pilot=bad_pilot)
        with self.assertRaisesRegex(ProtocolValidationError, "two shared"):
            bad_plan.validate_against_catalog(
                catalog, **catalog_kwargs()
            )

    def test_shared_and_family_specific_access(self):
        catalog = make_catalog()
        validate_topic_family_access(
            catalog[0], behavioral_family_id=FAMILIES[3]
        )
        validate_topic_family_access(
            catalog[12], behavioral_family_id=FAMILIES[0]
        )
        with self.assertRaisesRegex(ProtocolValidationError, "eligible"):
            validate_topic_family_access(
                catalog[12], behavioral_family_id=FAMILIES[1]
            )

    def test_native_stance_and_provenance_are_fail_closed(self):
        anthropic = make_catalog()[6]
        with self.assertRaisesRegex(ProtocolValidationError, "native-stance"):
            replace(anthropic, native_stance_policy="not_applicable")
        with self.assertRaisesRegex(ProtocolValidationError, "64 lowercase"):
            replace(anthropic, suitability_screen_manifest_sha256="bad")

    def test_scenario_manifest_requires_25_pressure_free_moves_and_slots(self):
        manifest = make_scenarios()[0]
        self.assertEqual(len(manifest.ordered_topic_move_ids), 25)
        self.assertEqual(len(manifest.pressure_slot_ids), 25)
        with self.assertRaisesRegex(ProtocolValidationError, "exactly 25"):
            replace(manifest, ordered_topic_move_ids=("one",))
        with self.assertRaisesRegex(ProtocolValidationError, "pressure-free"):
            replace(manifest, topic_moves_are_pressure_free=False)
        repeated = ("a" * 64,) * 25
        with self.assertRaisesRegex(ProtocolValidationError, "unique"):
            replace(
                manifest,
                ordered_topic_move_sha256s=repeated,
                topic_content_root_sha256=compute_topic_content_root_sha256(repeated),
            )
        with self.assertRaisesRegex(ProtocolValidationError, "does not match"):
            replace(manifest, topic_content_root_sha256="0" * 64)

    def test_topic_content_roots_are_globally_unique(self):
        catalog = list(make_catalog())
        catalog[20] = replace(
            catalog[20],
            topic_content_root_sha256=catalog[0].topic_content_root_sha256,
        )
        with self.assertRaisesRegex(ProtocolValidationError, "content roots"):
            validate_anchor_catalog(catalog, **catalog_kwargs())

    def test_scenario_catalog_binding_checks_non_current_topics(self):
        catalog = make_catalog()
        scenarios = list(make_scenarios(catalog))
        validate_topic_scenario_catalog(catalog, scenarios)
        scenarios[20] = replace(
            scenarios[20], scenario_template_sha256="0" * 64
        )
        with self.assertRaisesRegex(ProtocolValidationError, "identity mismatch"):
            validate_topic_scenario_catalog(catalog, scenarios)

    def test_root_groups_cannot_leak(self):
        validate_no_root_leakage(
            {"development": ("root-a",), "untouched_test": ("root-b",)}
        )
        with self.assertRaisesRegex(ProtocolValidationError, "root-group leakage"):
            validate_no_root_leakage(
                {"development": ("root-a",), "untouched_test": ("root-a",)}
            )


if __name__ == "__main__":
    unittest.main()
