from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from persona_drift.g1_local_reviewer import (
    AppendOnlyLedger,
    Registry,
    ReviewRunnerError,
    assigned_items,
    canonical_json_bytes,
    prepare_review,
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
            "candidate_anonymous_id": payload["candidate_anonymous_id"],
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
        self._provenance = {
            "backend": "unit-test-fake",
            "network_used": False,
            "model_loaded": False,
        }

    @property
    def provenance(self):
        return self._provenance

    def generate(self, messages, decoder):
        self.calls += 1
        if not messages or decoder.max_new_tokens < 1:
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

    def test_accepts_exactly_one_complete_json_or_bare_fence(self) -> None:
        for opener in ("```json", "```"):
            parsed = self.task.parse_output(
                f"{opener}\n{self.valid}\n```", self.item
            )
            self.assertEqual(
                parsed["blind_item_id"], self.item.input_value["blind_item_id"]
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

    def test_fenced_output_is_accepted_but_raw_and_normalization_are_audited(self) -> None:
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
            self.assertEqual(summary.accepted, 1)
            self.assertEqual(record["raw_output"], fenced)
            self.assertEqual(
                record["normalization"],
                "strip_single_outer_markdown_json_fence",
            )
            self.assertEqual(
                record["normalized_output_sha256"],
                hashlib.sha256(bare.encode()).hexdigest(),
            )

    def test_invalid_attempt_is_retained_then_valid_retry_is_chained(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "ratings.jsonl"
            invalid = run_review(
                self.prepared,
                output_path=output,
                backend=QueueBackend(["not JSON"]),
                clock=lambda: FIXED_TIME,
                attempt_id_factory=lambda: "ATT-invalid",
            )
            prefix = output.read_bytes()
            self.assertEqual(invalid.rejected_invalid_output, 1)

            accepted = run_review(
                self.prepared,
                output_path=output,
                backend=QueueBackend([response_for(self.item)]),
                clock=lambda: FIXED_TIME,
                attempt_id_factory=lambda: "ATT-valid",
            )
            combined = output.read_bytes()
            self.assertTrue(combined.startswith(prefix))
            self.assertEqual(accepted.accepted, 1)
            records = [
                json.loads(line)
                for line in combined.decode().splitlines()
            ]
            self.assertEqual(
                [record["status"] for record in records],
                ["rejected_invalid_output", "accepted"],
            )
            self.assertEqual(
                records[1]["previous_record_sha256"],
                records[0]["record_sha256"],
            )
            with AppendOnlyLedger(output) as ledger:
                self.assertEqual(len(ledger.records), 2)

    def test_generation_failure_is_appended_before_runner_stops(self) -> None:
        class BrokenBackend(QueueBackend):
            def generate(self, messages, decoder):
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
