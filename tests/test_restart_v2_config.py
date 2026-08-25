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
        self.assertEqual(payload["schema_version"], "restart-v2.2")
        self.assertEqual(payload["protocol_revision"], "2.2-preparation")
        self.assertEqual(
            payload["authoritative_documents"]["endorsed_design_discussion"],
            ["persona和topic的讨论.md"],
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
            {"development": 15, "calibration": 5, "untouched_test": 10},
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
        self.assertEqual(sample["fixed_non_persona_factors"]["main_topics"], 30)

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
