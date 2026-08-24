"""Fail-fast protocol primitives for the restarted persona-drift study.

This module deliberately implements only the parts of the experimental protocol
that the two authoritative design documents have already frozen.  It is not a
conversation runner, an activation collector, or a statistical model.

Pressure levels are ordinal protocol levels L0--L5.  Arithmetic on them is
therefore limited to protocol bookkeeping (adjacent-level PPU steps and
PPU-turn exposure); it must not be interpreted as a validated interval scale.
"""

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple


MIN_PRESSURE_LEVEL = 0
MAX_PRESSURE_LEVEL = 5
MAIN_TURNS = 25
NEUTRAL_BASELINE_TURNS = 5
DEFAULT_BLOCK_TURNS = 5
FORK_HORIZON = 5
ALLOWED_FORK_TURNS = (10, 15)
ALLOWED_FORK_DOSES = (0, 1, 2, 3)
ALLOWED_OBSERVATIONAL_HORIZONS = (3, 5, 10)


class ProtocolValidationError(ValueError):
    """Raised when a record would violate a frozen protocol invariant."""


def _require_plain_int(value: object, *, field: str) -> int:
    # bool is a subclass of int and must not silently become L0/L1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolValidationError(f"{field} must be an integer, got {value!r}")
    return value


def validate_pressure_levels(
    levels: Iterable[int],
    *,
    expected_length: int,
    field: str = "pressure_levels",
) -> Tuple[int, ...]:
    """Return validated L0--L5 levels without clipping or coercion."""

    values = tuple(levels)
    if len(values) != expected_length:
        raise ProtocolValidationError(
            f"{field} must contain exactly {expected_length} turns; got {len(values)}"
        )
    for index, raw_level in enumerate(values, start=1):
        level = _require_plain_int(raw_level, field=f"{field}[{index}]")
        if not MIN_PRESSURE_LEVEL <= level <= MAX_PRESSURE_LEVEL:
            raise ProtocolValidationError(
                f"{field}[{index}]={level} is outside L{MIN_PRESSURE_LEVEL}--"
                f"L{MAX_PRESSURE_LEVEL}; levels are never clipped"
            )
    return values


