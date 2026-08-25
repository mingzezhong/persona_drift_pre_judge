from dataclasses import replace
import unittest

from persona_drift.personas import PersonaGeneralizationRole
from persona_drift.protocol import ProtocolValidationError, canonical_gradual_schedule
from persona_drift.records import (
    ActivationComponent,
    ActivationSnapshotMetadata,
    DriftOutcome,
    DriftOutcomeMetadata,
    ForkMetadata,
    ModelId,
    NumericDType,
    StudyPhase,
    TopicPartition,
    TrajectoryMetadata,
    create_manifest_validated_trajectory_metadata,
    validate_activation_coverage,
    validate_feature_cutoff,
    validate_trajectory_persona_identity,
)
from test_personas_restart_v2 import digest, make_catalog, make_plan


class RecordTests(unittest.TestCase):
    def _trajectory_values(self, **overrides):
        schedule = canonical_gradual_schedule()
        values = {
            "trajectory_id": "traj-0001",
            "phase": StudyPhase.MAIN,
            "model_id": ModelId.QWEN3_8B,
            "model_revision": "revision-sha",
            "tokenizer_revision": "tokenizer-sha",
            "chat_template_version": "qwen-chat-v1",
            "behavioral_family_id": "risk-family",
            "persona_trait_id": "risk-averse",
            "persona_prompt_variant_id": "risk-averse-v1",
            "persona_generalization_role": PersonaGeneralizationRole.SEEN_TRAIT_OBSERVED_WORDING,
            "persona_prompt_sha256": "d" * 64,
            "persona_catalog_sha256": "e" * 64,
            "persona_generalization_plan_sha256": "9" * 64,
            "pressure_family": "encourage-risk",
            "topic_id": "mmlu-econ-001",
            "scenario_version": "scenario-v1",
            "scenario_sha256": "f" * 64,
            "topic_move_ids": tuple(f"move-{turn}" for turn in range(1, 26)),
            "topic_move_sha256s": tuple("a" * 64 for _ in range(25)),
            "topic_partition": TopicPartition.DEVELOPMENT,
            "seed": 0,
            "schedule_id": schedule.schedule_id,
            "pressure_levels": schedule.levels,
            "pressure_template_ids": tuple(f"template-{turn}" for turn in range(1, 26)),
            "generation_config_sha256": "c" * 64,
        }
        values.update(overrides)
        return values

    def _trajectory(self, **overrides):
        return TrajectoryMetadata(**self._trajectory_values(**overrides))

    def test_valid_trajectory_serializes_enums_and_levels(self) -> None:
        record = self._trajectory()
        payload = record.to_dict()
        self.assertEqual(payload["model_id"], "Qwen/Qwen3-8B")
        self.assertEqual(payload["persona_trait_id"], "risk-averse")
        self.assertEqual(payload["persona_generalization_role"], "seen_trait_observed_wording")
        self.assertEqual(len(payload["pressure_levels"]), 25)

    def test_pilot_topic_must_be_development(self) -> None:
        with self.assertRaisesRegex(ProtocolValidationError, "pilot topics"):
            self._trajectory(
                phase=StudyPhase.PILOT,
                topic_partition=TopicPartition.UNTOUCHED_TEST,
            )

    def test_persona_hierarchy_and_topic_pressure_components_are_required(self) -> None:
        with self.assertRaisesRegex(ProtocolValidationError, "persona_prompt_sha256"):
            self._trajectory(persona_prompt_sha256="not-a-hash")
        with self.assertRaisesRegex(ProtocolValidationError, "PersonaGeneralizationRole"):
            self._trajectory(persona_generalization_role="development")
        with self.assertRaisesRegex(ProtocolValidationError, "topic_move_ids"):
            self._trajectory(topic_move_ids=("move-1",))
        with self.assertRaisesRegex(ProtocolValidationError, "topic_move_sha256s"):
            self._trajectory(topic_move_sha256s=("a" * 64,))

    def test_manifest_backed_factory_accepts_a_catalog_assignment(self) -> None:
        catalog = make_catalog()
        plan = make_plan(catalog)
        values = self._trajectory_values(
            behavioral_family_id="family-0",
            persona_trait_id="trait-0-0",
            persona_prompt_variant_id="variant-0-0-observed",
            persona_generalization_role=(
                PersonaGeneralizationRole.SEEN_TRAIT_OBSERVED_WORDING
            ),
            persona_prompt_sha256=digest("variant-0-0-observed"),
        )
        values.pop("persona_catalog_sha256")
        values.pop("persona_generalization_plan_sha256")
        record = create_manifest_validated_trajectory_metadata(
            persona_catalog=catalog,
            persona_generalization_plan=plan,
            persona_catalog_manifest_sha256="e" * 64,
            persona_generalization_plan_manifest_sha256="9" * 64,
            **values,
        )
        self.assertIs(
            validate_trajectory_persona_identity(
                record,
                persona_catalog=catalog,
                persona_generalization_plan=plan,
                persona_catalog_manifest_sha256="e" * 64,
                persona_generalization_plan_manifest_sha256="9" * 64,
            ),
            record,
        )

    def test_manifest_backed_identity_rejects_invalid_combinations(self) -> None:
        catalog = make_catalog()
        plan = make_plan(catalog)
        record = self._trajectory(
            behavioral_family_id="family-0",
            persona_trait_id="trait-0-0",
            persona_prompt_variant_id="variant-0-0-observed",
            persona_generalization_role=(
                PersonaGeneralizationRole.SEEN_TRAIT_OBSERVED_WORDING
            ),
            persona_prompt_sha256=digest("variant-0-0-observed"),
        )

        def validate(candidate):
            return validate_trajectory_persona_identity(
                candidate,
                persona_catalog=catalog,
                persona_generalization_plan=plan,
                persona_catalog_manifest_sha256="e" * 64,
                persona_generalization_plan_manifest_sha256="9" * 64,
            )

        invalid_records = (
            replace(record, behavioral_family_id="family-1"),
            replace(record, persona_trait_id="trait-0-1"),
            replace(
                record,
                persona_generalization_role=(
                    PersonaGeneralizationRole.UNSEEN_PROMPT_WORDING
                ),
            ),
            replace(record, persona_prompt_sha256="0" * 64),
            replace(record, persona_catalog_sha256="0" * 64),
            replace(record, persona_generalization_plan_sha256="0" * 64),
        )
        for invalid in invalid_records:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ProtocolValidationError):
                    validate(invalid)

    def test_primary_activation_is_pre_response_final_prompt_token(self) -> None:
        valid = {
            "trajectory_id": "traj-0001",
            "main_turn": 10,
            "layer_index": 5,
            "component": ActivationComponent.RESID_PRE,
            "hidden_size": 4096,
            "vector_shape": (4096,),
            "storage_dtype": NumericDType.BFLOAT16,
            "compute_dtype": NumericDType.BFLOAT16,
            "vector_uri": "activations/traj-0001/turn-10/layer-05.pt",
            "vector_sha256": "a" * 64,
            "prompt_sha256": "b" * 64,
            "token_index": 123,
            "hook_contract_version": "hooks-v1",
            "available_at_turn": 10,
        }
        ActivationSnapshotMetadata(**valid)
        with self.assertRaisesRegex(ProtocolValidationError, "pre_response"):
            ActivationSnapshotMetadata(**valid, timing="post_response")
        with self.assertRaisesRegex(ProtocolValidationError, "final_prompt_token"):
            ActivationSnapshotMetadata(**valid, token_position="response_token_mean")
        with self.assertRaisesRegex(ProtocolValidationError, "t_minus_pre_response"):
            ActivationSnapshotMetadata(**valid, availability_boundary="t_plus_post_response")
        with self.assertRaisesRegex(ProtocolValidationError, "float32 primary storage"):
            ActivationSnapshotMetadata(
                **{**valid, "storage_dtype": NumericDType.FLOAT32}
            )
        ActivationSnapshotMetadata(
            **{**valid, "compute_dtype": NumericDType.FLOAT32}
        )

    def test_future_snapshot_cannot_enter_earlier_prediction_cutoff(self) -> None:
        def snapshot(turn):
            return ActivationSnapshotMetadata(
                trajectory_id="traj-0001",
                main_turn=turn,
                layer_index=5,
                component=ActivationComponent.RESID_PRE,
                hidden_size=4096,
                vector_shape=(4096,),
                storage_dtype=NumericDType.BFLOAT16,
                compute_dtype=NumericDType.BFLOAT16,
                vector_uri=f"activations/turn-{turn}.pt",
                vector_sha256="a" * 64,
                prompt_sha256="b" * 64,
                token_index=123,
                hook_contract_version="hooks-v1",
                available_at_turn=turn,
            )

        validate_feature_cutoff((snapshot(8), snapshot(10)), prediction_cutoff_turn=10)
        with self.assertRaisesRegex(ProtocolValidationError, "feature-time leakage"):
            validate_feature_cutoff((snapshot(11),), prediction_cutoff_turn=10)

    def test_reproducibility_keys_are_required_and_hashed(self) -> None:
        with self.assertRaisesRegex(ProtocolValidationError, "model_revision"):
            self._trajectory(model_revision="")
        with self.assertRaisesRegex(ProtocolValidationError, "generation_config_sha256"):
            self._trajectory(generation_config_sha256="not-a-hash")

    def test_all_turn_layer_component_coverage_is_fail_fast(self) -> None:
        snapshots = []
        for turn in range(1, 26):
            for layer in range(2):
                for component in ActivationComponent:
                    snapshots.append(
                        ActivationSnapshotMetadata(
                            trajectory_id="traj-0001",
                            main_turn=turn,
                            layer_index=layer,
                            component=component,
                            hidden_size=8,
                            vector_shape=(8,),
                            storage_dtype=NumericDType.BFLOAT16,
                            compute_dtype=NumericDType.BFLOAT16,
                            vector_uri=f"a/{turn}/{layer}/{component.value}.pt",
                            vector_sha256="a" * 64,
                            prompt_sha256="b" * 64,
                            token_index=123,
                            hook_contract_version="hooks-v1",
                            available_at_turn=turn,
                        )
                    )
        validate_activation_coverage(
            tuple(snapshots), trajectory_id="traj-0001", layer_count=2
        )
        with self.assertRaisesRegex(ProtocolValidationError, "incomplete all-layer"):
            validate_activation_coverage(
                tuple(snapshots[:-1]), trajectory_id="traj-0001", layer_count=2
            )

    def test_drift_requires_onset_and_behavior_blinding(self) -> None:
        with self.assertRaisesRegex(ProtocolValidationError, "onset_main_turn"):
            DriftOutcomeMetadata(
                trajectory_id="traj-0001",
                outcome=DriftOutcome.DRIFT,
                label_protocol_version="judge-v1",
            )
        with self.assertRaisesRegex(ProtocolValidationError, "without exposing"):
            DriftOutcomeMetadata(
                trajectory_id="traj-0001",
                outcome=DriftOutcome.NO_DRIFT_THROUGH_OBSERVATION_END,
                label_protocol_version="judge-v1",
                judged_without_activations=False,
            )

    def test_no_event_is_behavior_stable_through_end_and_survival_censored(self) -> None:
        no_event = DriftOutcomeMetadata(
            trajectory_id="traj-0001",
            outcome=DriftOutcome.NO_DRIFT_THROUGH_OBSERVATION_END,
            label_protocol_version="judge-v1",
        )
        self.assertFalse(no_event.event_observed)
        self.assertTrue(no_event.behavior_stable_through_observation_end)
        self.assertEqual(no_event.censor_turn, 25)
        self.assertEqual(no_event.event_or_censor_turn, 25)

        event = DriftOutcomeMetadata(
            trajectory_id="traj-0002",
            outcome=DriftOutcome.DRIFT,
            label_protocol_version="judge-v1",
            onset_main_turn=17,
        )
        self.assertTrue(event.event_observed)
        self.assertFalse(event.behavior_stable_through_observation_end)
        self.assertIsNone(event.censor_turn)
        self.assertEqual(event.event_or_censor_turn, 17)

    def test_event_and_censor_times_are_consistent(self) -> None:
        with self.assertRaisesRegex(ProtocolValidationError, "later than observation_end"):
            DriftOutcomeMetadata(
                trajectory_id="traj-0001",
                outcome=DriftOutcome.DRIFT,
                label_protocol_version="judge-v1",
                onset_main_turn=21,
                observation_end_main_turn=20,
            )
        with self.assertRaisesRegex(ProtocolValidationError, "cannot carry a drift onset"):
            DriftOutcomeMetadata(
                trajectory_id="traj-0001",
                outcome=DriftOutcome.NO_DRIFT_THROUGH_OBSERVATION_END,
                label_protocol_version="judge-v1",
                onset_main_turn=20,
            )
        with self.assertRaisesRegex(ProtocolValidationError, "must be an integer"):
            DriftOutcomeMetadata(
                trajectory_id="traj-0001",
                outcome=DriftOutcome.NO_DRIFT_THROUGH_OBSERVATION_END,
                label_protocol_version="judge-v1",
                observation_end_main_turn=True,
            )

    def test_fork_requires_eligible_prefix_and_rejects_l6(self) -> None:
        valid = {
            "fork_id": "fork-0001",
            "source_trajectory_id": "traj-0001",
            "prefix_turn": 10,
            "planned_future_levels": (2,) * 5,
            "dose_ppu": 3,
            "continuation_seed": 1,
            "randomization_id": "rand-block-01",
            "source_prefix_not_drifted": True,
        }
        record = ForkMetadata(**valid)
        self.assertEqual(record.intervened_future_levels, (5,) * 5)
        with self.assertRaisesRegex(ProtocolValidationError, "not-yet-drifted"):
            ForkMetadata(**{**valid, "source_prefix_not_drifted": False})
        with self.assertRaisesRegex(ProtocolValidationError, "outside L0--L5"):
            ForkMetadata(**{**valid, "planned_future_levels": (3,) * 5})
        with self.assertRaisesRegex(ProtocolValidationError, "must include assistant response"):
            ForkMetadata(
                **{**valid, "prefix_includes_assistant_response_at_t": False}
            )
        with self.assertRaisesRegex(ProtocolValidationError, "t_plus_post_response"):
            ForkMetadata(**{**valid, "prefix_boundary": "t_minus_pre_response"})


if __name__ == "__main__":
    unittest.main()
