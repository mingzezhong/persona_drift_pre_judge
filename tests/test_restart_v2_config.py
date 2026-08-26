import pathlib
import unittest

from persona_drift.protocol import frozen_pilot_schedules

try:
    import yaml
except ImportError:  # pragma: no cover - the project environment installs PyYAML
    yaml = None


@unittest.skipIf(yaml is None, "PyYAML is unavailable in the local fallback interpreter")
class RestartConfigTests(unittest.TestCase):
    def _load(self):
        config_path = pathlib.Path(__file__).parents[1] / "configs" / "restart_v2.yaml"
        return yaml.safe_load(config_path.read_text(encoding="utf-8"))

    def test_frozen_counts_components_clocks_and_schedules(self) -> None:
        payload = self._load()
        self.assertEqual(payload["schema_version"], "restart-v2.3")
        self.assertEqual(payload["protocol_revision"], "2.3-preparation")
        self.assertEqual(
            payload["authoritative_documents"]["endorsed_design_discussion"],
            ["persona和topic的讨论.md", "topic的优化.md"],
        )
        frozen = payload["frozen"]
        self.assertEqual(frozen["main_turn"]["count"], 25)
        self.assertEqual(len(frozen["models"]), 3)
        self.assertEqual(
            frozen["activation_capture"]["components"],
            ["resid_pre", "attn_out", "mlp_out"],
        )
        self.assertEqual(
            frozen["temporal_contract"]["observational_cutoff"],
            "t_minus_after_user_t_before_assistant_t",
        )
        self.assertTrue(
            frozen["temporal_contract"]["clocks_are_distinct_estimands"]
        )
        self.assertEqual(
            frozen["topics"]["partitions"],
            {"development": 18, "calibration": 6, "untouched_test": 12},
        )
        topics = frozen["topics"]
        self.assertEqual(
            topics["machine_identity_fields"]["family_eligibility"],
            "eligible_behavioral_family_id",
        )
        self.assertTrue(
            topics["machine_identity_fields"][
                "scenario_version_is_distinct_from_conversion_template_id"
            ]
        )
        self.assertEqual(topics["total"], 36)
        self.assertEqual(
            topics["topic_scopes"]["shared_core"]["kinds"],
            {"evidence": 6, "opinion": 6},
        )
        self.assertEqual(
            topics["topic_scopes"]["family_specific"]["topics_per_family"], 6
        )
        self.assertEqual(
            topics["scope_stratification"]["shared_core"],
            {"development": 6, "calibration": 2, "untouched_test": 4},
        )
        self.assertEqual(
            topics["scope_stratification"]["each_family_specific"],
            {"development": 3, "calibration": 1, "untouched_test": 2},
        )
        self.assertEqual(topics["pilot"]["shared_topics"], 2)
        self.assertEqual(
            topics["pilot"]["family_specific_topics_per_family"], 1
        )
        self.assertEqual(
            topics["pilot"]["catalog_asset_semantics"],
            "outcome_free_quality_assurance_assets",
        )
        dose_finding = topics["pilot"]["outcome_bearing_dose_finding"]
        self.assertEqual(dose_finding["development_family_count"], 3)
        self.assertEqual(dose_finding["exposed_logical_assets"], 5)
        self.assertEqual(
            dose_finding["exposed_asset_composition"],
            {"shared_core": 2, "matching_family_specific": 3},
        )
        self.assertEqual(
            dose_finding["heldout_family_slot_outcome_access"], "forbidden"
        )
        split_manifest = topics["split_manifest"]
        self.assertTrue(split_manifest["assignment_must_be_outcome_blind"])
        self.assertTrue(split_manifest["manifest_sha256_required"])
        self.assertTrue(split_manifest["balance_diagnostics_sha256_required"])
        self.assertTrue(
            topics["turn_composition"][
                "topic_moves_and_pressure_templates_recorded_separately"
            ]
        )
        composition = topics["turn_composition"]
        self.assertTrue(composition["deterministic_composition_version_required"])
        self.assertEqual(
            composition["composed_user_turn_sha256s_per_trajectory"], 25
        )
        self.assertEqual(
            composition["pre_response_full_prompt_sha256s_per_trajectory"], 25
        )
        self.assertTrue(
            composition["composed_user_turn_sha256s_must_be_unique"]
        )
        self.assertTrue(
            composition["pre_response_full_prompt_sha256s_must_be_unique"]
        )
        self.assertTrue(
            composition["activation_snapshot_prompt_sha256_must_bind_by_turn"]
        )
        self.assertTrue(
            composition["topic_content_root"][
                "globally_unique_across_36_topics"
            ]
        )
        self.assertFalse(
            composition["topic_content_root"][
                "repeated_move_content_within_topic_allowed"
            ]
        )
        self.assertEqual(
            topics["predictor_fit_access"]["requires_both"],
            [
                "topic_split_is_development",
                "persona_role_is_seen_trait_observed_wording",
            ],
        )

        schedule_config = frozen["pressure"]["pilot_candidate_schedules"]
        config_blocks = [
            schedule_config[name]
            for name in ("S_minus_2", "S_minus_1", "S_0", "S_plus_1", "S_plus_2")
        ]
        code_blocks = [
            list(schedule.levels[::5]) for schedule in frozen_pilot_schedules()
        ]
        self.assertEqual(config_blocks, code_blocks)
        self.assertEqual(
            frozen["intervention"]["eligible_prefix_requirements"],
            [
                "completed_through_prefix_turn_without_drift",
                "maximum_planned_future_level_at_most_2",
                "all_doses_0_through_3_feasible_without_clipping",
            ],
        )
        heldout_schedule = frozen["pressure"]["heldout_family_schedule_selection"]
        self.assertEqual(
            heldout_schedule["outcome_access_during_G4_level_calibration"],
            "forbidden",
        )
        self.assertFalse(heldout_schedule["heldout_outcomes_may_select_schedule"])
        self.assertEqual(heldout_schedule["missing_frozen_rule_policy"], "stop")

        ontology = frozen["persona_ontology"]
        self.assertEqual(ontology["reported_persona_unit"], "persona_trait")
        self.assertFalse(ontology["prompt_variants_count_as_personas"])
        self.assertFalse(ontology["evaluation_items_count_as_personas"])

        sampling = payload["planning"]["persona_sampling"]
        self.assertEqual(sampling["behavioral_families"], 4)
        self.assertEqual(sampling["true_traits_per_family"], {"minimum": 4, "maximum": 6})
        self.assertEqual(sampling["total_true_traits"], {"minimum": 16, "maximum": 24})
        self.assertEqual(sampling["fully_unseen_families"], 1)

        sample = payload["planning"]["sample_design"]
        self.assertTrue(sample["status"].startswith("blocked_pending_"))
        self.assertEqual(sample["retired_flat_four_counts"]["status"], "historical_only_do_not_submit")
        logical_topics = sample["fixed_non_persona_factors"]["logical_topic_slots"]
        self.assertEqual(logical_topics["count"], 36)
        self.assertIn("not_full_persona_cross_product", logical_topics["semantics"])

    def test_topic_scoring_candidates_do_not_authorize_execution(self) -> None:
        payload = self._load()
        topic_design = payload["planning"]["topic_design"]
        self.assertFalse(topic_design["execution_authorized"])
        scoring = topic_design["suitability_scoring"]
        self.assertTrue(scoring["status"].startswith("candidate_only_open_"))
        self.assertFalse(scoring["execution_authorized"])
        self.assertEqual(scoring["candidate_scale"], {"minimum": 0, "maximum": 2})
        self.assertEqual(scoring["candidate_total_threshold"], 8)
        self.assertEqual(len(scoring["candidate_criteria_not_frozen"]), 5)
        self.assertEqual(scoring["aggregation_rule"], "open")
        self.assertEqual(scoring["rater_and_tie_rule"], "open")
        self.assertEqual(
            payload["frozen"]["topics"]["candidate_sources"]["mmlu_pro"][
                "category_quota"
            ],
            "none",
        )
        sources = payload["frozen"]["topics"]["candidate_sources"]
        required_manifest_fields = {
            "selection_outcome_blind",
            "immutable_candidate_source_item_ids",
            "candidate_items_sha256",
            "exclusion_log_sha256",
            "suitability_rubric_sha256",
        }
        self.assertEqual(
            set(sources["mmlu_pro"]["manifest_requires"]),
            required_manifest_fields,
        )
        self.assertEqual(
            set(sources["anthropic_sycophancy"]["manifest_requires"]),
            required_manifest_fields,
        )
        self.assertTrue(
            sources["anthropic_sycophancy"][
                "exact_group_ids_and_source_revision"
            ]["status"].startswith("open_must_")
        )
        frozen_screen = payload["frozen"]["topics"]["suitability_screen"]
        self.assertNotIn("required_concepts", frozen_screen)
        self.assertTrue(frozen_screen["selection_must_be_outcome_blind"])
        self.assertIn(
            "docs/topic_design_amendment_v2_3.md",
            payload["authoritative_documents"]["active_amendments"],
        )
        for gate_name in (
            "public_topic_item_ids_and_conversion_templates",
            "topic_scenario_family_ids_subtypes_and_target_family_assignments",
            "topic_suitability_scale_aggregation_raters_ties_and_threshold",
            "public_source_candidate_groups_revisions_items_and_manifest_hashes",
            "topic_scenario_manifests_with_25_moves_and_pressure_slots",
            "topic_scope_by_behavioral_family_eligibility_matrix",
            "persona_trait_variant_holdout_assignments",
            "phase_specific_X_phi_exposure_signed_manifests",
        ):
            self.assertTrue(
                payload["protocol_gates"][gate_name]["status"].startswith(
                    "open_must_"
                )
            )
        gates = payload["protocol_gates"]
        self.assertEqual(
            gates["topic_scope_by_behavioral_family_eligibility_matrix"]["status"],
            "open_must_freeze_before_G1_pass",
        )
        self.assertEqual(
            gates["persona_trait_variant_holdout_assignments"]["status"],
            "open_must_freeze_before_G2_pass",
        )
        self.assertEqual(
            gates["phase_specific_X_phi_exposure_signed_manifests"]["status"],
            "open_must_freeze_before_each_outcome_phase",
        )
        for gate_name in (
            "development_calibration_test_topic_id_assignment",
            "six_development_pilot_topic_ids",
        ):
            self.assertEqual(
                gates[gate_name]["status"],
                "open_must_freeze_before_G1_pass",
            )
        self.assertEqual(
            gates["heldout_family_schedule_transfer_or_fallback_rule"]["status"],
            "open_must_freeze_before_G6_main_outcome_reveal",
        )
        self.assertEqual(
            gates["persona_family_trait_catalog"]["status"],
            "open_must_freeze_before_G1_pass",
        )
        self.assertEqual(
            gates["persona_generalization_assignments"]["status"],
            "open_must_freeze_before_G2_pass",
        )
        self.assertNotIn(
            "persona_family_trait_catalog_and_generalization_assignments",
            gates,
        )

    def test_open_candidates_do_not_authorize_persona_or_seed_execution(self) -> None:
        payload = self._load()
        frozen_ontology = payload["frozen"]["persona_ontology"]
        self.assertNotIn("source_collection", frozen_ontology)

        source = payload["planning"]["persona_source_selection"]
        self.assertTrue(source["status"].startswith("candidate_only_open_"))
        self.assertFalse(source["execution_authorized"])
        self.assertEqual(
            source["collection_candidates"],
            ["anthropic_model_written_evals"],
        )

        poles = payload["planning"]["persona_sampling"][
            "each_family_has_two_behavioral_poles"
        ]
        self.assertTrue(poles["status"].startswith("candidate_only_open_"))
        self.assertTrue(poles["candidate_value"])
        self.assertFalse(poles["execution_authorized"])

        sample = payload["planning"]["sample_design"]
        fixed = sample["fixed_non_persona_factors"]
        for retired_key in (
            "pilot_seeds",
            "main_seeds_initial",
            "fork_continuation_seeds",
        ):
            self.assertNotIn(retired_key, fixed)
        self.assertNotIn("preregistered_seed_expansion_if_underpowered", sample)

        candidate = sample["candidate_seed_design"]
        self.assertTrue(candidate["status"].startswith("candidate_only_open_"))
        self.assertFalse(candidate["execution_authorized"])
        self.assertEqual(candidate["pilot_seeds"], 4)
        self.assertEqual(candidate["main_seeds_initial"], 8)
        self.assertEqual(candidate["fork_continuation_seeds"], 4)
        self.assertEqual(
            candidate["main_seed_expansion_if_underpowered"],
            {"from": 8, "to": 10},
        )

        gates = payload["protocol_gates"]
        for gate_name in (
            "persona_source_collection_selection",
            "persona_behavioral_pole_structure",
            "seed_counts_and_expansion_rule",
        ):
            self.assertTrue(gates[gate_name]["status"].startswith("open_must_"))

    def test_open_items_are_explicit_protocol_gates(self) -> None:
        payload = self._load()
        self.assertTrue(payload["protocol_gates"])
        for gate in payload["protocol_gates"].values():
            self.assertTrue(gate["status"].startswith("open_must_"))


if __name__ == "__main__":
    unittest.main()
