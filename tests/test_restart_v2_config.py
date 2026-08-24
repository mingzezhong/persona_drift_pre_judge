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

        sample = frozen["sample_design"]
        self.assertEqual(
            sample["pilot"]["models"]
            * sample["pilot"]["personas"]
            * sample["pilot"]["topics"]
            * sample["pilot"]["seeds"]
            * sample["pilot"]["candidate_schedules"],
            sample["pilot"]["full_trajectories"],
        )
        self.assertEqual(sample["pilot"]["full_trajectories"] * 25, 36000)
        self.assertEqual(sample["main"]["full_trajectories"], 8640)
        self.assertEqual(sample["main"]["full_trajectories"] * 25, 216000)
        self.assertEqual(sample["intervention"]["fork_continuations"], 9600)
        self.assertEqual(sample["intervention"]["fork_continuations"] * 5, 48000)
        self.assertEqual(
            sample["intervention"]["status"],
            "contingent_target_subject_to_G7_eligibility",
        )
        self.assertEqual(sample["base_plan_target_model_generated_turns"], 300000)

    def test_open_items_are_explicit_protocol_gates(self) -> None:
        payload = self._load()
        self.assertTrue(payload["protocol_gates"])
        for gate in payload["protocol_gates"].values():
            self.assertTrue(gate["status"].startswith("open_must_"))


if __name__ == "__main__":
    unittest.main()
