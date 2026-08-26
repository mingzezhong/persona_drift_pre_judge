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
    PredictorFitAccess,
    StudyPhase,
    TopicPartition,
    TrajectoryMetadata,
    create_manifest_validated_trajectory_metadata,
    validate_activation_coverage,
    validate_activation_prompt_binding,
    validate_feature_cutoff,
    validate_trajectory_topic_identity,
    validate_trajectory_persona_identity,
)
from persona_drift.splits import TopicScope
from test_personas_restart_v2 import digest, make_catalog, make_plan
from test_splits_restart_v2 import (
    FAMILIES,
    make_candidate_pools,
    make_catalog as make_topic_catalog,
    make_rubric,
    make_scenarios,
    make_split as make_topic_split,
    move_hashes,
)


class RecordTests(unittest.TestCase):
    def _trajectory_values(self, **overrides):
        schedule = canonical_gradual_schedule()
        scenario = make_scenarios()[0]
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
            "topic_id": "shared-0",
            "topic_scope": TopicScope.SHARED_CORE,
            "scenario_family_id": "shared-core",
            "eligible_behavioral_family_id": None,
            "scenario_subtype": "subtype-shared-0",
            "topic_catalog_manifest_sha256": "7" * 64,
            "topic_split_plan_manifest_sha256": "8" * 64,
            "scenario_version": scenario.scenario_version,
            "scenario_template_sha256": scenario.scenario_template_sha256,
            "scenario_manifest_sha256": scenario.manifest_sha256,
            "topic_content_root_sha256": scenario.topic_content_root_sha256,
            "topic_move_ids": scenario.ordered_topic_move_ids,
            "topic_move_sha256s": scenario.ordered_topic_move_sha256s,
            "pressure_slot_ids": scenario.pressure_slot_ids,
            "topic_split": TopicPartition.DEVELOPMENT,
            "predictor_fit_access": PredictorFitAccess.FIT,
            "seed": 0,
            "schedule_id": schedule.schedule_id,
            "pressure_levels": schedule.levels,
            "pressure_template_ids": tuple(f"template-{turn}" for turn in range(1, 26)),
            "turn_composition_version": "compose-v1",
            "composed_user_turn_sha256s": move_hashes("composed-user-turn"),
            "pre_response_full_prompt_sha256s": move_hashes(
                "pre-response-full-prompt"
            ),
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
        self.assertEqual(payload["topic_scope"], "shared_core")
        self.assertEqual(payload["predictor_fit_access"], "fit")
        self.assertEqual(payload["schema_version"], "restart-v2.3")
        self.assertEqual(len(payload["pressure_levels"]), 25)
        self.assertEqual(len(payload["composed_user_turn_sha256s"]), 25)
        self.assertEqual(len(payload["pre_response_full_prompt_sha256s"]), 25)

    def test_pilot_topic_must_be_development(self) -> None:
        with self.assertRaisesRegex(ProtocolValidationError, "pilot topics"):
            self._trajectory(
                phase=StudyPhase.PILOT,
                topic_split=TopicPartition.UNTOUCHED_TEST,
                predictor_fit_access=PredictorFitAccess.EVALUATION_ONLY,
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
        with self.assertRaisesRegex(ProtocolValidationError, "topic_catalog_manifest_sha256"):
            self._trajectory(topic_catalog_manifest_sha256="not-a-hash")
        with self.assertRaisesRegex(ProtocolValidationError, "turn_composition_version"):
            self._trajectory(turn_composition_version="")
        with self.assertRaisesRegex(ProtocolValidationError, "composed_user_turn"):
            self._trajectory(composed_user_turn_sha256s=("4" * 64,))
        with self.assertRaisesRegex(
            ProtocolValidationError, "pre_response_full_prompt"
        ):
            self._trajectory(pre_response_full_prompt_sha256s=("bad",) * 25)
        with self.assertRaisesRegex(ProtocolValidationError, "unique"):
            self._trajectory(composed_user_turn_sha256s=("4" * 64,) * 25)
        with self.assertRaisesRegex(ProtocolValidationError, "unique"):
            self._trajectory(
                pre_response_full_prompt_sha256s=("5" * 64,) * 25
            )
        with self.assertRaisesRegex(ProtocolValidationError, "content_root"):
            self._trajectory(topic_move_sha256s=move_hashes("wrong-topic"))
        with self.assertRaisesRegex(ProtocolValidationError, "unique"):
            self._trajectory(topic_move_sha256s=("a" * 64,) * 25)

    def test_outcome_bearing_pilot_excludes_persona_holdouts(self) -> None:
        self._trajectory(phase=StudyPhase.PILOT)
        with self.assertRaisesRegex(
            ProtocolValidationError, "seen-trait observed-wording"
        ):
            self._trajectory(
                phase=StudyPhase.PILOT,
                persona_generalization_role=(
                    PersonaGeneralizationRole.UNSEEN_BEHAVIORAL_FAMILY
                ),
                predictor_fit_access=PredictorFitAccess.EVALUATION_ONLY,
            )

    def test_dual_fit_access_excludes_all_persona_holdouts(self) -> None:
        unseen_family = self._trajectory(
            persona_generalization_role=(
                PersonaGeneralizationRole.UNSEEN_BEHAVIORAL_FAMILY
            ),
            predictor_fit_access=PredictorFitAccess.EVALUATION_ONLY,
        )
        self.assertEqual(unseen_family.topic_split, TopicPartition.DEVELOPMENT)
        with self.assertRaisesRegex(ProtocolValidationError, "require both"):
            self._trajectory(
                persona_generalization_role=(
                    PersonaGeneralizationRole.UNSEEN_BEHAVIORAL_FAMILY
                ),
                predictor_fit_access=PredictorFitAccess.FIT,
            )
        self._trajectory(
            topic_split=TopicPartition.CALIBRATION,
            predictor_fit_access=PredictorFitAccess.EVALUATION_ONLY,
        )
        with self.assertRaisesRegex(ProtocolValidationError, "require both"):
            self._trajectory(
                predictor_fit_access=PredictorFitAccess.EVALUATION_ONLY,
            )

    def test_family_specific_trajectory_requires_matching_persona_family(self) -> None:
        self._trajectory(
            topic_scope=TopicScope.FAMILY_SPECIFIC,
            eligible_behavioral_family_id="risk-family",
        )
        with self.assertRaisesRegex(ProtocolValidationError, "must match"):
            self._trajectory(
                topic_scope=TopicScope.FAMILY_SPECIFIC,
                eligible_behavioral_family_id="other-family",
            )

    def test_topic_manifest_validator_binds_hierarchy_split_and_access(self) -> None:
        catalog = make_topic_catalog()
        split = make_topic_split()
        record = self._trajectory(behavioral_family_id=FAMILIES[0])
        self.assertIs(
            validate_trajectory_topic_identity(
                record,
                topic_catalog=catalog,
                topic_split_plan=split,
                topic_scenario_manifests=make_scenarios(catalog),
                source_candidate_pool_manifests=make_candidate_pools(),
                suitability_rubric_manifest=make_rubric(),
                persona_catalog=make_catalog(),
                topic_catalog_manifest_sha256="7" * 64,
                ),
            record,
        )
        with self.assertRaisesRegex(ProtocolValidationError, "split manifest"):
            validate_trajectory_topic_identity(
                replace(record, topic_split_plan_manifest_sha256="0" * 64),
                topic_catalog=catalog,
                topic_split_plan=split,
                topic_scenario_manifests=make_scenarios(catalog),
                source_candidate_pool_manifests=make_candidate_pools(),
                suitability_rubric_manifest=make_rubric(),
                persona_catalog=make_catalog(),
                topic_catalog_manifest_sha256="7" * 64,
            )
        with self.assertRaisesRegex(ProtocolValidationError, "partition mismatch"):
            validate_trajectory_topic_identity(
                replace(
                    record,
                    topic_split=TopicPartition.CALIBRATION,
                    predictor_fit_access=PredictorFitAccess.EVALUATION_ONLY,
                ),
                topic_catalog=catalog,
                topic_split_plan=split,
                topic_scenario_manifests=make_scenarios(catalog),
                source_candidate_pool_manifests=make_candidate_pools(),
                suitability_rubric_manifest=make_rubric(),
                persona_catalog=make_catalog(),
                topic_catalog_manifest_sha256="7" * 64,
                )
        nonpilot = make_scenarios(catalog)[2]
        with self.assertRaisesRegex(ProtocolValidationError, "pilot subset"):
            validate_trajectory_topic_identity(
                replace(
                    record,
                    phase=StudyPhase.PILOT,
                    topic_id="shared-2",
                    scenario_subtype="subtype-shared-2",
                    scenario_manifest_sha256=nonpilot.manifest_sha256,
                    topic_content_root_sha256=nonpilot.topic_content_root_sha256,
                    topic_move_ids=nonpilot.ordered_topic_move_ids,
                    topic_move_sha256s=nonpilot.ordered_topic_move_sha256s,
                    pressure_slot_ids=nonpilot.pressure_slot_ids,
                ),
                topic_catalog=catalog,
                topic_split_plan=split,
                topic_scenario_manifests=make_scenarios(catalog),
                source_candidate_pool_manifests=make_candidate_pools(),
                suitability_rubric_manifest=make_rubric(),
                persona_catalog=make_catalog(),
                topic_catalog_manifest_sha256="7" * 64,
                )
        with self.assertRaisesRegex(ProtocolValidationError, "moves or pressure slots"):
            validate_trajectory_topic_identity(
                replace(
                    record,
                    topic_move_ids=("wrong-move",) + record.topic_move_ids[1:],
                ),
                topic_catalog=catalog,
                topic_split_plan=split,
                topic_scenario_manifests=make_scenarios(catalog),
                source_candidate_pool_manifests=make_candidate_pools(),
                suitability_rubric_manifest=make_rubric(),
                persona_catalog=make_catalog(),
                topic_catalog_manifest_sha256="7" * 64,
                )
        scenarios = list(make_scenarios(catalog))
        scenarios[20] = replace(
            scenarios[20],
            ordered_topic_move_sha256s=scenarios[0].ordered_topic_move_sha256s,
            topic_content_root_sha256=scenarios[0].topic_content_root_sha256,
        )
        with self.assertRaisesRegex(ProtocolValidationError, "globally unique"):
            validate_trajectory_topic_identity(
                record,
                topic_catalog=catalog,
                topic_split_plan=split,
                topic_scenario_manifests=scenarios,
                source_candidate_pool_manifests=make_candidate_pools(),
                suitability_rubric_manifest=make_rubric(),
                persona_catalog=make_catalog(),
                topic_catalog_manifest_sha256="7" * 64,
                )
        mismatched_catalog = list(catalog)
        mismatched_catalog[12] = replace(
            mismatched_catalog[12],
            eligible_behavioral_family_id="foreign-family",
        )
        with self.assertRaisesRegex(ProtocolValidationError, "unknown eligible families"):
            validate_trajectory_topic_identity(
                record,
                topic_catalog=mismatched_catalog,
                topic_split_plan=split,
                topic_scenario_manifests=make_scenarios(mismatched_catalog),
                source_candidate_pool_manifests=make_candidate_pools(),
                suitability_rubric_manifest=make_rubric(),
                persona_catalog=make_catalog(),
                topic_catalog_manifest_sha256="7" * 64,
                )

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
        values.pop("topic_catalog_manifest_sha256")
        values.pop("topic_split_plan_manifest_sha256")
        values.pop("scenario_manifest_sha256")
        values.pop("topic_content_root_sha256")
        record = create_manifest_validated_trajectory_metadata(
            persona_catalog=catalog,
            persona_generalization_plan=plan,
            persona_catalog_manifest_sha256="e" * 64,
            persona_generalization_plan_manifest_sha256="9" * 64,
            topic_catalog=make_topic_catalog(),
            topic_split_plan=make_topic_split(),
            topic_scenario_manifests=make_scenarios(),
            source_candidate_pool_manifests=make_candidate_pools(),
            suitability_rubric_manifest=make_rubric(),
            topic_catalog_manifest_sha256="7" * 64,
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
        self.assertEqual(
            record.topic_split_plan_manifest_sha256,
            make_topic_split().manifest_sha256,
        )
        invalid_values = self._trajectory_values(
            behavioral_family_id="family-0",
            persona_trait_id="trait-0-0",
            persona_prompt_variant_id="variant-0-0-observed",
            persona_prompt_sha256=digest("variant-0-0-observed"),
            topic_move_ids=("wrong-move",)
            + tuple(f"shared-0-move-{turn}" for turn in range(2, 26)),
        )
        for owned in (
            "persona_catalog_sha256",
            "persona_generalization_plan_sha256",
            "topic_catalog_manifest_sha256",
            "topic_split_plan_manifest_sha256",
            "scenario_manifest_sha256",
            "topic_content_root_sha256",
        ):
            invalid_values.pop(owned)
        with self.assertRaisesRegex(ProtocolValidationError, "moves or pressure slots"):
            create_manifest_validated_trajectory_metadata(
                persona_catalog=catalog,
                persona_generalization_plan=plan,
                persona_catalog_manifest_sha256="e" * 64,
                persona_generalization_plan_manifest_sha256="9" * 64,
                topic_catalog=make_topic_catalog(),
                topic_split_plan=make_topic_split(),
                topic_scenario_manifests=make_scenarios(),
                source_candidate_pool_manifests=make_candidate_pools(),
                suitability_rubric_manifest=make_rubric(),
                topic_catalog_manifest_sha256="7" * 64,
                **invalid_values,
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
                predictor_fit_access=PredictorFitAccess.EVALUATION_ONLY,
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

    def test_activation_snapshot_binds_to_exact_full_prompt(self) -> None:
        trajectory = self._trajectory()
        snapshot = ActivationSnapshotMetadata(
            trajectory_id=trajectory.trajectory_id,
            main_turn=10,
            layer_index=5,
            component=ActivationComponent.RESID_PRE,
            hidden_size=8,
            vector_shape=(8,),
            storage_dtype=NumericDType.BFLOAT16,
            compute_dtype=NumericDType.BFLOAT16,
            vector_uri="activations/turn-10.pt",
            vector_sha256="a" * 64,
            prompt_sha256=trajectory.pre_response_full_prompt_sha256s[9],
            token_index=123,
            hook_contract_version="hooks-v1",
            available_at_turn=10,
        )
        validate_activation_prompt_binding((snapshot,), trajectory)
        with self.assertRaisesRegex(ProtocolValidationError, "trajectory_id"):
            validate_activation_prompt_binding(
                (replace(snapshot, trajectory_id="other-trajectory"),), trajectory
            )
        with self.assertRaisesRegex(ProtocolValidationError, "full prompt"):
            validate_activation_prompt_binding(
                (replace(snapshot, prompt_sha256="0" * 64),), trajectory
            )

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
