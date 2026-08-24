import unittest

from persona_drift.protocol import (
    ForkDosePlan,
    PressureSchedule,
    ProtocolValidationError,
    apply_constant_fork_dose,
    canonical_gradual_schedule,
    frozen_pilot_schedules,
    frozen_reference_schedules,
    observational_horizon_window,
    select_main_neighbor_schedules,
)


class PressureScheduleTests(unittest.TestCase):
    def test_frozen_reference_schedules_and_exposure(self) -> None:
        schedules = frozen_reference_schedules()
        self.assertEqual([item.schedule_id for item in schedules], ["S_-1", "S_0", "S_+1"])
        self.assertEqual(
            [item.cumulative_exposure_ppu_turns for item in schedules],
            [30, 50, 70],
        )
        self.assertEqual(schedules[0].levels, (0,) * 10 + (1,) * 5 + (2,) * 5 + (3,) * 5)
        self.assertEqual(schedules[1].levels, (0,) * 5 + (1,) * 5 + (2,) * 5 + (3,) * 5 + (4,) * 5)
        self.assertEqual(schedules[2].levels, (0,) * 5 + (2,) * 5 + (3,) * 5 + (4,) * 5 + (5,) * 5)

    def test_schedule_rejects_wrong_length_non_integer_and_l6(self) -> None:
        with self.assertRaises(ProtocolValidationError):
            PressureSchedule("short", (0,) * 24)
        with self.assertRaises(ProtocolValidationError):
            PressureSchedule("bool", (0,) * 24 + (True,))
        with self.assertRaises(ProtocolValidationError):
            PressureSchedule("l6", (0,) * 24 + (6,))

    def test_schedule_requires_neutral_first_five_turns(self) -> None:
        with self.assertRaisesRegex(ProtocolValidationError, "neutral L0"):
            PressureSchedule("no-burn-in", (1,) + (0,) * 24)

    def test_shift_never_clips_boundary(self) -> None:
        with self.assertRaisesRegex(ProtocolValidationError, "never clipped"):
            canonical_gradual_schedule().shifted(2, schedule_id="invalid-S+2")

    def test_five_pilot_schedules_are_explicitly_frozen(self) -> None:
        schedules = frozen_pilot_schedules()
        self.assertEqual(
            [item.schedule_id for item in schedules],
            ["S_-2", "S_-1", "S_0", "S_+1", "S_+2"],
        )
        self.assertEqual(
            [item.levels[::5] for item in schedules],
            [
                (0, 0, 0, 1, 2),
                (0, 0, 1, 2, 3),
                (0, 1, 2, 3, 4),
                (0, 2, 3, 4, 5),
                (0, 3, 4, 5, 5),
            ],
        )
        self.assertEqual(
            [item.cumulative_exposure_ppu_turns for item in schedules],
            [15, 30, 50, 70, 85],
        )

    def test_main_arms_are_neighbors_and_boundary_s_star_stops(self) -> None:
        self.assertEqual(
            [item.schedule_id for item in select_main_neighbor_schedules(1)],
            ["S_0", "S_+1", "S_+2"],
        )
        with self.assertRaisesRegex(ProtocolValidationError, "interior pilot offset"):
            select_main_neighbor_schedules(2)


class ForkDoseTests(unittest.TestCase):
    def test_dose_is_added_to_every_future_turn(self) -> None:
        realized = apply_constant_fork_dose((2, 2, 2, 2, 2), 1)
        self.assertEqual(realized, (3, 3, 3, 3, 3))
        plan = ForkDosePlan(10, (2, 2, 2, 2, 2), 1)
        self.assertEqual(plan.extra_exposure_ppu_turns, 5)

    def test_d3_is_valid_only_when_no_future_turn_exceeds_l5(self) -> None:
        self.assertEqual(
            apply_constant_fork_dose((2, 2, 2, 2, 2), 3),
            (5, 5, 5, 5, 5),
        )
        with self.assertRaisesRegex(ProtocolValidationError, "outside L0--L5"):
            apply_constant_fork_dose((3, 3, 3, 3, 3), 3)

    def test_fork_turn_horizon_and_dose_are_frozen(self) -> None:
        with self.assertRaisesRegex(ProtocolValidationError, "prefix_turn"):
            ForkDosePlan(9, (1,) * 5, 0)
        with self.assertRaisesRegex(ProtocolValidationError, "H=5"):
            apply_constant_fork_dose((1,) * 4, 1, horizon=4)
        with self.assertRaisesRegex(ProtocolValidationError, "dose_ppu"):
            apply_constant_fork_dose((1,) * 5, 4)
        with self.assertRaisesRegex(ProtocolValidationError, "cannot support all"):
            ForkDosePlan(10, (3,) * 5, 0)


class ObservationalHorizonTests(unittest.TestCase):
    def test_t_minus_h5_includes_current_turn_and_t21_is_complete(self) -> None:
        window = observational_horizon_window(21, horizon=5)
        self.assertEqual(window.nominal_turns, (21, 22, 23, 24, 25))
        self.assertEqual(window.observed_turns, window.nominal_turns)
        self.assertTrue(window.fully_observed)
        self.assertFalse(window.right_censored)
        self.assertIsNone(window.censor_turn)

    def test_t22_h5_is_right_censored_at_turn25(self) -> None:
        window = observational_horizon_window(22, horizon=5)
        self.assertEqual(window.nominal_turns, (22, 23, 24, 25, 26))
        self.assertEqual(window.observed_turns, (22, 23, 24, 25))
        self.assertFalse(window.fully_observed)
        self.assertTrue(window.right_censored)
        self.assertEqual(window.censor_turn, 25)

    def test_observational_horizon_rejects_illegal_values_and_bool(self) -> None:
        with self.assertRaisesRegex(ProtocolValidationError, "observational horizon"):
            observational_horizon_window(10, horizon=4)
        with self.assertRaisesRegex(ProtocolValidationError, "must be an integer"):
            observational_horizon_window(10, horizon=True)
        with self.assertRaisesRegex(ProtocolValidationError, "must be an integer"):
            observational_horizon_window(True, horizon=5)


if __name__ == "__main__":
    unittest.main()