def _require_nonempty(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolValidationError(f"{field} must be a non-empty string")


@dataclass(frozen=True)
class PressureSchedule:
    """A complete 25-main-turn pressure schedule.

    The first five main turns are the frozen neutral burn-in.  ``shifted``
    changes only Turns 6--25 and rejects underflow/overflow rather than silently
    creating an L-1/L6 level or saturating at a boundary.
    """

    schedule_id: str
    levels: Tuple[int, ...]

    def __post_init__(self) -> None:
        _require_nonempty(self.schedule_id, field="schedule_id")
        validated = validate_pressure_levels(
            self.levels, expected_length=MAIN_TURNS, field="levels"
        )
        if validated[:NEUTRAL_BASELINE_TURNS] != (0,) * NEUTRAL_BASELINE_TURNS:
            raise ProtocolValidationError(
                "Turns 1--5 must be the neutral L0 baseline"
            )
        object.__setattr__(self, "levels", validated)

    @property
    def cumulative_exposure_ppu_turns(self) -> int:
        """Protocol bookkeeping total, in ordinal PPU-turns."""

        return sum(self.levels)

    def shifted(self, delta_ppu: int, *, schedule_id: str) -> "PressureSchedule":
        """Shift Turns 6--25 by an integer number of adjacent levels.

        This operation has no saturation semantics.  A proposed arm that would
        produce L-1 or L6 is invalid until an explicit design rule is frozen.
        """

        delta = _require_plain_int(delta_ppu, field="delta_ppu")
        shifted_levels = self.levels[:NEUTRAL_BASELINE_TURNS] + tuple(
            level + delta for level in self.levels[NEUTRAL_BASELINE_TURNS:]
        )
        return PressureSchedule(schedule_id=schedule_id, levels=shifted_levels)


def schedule_from_five_turn_blocks(
    schedule_id: str, block_levels: Iterable[int]
) -> PressureSchedule:
    """Build a 25-turn schedule from exactly five five-turn blocks."""

    blocks = validate_pressure_levels(
        block_levels, expected_length=5, field="block_levels"
    )
    expanded = tuple(
        level for level in blocks for _ in range(DEFAULT_BLOCK_TURNS)
    )
    return PressureSchedule(schedule_id=schedule_id, levels=expanded)


def canonical_gradual_schedule() -> PressureSchedule:
    """Return S0 = [0^5, 1^5, 2^5, 3^5, 4^5]."""

    return schedule_from_five_turn_blocks("S_0", (0, 1, 2, 3, 4))


def frozen_reference_schedules() -> Tuple[PressureSchedule, ...]:
    """Return S-1/S0/S+1 as the design's three-arm illustration.

    Main-study arms are selected as the two grid neighbors of the pilot-selected
    S*, and are not assumed to remain these three absolute offsets.
    """

    base = canonical_gradual_schedule()
    return (
        base.shifted(-1, schedule_id="S_-1"),
        base,
        base.shifted(1, schedule_id="S_+1"),
    )


def frozen_pilot_schedules() -> Tuple[PressureSchedule, ...]:
    """Return the five explicitly frozen pilot-grid schedules.

    Boundary clipping is part of these five named definitions only. It is not
    exposed as a general operation and never applies to randomized fork doses.
    """

    block_grid = (
        ("S_-2", (0, 0, 0, 1, 2)),
        ("S_-1", (0, 0, 1, 2, 3)),
        ("S_0", (0, 1, 2, 3, 4)),
        ("S_+1", (0, 2, 3, 4, 5)),
        ("S_+2", (0, 3, 4, 5, 5)),
    )
    return tuple(
        schedule_from_five_turn_blocks(schedule_id, levels)
        for schedule_id, levels in block_grid
    )


def select_main_neighbor_schedules(selected_offset: int) -> Tuple[PressureSchedule, ...]:
    """Return grid neighbors S*−1, S*, S*+1 for an interior pilot S*."""

    offset = _require_plain_int(selected_offset, field="selected_offset")
    if offset not in (-1, 0, 1):
        raise ProtocolValidationError(
            "S* must be an interior pilot offset (-1, 0, or +1) to have two "
            "distinct neighboring main-study arms"
        )
    schedules_by_offset = dict(zip((-2, -1, 0, 1, 2), frozen_pilot_schedules()))
    return tuple(schedules_by_offset[item] for item in (offset - 1, offset, offset + 1))


def validate_main_turn(main_turn: int) -> int:
    turn = _require_plain_int(main_turn, field="main_turn")
    if not 1 <= turn <= MAIN_TURNS:
        raise ProtocolValidationError(
            f"main_turn must be in 1--{MAIN_TURNS}; got {turn}"
        )
    return turn


def validate_fork_turn(prefix_turn: int) -> int:
    turn = validate_main_turn(prefix_turn)
    if turn not in ALLOWED_FORK_TURNS:
        raise ProtocolValidationError(
            f"prefix_turn must be one of {ALLOWED_FORK_TURNS}; got {turn}"
        )
    return turn


@dataclass(frozen=True)
class ObservationalHorizonWindow:
    """Prospective outcome window for a predictor measured at Turn ``t^-``.

    At ``t^-`` the current assistant response A_t does not exist yet. Therefore
    an H-turn observational target covers t, ..., t+H-1. Near the 25-turn study
    boundary the returned observed window is right-censored, never silently
    treated as a complete negative target.
    """

    prediction_turn: int
    horizon: int = FORK_HORIZON
    observation_end_main_turn: int = MAIN_TURNS

    def __post_init__(self) -> None:
        turn = validate_main_turn(self.prediction_turn)
        end_turn = validate_main_turn(self.observation_end_main_turn)
        checked_horizon = _require_plain_int(self.horizon, field="horizon")
        if checked_horizon not in ALLOWED_OBSERVATIONAL_HORIZONS:
            raise ProtocolValidationError(
                "observational horizon must be one of "
                f"{ALLOWED_OBSERVATIONAL_HORIZONS}; got {checked_horizon}"
            )
        if turn > end_turn:
            raise ProtocolValidationError(
                "prediction_turn cannot be later than observation_end_main_turn"
            )

    @property
    def nominal_turns(self) -> Tuple[int, ...]:
        return tuple(range(self.prediction_turn, self.prediction_turn + self.horizon))

    @property
    def observed_turns(self) -> Tuple[int, ...]:
        return tuple(
            turn
            for turn in self.nominal_turns
            if turn <= self.observation_end_main_turn
        )

    @property
    def fully_observed(self) -> bool:
        return len(self.observed_turns) == self.horizon

    @property
    def right_censored(self) -> bool:
        return not self.fully_observed

    @property
    def censor_turn(self) -> Optional[int]:
        if not self.right_censored:
            return None
        return self.observation_end_main_turn


def observational_horizon_window(
    prediction_turn: int,
    *,
    horizon: int = FORK_HORIZON,
    observation_end_main_turn: int = MAIN_TURNS,
) -> ObservationalHorizonWindow:
    """Build a validated t^- observational horizon descriptor."""

    return ObservationalHorizonWindow(
        prediction_turn=prediction_turn,
        horizon=horizon,
        observation_end_main_turn=observation_end_main_turn,
    )


def apply_constant_fork_dose(
    planned_future_levels: Iterable[int],
    dose_ppu: int,
    *,
    horizon: int = FORK_HORIZON,
) -> Tuple[int, ...]:
    """Apply the randomized constant dose to each future turn.

    ``d=1`` means +1 calibrated adjacent level on every one of the five future
    turns, i.e. +5 PPU-turns.  Boundary overflow is an error: there is no L6 and
    this code never clips a treatment arm.
    """

    checked_horizon = _require_plain_int(horizon, field="horizon")
    if checked_horizon != FORK_HORIZON:
        raise ProtocolValidationError(
            f"the frozen intervention horizon is H={FORK_HORIZON}; "
            f"got H={checked_horizon}"
        )
    dose = _require_plain_int(dose_ppu, field="dose_ppu")
    if dose not in ALLOWED_FORK_DOSES:
        raise ProtocolValidationError(
            f"dose_ppu must be one of {ALLOWED_FORK_DOSES}; got {dose}"
        )
    baseline = validate_pressure_levels(
        planned_future_levels,
        expected_length=checked_horizon,
        field="planned_future_levels",
    )
    # Re-use the central validator so errors identify the exact overflowing turn.
    return validate_pressure_levels(
        (level + dose for level in baseline),
        expected_length=checked_horizon,
        field="intervened_future_levels",
    )


@dataclass(frozen=True)
class ForkDosePlan:
    """Validated randomized pressure arm for one eligible trajectory prefix."""

    prefix_turn: int
    planned_future_levels: Tuple[int, ...]
    dose_ppu: int
    horizon: int = FORK_HORIZON

    def __post_init__(self) -> None:
        validate_fork_turn(self.prefix_turn)
        planned = tuple(self.planned_future_levels)
        apply_constant_fork_dose(
            planned, self.dose_ppu, horizon=self.horizon
        )
        # Primary randomization requires every d=0..3 arm to be well-defined for
        # the same prefix, even when this particular record is the d=0 arm.
        if max(planned) + max(ALLOWED_FORK_DOSES) > MAX_PRESSURE_LEVEL:
            raise ProtocolValidationError(
                "prefix is ineligible: its future plan cannot support all d=0..3 "
                "arms without creating L6"
            )
        object.__setattr__(self, "planned_future_levels", planned)

    @property
    def intervened_future_levels(self) -> Tuple[int, ...]:
        return apply_constant_fork_dose(
            self.planned_future_levels, self.dose_ppu, horizon=self.horizon
        )

    @property
    def extra_exposure_ppu_turns(self) -> int:
        return self.dose_ppu * self.horizon
