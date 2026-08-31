from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml

from persona_drift.g1_local_reviewer import (
    AppendOnlyLedger,
    Registry,
    ReviewRunnerError,
    LocalHuggingFaceBackend,
    _build_tokenizer_constraint_data,
    _load_schema_enforcer,
    _tokenizer_load_options,
    assigned_items,
    effective_response_schema,
    canonical_json_bytes,
    prepare_review,
    normalize_model_output,
    review_contract,
    review_plan,
    runner_implementation_binding,
    run_review,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = PROJECT_ROOT / "configs/g1_reviewer_registry_v2_3.yaml"
PROMPTS = (
    PROJECT_ROOT / "data/rater_specs/g1_local_reviewer_prompts_v2_3.yaml"
)
SMOKE = PROJECT_ROOT / "data/synthetic/g1_reviewer_smoke_v2_3.jsonl"
FIXED_TIME = datetime(2026, 8, 28, 0, 0, tzinfo=timezone.utc)


class TokenizerLoadOptionsTests(unittest.TestCase):
    def test_mistral_enables_upstream_regex_fix(self) -> None:
        self.assertEqual(
            _tokenizer_load_options("mistral"),
            {
                "local_files_only": True,
                "trust_remote_code": False,
                "fix_mistral_regex": True,
            },
        )

    def test_other_families_do_not_receive_mistral_only_option(self) -> None:
        self.assertEqual(
            _tokenizer_load_options("olmo2"),
            {"local_files_only": True, "trust_remote_code": False},
        )


def prepared_for(slot: str, *tasks: str):
    return prepare_review(
        registry_path=REGISTRY,
        reviewer_slot_id=slot,
        prompts_path=PROMPTS,
        packet_path=SMOKE,
        selected_tasks=tasks,
    )


def response_for(item) -> str:
    payload = item.input_value
    if item.task_id == "persona_scalar":
        value = {
            "definition": "Prefers preserving reversible options.",
            "scores": {
                "construct_consistency": 2,
                "behavioral_observability": 2,
                "pressure_opposability": 2,
                "distinctness": 2,
                "safety_hhh_confound_separation": 2,
                "subject_frame_transfer": 2,
                "item_quality_diversity": 2,
            },
            "rationale": "The paired statements support one observable construct.",
        }
    elif item.task_id == "persona_pair":
        value = {
            "candidate_a_id": payload["candidate_a"]["id"],
            "candidate_b_id": payload["candidate_b"]["id"],
            "relation_label": "opposite_poles_of_one_axis",
            "rationale": "The candidates prefer opposite commitment policies.",
        }
    elif item.task_id == "persona_family":
        value = {
            "candidate_id": payload["candidate_id"],
            "family_id": payload["family_options"][0],
            "rationale": "The definition concerns decisions under uncertainty.",
        }
    elif item.task_id == "topic_triage":
        value = {
            "blind_item_id": payload["blind_item_id"],
            "rating": "advance",
            "rationale": "The item has a stable keyed reference.",
        }
    elif item.task_id == "topic_suitability":
        value = {
            "blind_item_id": payload["blind_item_id"],
            "scores": {
                "twenty_five_turn_extensibility": 2,
                "persona_expression_opportunity": 2,
                "pressure_compatibility": 2,
                "stable_reference_or_stance": 2,
                "safety_confound_separation": 2,
            },
            "rationale": "The decision can be extended while preserving a stable frame.",
        }
    elif item.task_id == "scenario_writer":
        value = {
            "blind_item_id": payload["blind_item_id"],
            "scenario_summary": "Review the conservation evidence in stages.",
            "moves": [
                {
                    "move_index": index,
                    "move_text": f"Discuss evidence component {index}.",
                }
                for index in range(1, 26)
            ],
        }
    elif item.task_id == "scenario_qa":
        value = {
            "blind_item_id": payload["blind_item_id"],
            "checks": {
                "topical_coherence": "pass",
                "nonredundancy": "pass",
                "pressure_absence": "pass",
                "persona_neutrality": "pass",
                "safety_confound_separation": "pass",
            },
            "rationale": "The supplied moves satisfy every listed check.",
        }
    else:
        raise AssertionError(item.task_id)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class QueueBackend:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0
        self.schemas = []
        self._provenance = {
            "backend": "unit-test-fake",
            "network_used": False,
            "model_loaded": False,
        }

    @property
    def provenance(self):
        return self._provenance

    def generate(self, messages, decoder, effective_schema):
        self.calls += 1
        self.schemas.append(effective_schema)
        if not messages or decoder.max_new_tokens < 1 or not effective_schema:
            raise AssertionError("runner supplied an invalid generation request")
        return self.outputs.pop(0)


class AssetAndAssignmentTests(unittest.TestCase):
    def test_tracked_assets_prepare_without_importing_transformers(self) -> None:
        before = set(sys.modules)
        primary = prepared_for("primary_01")
        adjudicator = prepared_for("adjudicator_04")
        writer = prepared_for("scenario_writer")
        self.assertEqual(
            {item.task_id for item in assigned_items(primary)},
            {
                "persona_scalar",
                "persona_pair",
                "persona_family",
                "topic_triage",
                "topic_suitability",
                "scenario_qa",
            },
        )
        self.assertEqual(
            {item.task_id for item in assigned_items(adjudicator)},
            {
                "persona_scalar",
                "persona_pair",
                "persona_family",
                "topic_suitability",
            },
        )
        self.assertEqual(
            [item.task_id for item in assigned_items(writer)],
            ["scenario_writer"],
        )
        self.assertNotIn("transformers", set(sys.modules) - before)
        self.assertNotIn("torch", set(sys.modules) - before)

    def test_dry_plan_binds_all_content_and_does_not_load_model(self) -> None:
        plan = review_plan(prepared_for("primary_02", "topic_triage"))
        self.assertEqual(plan["status"], "DRY_RUN")
        self.assertFalse(plan["model_loaded"])
        self.assertFalse(plan["network_allowed"])
        self.assertEqual(plan["assigned_task_counts"], {"topic_triage": 1})
        for key in (
            "registry_file_sha256",
            "registry_canonical_sha256",
            "prompt_catalog_file_sha256",
            "prompt_catalog_canonical_sha256",
            "packet_file_sha256",
            "review_contract_sha256",
        ):
            self.assertRegex(plan[key], r"^[0-9a-f]{64}$")

    def test_review_contract_binds_exact_runner_implementation_bytes(self) -> None:
        contract = review_contract(prepared_for("primary_02", "topic_triage"))
        implementation = contract["runner_implementation"]
        expected_paths = {
            "src/persona_drift/g1_local_reviewer.py",
            "scripts/run_g1_local_reviewer.py",
        }
        self.assertEqual(set(implementation["file_sha256s"]), expected_paths)
        for relative_path, observed in implementation["file_sha256s"].items():
            expected = hashlib.sha256(
                (PROJECT_ROOT / relative_path).read_bytes()
            ).hexdigest()
            self.assertEqual(observed, expected)
        expected_root = hashlib.sha256(
            canonical_json_bytes(implementation["file_sha256s"])
        ).hexdigest()
        self.assertEqual(implementation["canonical_sha256"], expected_root)

    def test_production_stays_locked_by_registry(self) -> None:
        with self.assertRaisesRegex(
            ReviewRunnerError, "frozen_for_production"
        ):
            prepare_review(
                registry_path=REGISTRY,
                reviewer_slot_id="primary_01",
                prompts_path=PROMPTS,
                packet_path=SMOKE,
                production=True,
                production_task="topic_triage",
            )

    def test_production_registry_authorizes_only_current_runner_bytes(self) -> None:
        source = yaml.safe_load(REGISTRY.read_bytes())
        source["registry_status"] = "frozen_for_production"
        source["production_review_authorized"] = True
        source["runner_implementation"] = runner_implementation_binding()
        with tempfile.TemporaryDirectory() as temporary:
            production_registry = Path(temporary) / "production.yaml"
            production_registry.write_text(
                yaml.safe_dump(source, sort_keys=False), encoding="utf-8"
            )
            loaded = Registry.load(
                production_registry,
                reviewer_slot_id="primary_01",
                production=True,
                batch_size=1,
            )
            self.assertEqual(
                dict(loaded.runner_implementation),
                runner_implementation_binding(),
            )

            mismatched = source["runner_implementation"]
            mismatched["file_sha256s"][
                "scripts/run_g1_local_reviewer.py"
            ] = "0" * 64
            mismatched["canonical_sha256"] = hashlib.sha256(
                canonical_json_bytes(mismatched["file_sha256s"])
            ).hexdigest()
            production_registry.write_text(
                yaml.safe_dump(source, sort_keys=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                ReviewRunnerError, "differs from current exact bytes"
            ):
                Registry.load(
                    production_registry,
                    reviewer_slot_id="primary_01",
                    production=True,
                    batch_size=1,
                )

    def test_role_filter_fails_if_explicit_task_is_not_assigned(self) -> None:
        prepared = prepared_for("primary_01", "scenario_writer")
        with self.assertRaisesRegex(ReviewRunnerError, "no assigned packet items"):
            assigned_items(prepared)


class StrictOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        prepared = prepared_for("primary_01", "topic_triage")
        cls.item = assigned_items(prepared)[0]
        cls.task = prepared.prompts.tasks["topic_triage"]
        cls.valid = response_for(cls.item)

    def test_accepts_one_exact_schema_conforming_object(self) -> None:
        parsed = self.task.parse_output(self.valid, self.item)
        self.assertEqual(parsed["blind_item_id"], self.item.input_value["blind_item_id"])

    def test_markdown_fences_are_rejected_without_repair(self) -> None:
        for opener in ("```json", "```"):
            with self.assertRaisesRegex(ReviewRunnerError, "no repair"):
                self.task.parse_output(
                    f"{opener}\n{self.valid}\n```", self.item
                )

    def test_rejects_prose_other_fences_duplicates_and_nonfinite_numbers(self) -> None:
        invalid = (
            "Result: " + self.valid,
            "```JSON\n" + self.valid + "\n```",
            "```python\n" + self.valid + "\n```",
            "````json\n" + self.valid + "\n````",
            "```json\n```json\n" + self.valid + "\n```\n```",
            "```json\n" + self.valid + "\n```\ntrailing prose",
            "prefix\n```json\n" + self.valid + "\n```",
            (
                '{"blind_item_id":"SYN-TOP-001","rating":"advance",'
                '"rating":"reject","rationale":"duplicate"}'
            ),
            (
                '{"blind_item_id":"SYN-TOP-001","rating":"advance",'
                '"rationale":NaN}'
            ),
        )
        for raw in invalid:
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(ReviewRunnerError):
                    self.task.parse_output(raw, self.item)

    def test_rejects_extra_fields_and_anonymous_id_mismatch(self) -> None:
        extra = json.loads(self.valid)
        extra["extra"] = True
        with self.assertRaisesRegex(ReviewRunnerError, "extra fields"):
            self.task.parse_output(json.dumps(extra), self.item)
        wrong = json.loads(self.valid)
        wrong["blind_item_id"] = "SYN-TOP-WRONG"
        with self.assertRaisesRegex(ReviewRunnerError, "differs"):
            self.task.parse_output(json.dumps(wrong), self.item)


class SchemaConstrainedGenerationTests(unittest.TestCase):
    def test_effective_schema_locks_dynamic_ids_family_options_and_scores(self) -> None:
        prepared = prepared_for("primary_01")
        items = {item.task_id: item for item in assigned_items(prepared)}

        scalar_task = prepared.prompts.tasks["persona_scalar"]
        frozen_scalar_schema = canonical_json_bytes(scalar_task.response_schema)
        scalar_schema = effective_response_schema(
            scalar_task, items["persona_scalar"]
        )
        self.assertNotIn("candidate_anonymous_id", scalar_schema["properties"])
        self.assertNotIn("candidate_anonymous_id", scalar_schema["required"])
        self.assertEqual(
            canonical_json_bytes(scalar_task.response_schema), frozen_scalar_schema
        )
        self.assertEqual(
            scalar_schema["properties"]["scores"]["properties"]
            ["construct_consistency"]["enum"],
            [0, 1, 2],
        )

    def test_scalar_repeat_aliases_produce_identical_model_visible_messages(self) -> None:
        prepared = prepared_for("primary_01", "persona_scalar")
        task = prepared.prompts.tasks["persona_scalar"]
        item = assigned_items(prepared)[0]
        first = {
            "candidate_anonymous_id": "PC-1111111111111111",
            "input_id": "PSI-11111111111111111111",
            "statements": item.input_value["statements"],
        }
        repeat = {
            "candidate_anonymous_id": "PC-2222222222222222",
            "input_id": "PSI-22222222222222222222",
            "statements": item.input_value["statements"],
        }
        first_messages = task.messages(
            system_prompt=prepared.prompts.system_prompt,
            input_value=first,
        )
        repeat_messages = task.messages(
            system_prompt=prepared.prompts.system_prompt,
            input_value=repeat,
        )
        self.assertEqual(first_messages, repeat_messages)
        serialized = canonical_json_bytes(first_messages)
        self.assertNotIn(b"PC-1111111111111111", serialized)
        self.assertNotIn(b"PSI-11111111111111111111", serialized)

    def test_scalar_schema_retains_score_and_rationale_constraints(self) -> None:
        prepared = prepared_for("primary_01")
        items = {item.task_id: item for item in assigned_items(prepared)}
        scalar_task = prepared.prompts.tasks["persona_scalar"]
        scalar_schema = effective_response_schema(
            scalar_task, items["persona_scalar"]
        )
        self.assertEqual(
            scalar_schema["properties"]["scores"]["properties"]
            ["construct_consistency"]["enum"],
            [0, 1, 2],
        )
        self.assertNotIn(
            "minimum",
            scalar_schema["properties"]["scores"]["properties"]
            ["construct_consistency"],
        )
        self.assertEqual(
            scalar_schema["properties"]["rationale"]["maxLength"], 1024
        )
        self.assertEqual(
            scalar_schema["required"], scalar_task.response_schema["required"]
        )
        self.assertIs(scalar_schema["additionalProperties"], False)

        family_task = prepared.prompts.tasks["persona_family"]
        family_item = items["persona_family"]
        family_schema = effective_response_schema(family_task, family_item)
        self.assertEqual(
            family_schema["properties"]["candidate_id"]["const"],
            family_item.input_value["candidate_id"],
        )
        self.assertEqual(
            family_schema["properties"]["family_id"]["enum"],
            family_item.input_value["family_options"],
        )

        triage_task = prepared.prompts.tasks["topic_triage"]
        triage_item = items["topic_triage"]
        triage_schema = effective_response_schema(triage_task, triage_item)
        self.assertEqual(
            triage_schema["properties"]["blind_item_id"]["const"],
            triage_item.input_value["blind_item_id"],
        )

    def test_string_integer_and_duplicate_key_remain_invalid(self) -> None:
        prepared = prepared_for("primary_01", "persona_scalar")
        item = assigned_items(prepared)[0]
        task = prepared.prompts.tasks[item.task_id]
        schema = effective_response_schema(task, item)
        value = json.loads(response_for(item))
        value["scores"]["construct_consistency"] = "2"
        with self.assertRaisesRegex(ReviewRunnerError, "type integer"):
            task.parse_normalized_output(
                normalize_model_output(json.dumps(value)), item, schema
            )
        duplicate = response_for(item).replace(
            '"rationale":', '"rationale":"duplicate","rationale":', 1
        )
        with self.assertRaisesRegex(ReviewRunnerError, "duplicate JSON key"):
            task.parse_normalized_output(
                normalize_model_output(duplicate), item, schema
            )

    def test_dependency_missing_or_wrong_version_fails_closed(self) -> None:
        runtime = yaml.safe_load(
            (
                PROJECT_ROOT
                / "configs/g1_reviewer_registry_amendment_6_v2_3.yaml"
            ).read_text()
        )["runtime"]
        with mock.patch(
            "persona_drift.g1_local_reviewer.importlib.metadata.version",
            side_effect=__import__("importlib.metadata").metadata.PackageNotFoundError,
        ):
            with self.assertRaisesRegex(ReviewRunnerError, "not installed"):
                _load_schema_enforcer(runtime)
        with mock.patch(
            "persona_drift.g1_local_reviewer.importlib.metadata.version",
            return_value="0.11.1",
        ):
            with self.assertRaisesRegex(ReviewRunnerError, "version mismatch"):
                _load_schema_enforcer(runtime)

    def test_constraint_initialization_failure_prevents_model_generate(self) -> None:
        class Tensor:
            shape = (1, 1)

            def to(self, _device):
                return self

        class Tokenizer:
            pad_token_id = 0
            eos_token_id = 1

            def apply_chat_template(self, *_args, **_kwargs):
                return "prompt"

            def __call__(self, *_args, **_kwargs):
                return {"input_ids": Tensor()}

        class Model:
            calls = 0

            def parameters(self):
                return iter([type("Parameter", (), {"device": "cpu"})()])

            def generate(self, **_kwargs):
                self.calls += 1
                raise AssertionError("model.generate must not run")

        model = Model()
        backend = LocalHuggingFaceBackend(
            model=model,
            tokenizer=Tokenizer(),
            torch_module=object(),
            provenance={},
            schema_parser_factory=lambda _schema: (_ for _ in ()).throw(
                RuntimeError("constraint boom")
            ),
            tokenizer_constraint_data=object(),
            prefix_allowed_tokens_factory=lambda *_args: None,
        )
        prepared = prepared_for("primary_01", "topic_triage")
        item = assigned_items(prepared)[0]
        with self.assertRaisesRegex(ReviewRunnerError, "constraint initialization"):
            backend.generate(
                prepared.prompts.tasks[item.task_id].messages(
                    system_prompt=prepared.prompts.system_prompt,
                    input_value=item.input_value,
                ),
                prepared.registry.decoder,
                effective_response_schema(prepared.prompts.tasks[item.task_id], item),
            )
        self.assertEqual(model.calls, 0)

    def test_constraint_decoder_preserves_exact_text_without_cleanup(self) -> None:
        class Tokenizer:
            calls = []

            def decode(self, token_ids, **kwargs):
                self.calls.append((token_ids, kwargs))
                return "exact  ,text\ufffd"

        class TokenizerData:
            decoder = None

        tokenizer = Tokenizer()
        tokenizer_data = _build_tokenizer_constraint_data(
            tokenizer,
            lambda observed: TokenizerData(),
        )
        self.assertEqual(tokenizer_data.decoder([1, 2]), "exact  ,text\ufffd")
        self.assertEqual(
            tokenizer.calls,
            [([1, 2], {"clean_up_tokenization_spaces": False})],
        )

    def test_multiple_items_cache_tokenizer_data_but_get_independent_state(self) -> None:
        class Tensor:
            shape = (1, 1)

            def to(self, _device):
                return self

        class Tokenizer:
            pad_token_id = 0
            eos_token_id = 1

            def apply_chat_template(self, *_args, **_kwargs):
                return "prompt"

            def __call__(self, *_args, **_kwargs):
                return {"input_ids": Tensor()}

            def decode(self, *_args, **_kwargs):
                return "{}"

        class Generated:
            def __getitem__(self, _key):
                return []

        class Model:
            def __init__(self):
                self.calls = 0
                self.kwargs = None

            def parameters(self):
                return iter([type("Parameter", (), {"device": "cpu"})()])

            def generate(self, **kwargs):
                self.calls += 1
                self.kwargs = kwargs
                return Generated()

        class Torch:
            @staticmethod
            def inference_mode():
                return contextlib.nullcontext()

        captured = {"schemas": [], "tokenizer_data": [], "parsers": []}
        prefix_function = lambda *_args: [0]
        tokenizer_data_builds = []
        tokenizer_data = type("TokenizerData", (), {"decoder": None})()

        def tokenizer_data_factory(observed_tokenizer):
            tokenizer_data_builds.append(observed_tokenizer)
            return tokenizer_data

        def parser_factory(schema):
            parser = object()
            captured["schemas"].append(schema)
            captured["parsers"].append(parser)
            return parser

        def prefix_factory(observed_tokenizer_data, parser):
            captured["tokenizer_data"].append(observed_tokenizer_data)
            return prefix_function

        model = Model()
        tokenizer = Tokenizer()
        cached_tokenizer_data = _build_tokenizer_constraint_data(
            tokenizer, tokenizer_data_factory
        )
        backend = LocalHuggingFaceBackend(
            model=model,
            tokenizer=tokenizer,
            torch_module=Torch(),
            provenance={},
            schema_parser_factory=parser_factory,
            tokenizer_constraint_data=cached_tokenizer_data,
            prefix_allowed_tokens_factory=prefix_factory,
        )
        prepared = prepared_for("primary_01", "topic_triage", "persona_scalar")
        items = assigned_items(prepared)
        schemas = [
            effective_response_schema(prepared.prompts.tasks[item.task_id], item)
            for item in items
        ]
        for schema in schemas:
            backend.generate([], prepared.registry.decoder, schema)
        self.assertEqual(tokenizer_data_builds, [tokenizer])
        self.assertEqual(model.calls, len(items))
        self.assertEqual(captured["schemas"], schemas)
        self.assertEqual(len({id(parser) for parser in captured["parsers"]}), len(items))
        self.assertTrue(
            all(value is tokenizer_data for value in captured["tokenizer_data"])
        )
        self.assertIs(model.kwargs["prefix_allowed_tokens_fn"], prefix_function)

    def test_tokenizer_data_build_failure_stops_before_generate(self) -> None:
        class Model:
            calls = 0

            def generate(self, **_kwargs):
                self.calls += 1

        model = Model()
        with self.assertRaisesRegex(
            ReviewRunnerError, "tokenizer constraint data initialization failed"
        ):
            _build_tokenizer_constraint_data(
                object(),
                lambda _tokenizer: (_ for _ in ()).throw(
                    RuntimeError("trie build failed")
                ),
            )
        self.assertEqual(model.calls, 0)

    def test_old_production_registry_cannot_authorize_amended_runner(self) -> None:
        with self.assertRaisesRegex(
            ReviewRunnerError, "differs from current exact bytes"
        ):
            Registry.load(
                PROJECT_ROOT
                / "configs/g1_reviewer_registry_production_v2_3.yaml",
                reviewer_slot_id="primary_01",
                production=True,
                batch_size=1,
            )


class AppendOnlyExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prepared = prepared_for("primary_01", "topic_triage")
        self.item = assigned_items(self.prepared)[0]

    def test_accepts_appends_hashes_and_resume_never_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "ratings.jsonl"
            backend = QueueBackend([response_for(self.item)])
            summary = run_review(
                self.prepared,
                output_path=output,
                backend=backend,
                clock=lambda: FIXED_TIME,
                attempt_id_factory=lambda: "ATT-first",
            )
            first_bytes = output.read_bytes()
            first = json.loads(first_bytes)
            self.assertEqual(summary.accepted, 1)
            self.assertEqual(summary.attempted, 1)
            self.assertEqual(backend.calls, 1)
            self.assertEqual(first["status"], "accepted")
            self.assertEqual(
                first["effective_response_schema_canonical_sha256"],
                hashlib.sha256(
                    canonical_json_bytes(first["effective_response_schema"])
                ).hexdigest(),
            )
            self.assertEqual(first["normalization"], "none")
            self.assertEqual(
                first["normalized_output_sha256"], first["raw_output_sha256"]
            )
            self.assertIsNone(first["previous_record_sha256"])
            self.assertEqual(
                first["raw_output_sha256"],
                hashlib.sha256(response_for(self.item).encode()).hexdigest(),
            )
            body = dict(first)
            record_hash = body.pop("record_sha256")
            self.assertEqual(
                record_hash,
                hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
            )

            def forbidden_factory(_registry):
                raise AssertionError("resume loaded a model with no pending inputs")

            resumed = run_review(
                self.prepared,
                output_path=output,
                backend_factory=forbidden_factory,
                clock=lambda: FIXED_TIME,
            )
            self.assertEqual(resumed.skipped_accepted, 1)
            self.assertEqual(resumed.attempted, 0)
            self.assertEqual(output.read_bytes(), first_bytes)

    def test_fenced_output_is_rejected_without_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "ratings.jsonl"
            bare = response_for(self.item)
            fenced = f"```json\n{bare}\n```"
            summary = run_review(
                self.prepared,
                output_path=output,
                backend=QueueBackend([fenced]),
                clock=lambda: FIXED_TIME,
                attempt_id_factory=lambda: "ATT-fenced",
            )
            record = json.loads(output.read_text())
            self.assertEqual(summary.accepted, 0)
            self.assertEqual(summary.rejected_invalid_output, 1)
            self.assertEqual(record["raw_output"], fenced)
            self.assertIsNone(record["normalization"])
            self.assertIsNone(record["normalized_output_sha256"])
            self.assertIn("no repair", record["error"])

    def test_invalid_attempt_is_retained_and_same_contract_cannot_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "ratings.jsonl"
            invalid_backend = QueueBackend(["not JSON"])
            invalid = run_review(
                self.prepared,
                output_path=output,
                backend=invalid_backend,
                clock=lambda: FIXED_TIME,
                attempt_id_factory=lambda: "ATT-invalid",
            )
            prefix = output.read_bytes()
            self.assertEqual(invalid.rejected_invalid_output, 1)
            self.assertEqual(invalid_backend.calls, 1)
            self.assertEqual(len(invalid_backend.schemas), 1)

            def forbidden_factory(_registry):
                raise AssertionError("failed ledger must stop before model loading")

            with self.assertRaisesRegex(ReviewRunnerError, "cannot resume"):
                run_review(
                    self.prepared,
                    output_path=output,
                    backend_factory=forbidden_factory,
                    clock=lambda: FIXED_TIME,
                )
            self.assertEqual(output.read_bytes(), prefix)
            with AppendOnlyLedger(output) as ledger:
                self.assertEqual(len(ledger.records), 1)

    def test_generation_failure_is_appended_before_runner_stops(self) -> None:
        class BrokenBackend(QueueBackend):
            def generate(self, messages, decoder, effective_schema):
                raise RuntimeError("synthetic failure")

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "ratings.jsonl"
            with self.assertRaisesRegex(ReviewRunnerError, "attempt was appended"):
                run_review(
                    self.prepared,
                    output_path=output,
                    backend=BrokenBackend([]),
                    clock=lambda: FIXED_TIME,
                    attempt_id_factory=lambda: "ATT-error",
                )
            record = json.loads(output.read_text())
            self.assertEqual(record["status"], "generation_error")
            self.assertIn("synthetic failure", record["error"])
            prefix = output.read_bytes()

            def forbidden_factory(_registry):
                raise AssertionError("failed ledger must stop before model loading")

            with self.assertRaisesRegex(ReviewRunnerError, "cannot resume"):
                run_review(
                    self.prepared,
                    output_path=output,
                    backend_factory=forbidden_factory,
                    clock=lambda: FIXED_TIME,
                )
            self.assertEqual(output.read_bytes(), prefix)

    def test_existing_ledger_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "ratings.jsonl"
            run_review(
                self.prepared,
                output_path=output,
                backend=QueueBackend([response_for(self.item)]),
                clock=lambda: FIXED_TIME,
                attempt_id_factory=lambda: "ATT-first",
            )
            text = output.read_text()
            output.write_text(text.replace('"status":"accepted"', '"status":"altered"'))
            with self.assertRaisesRegex(ReviewRunnerError, "hash mismatch"):
                with AppendOnlyLedger(output):
                    pass


class CommandLineDryRunTests(unittest.TestCase):
    def test_cli_dry_run_does_not_create_output_or_import_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "must-not-exist.jsonl"
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts/run_g1_local_reviewer.py"),
                    "--smoke",
                    "--slot",
                    "scenario_writer",
                    "--output",
                    str(output),
                    "--dry-run",
                ],
                cwd=PROJECT_ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertFalse(result["model_loaded"])
            self.assertEqual(result["assigned_task_counts"], {"scenario_writer": 1})
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
