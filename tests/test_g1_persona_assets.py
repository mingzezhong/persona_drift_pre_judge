from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from persona_drift.g1_personas import (
    CANDIDATE_POOL_FILENAME,
    DUPLICATE_ITEM_STATUS,
    G1_OPEN_STATUS,
    G1PersonaAssetError,
    NORMALIZATION_RULE_ID,
    PUBLIC_SOURCES_FILENAME,
    SAMPLING_FRAME_FILENAME,
    SOURCE_COMMIT,
    TRAIT_CANDIDATES,
    TraitCandidateSpec,
    UNIQUE_ITEM_STATUS,
    audit_candidate_duplicates,
    git_blob_sha1,
    normalize_statement,
    read_candidate_file,
    sha256_bytes,
    stable_item_id,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = PROJECT_ROOT / "data/manifests"
REPORT_DIR = PROJECT_ROOT / "data/reports"


def source_record(statement: str, *, matching: str = " Yes") -> dict:
    not_matching = " No" if matching == " Yes" else " Yes"
    return {
        "question": (
            'Is the following statement something you would say?\n"'
            + statement
            + '"'
        ),
        "statement": statement,
        "label_confidence": 0.91,
        "answer_matching_behavior": matching,
        "answer_not_matching_behavior": not_matching,
    }


def write_trait(root: Path, slug: str, records: list[dict]) -> TraitCandidateSpec:
    path = root / "persona" / f"{slug}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"\n".join(
        json.dumps(record, ensure_ascii=False).encode("utf-8")
        for record in records
    ) + b"\n"
    path.write_bytes(raw)
    return TraitCandidateSpec(
        slug=slug,
        candidate_family_id=f"family-{slug}",
        source_subject_type="person",
        git_blob_sha1=git_blob_sha1(raw),
        file_sha256=sha256_bytes(raw),
        expected_rows=len(records),
    )


def all_mapping_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from all_mapping_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from all_mapping_keys(nested)


class G1PersonaSourceUnitTests(unittest.TestCase):
    def test_normalization_and_stable_source_item_id_are_frozen(self) -> None:
        self.assertEqual(
            normalize_statement("  ＣＡＦÉ\t\nTest  "),
            "café test",
        )
        raw_hash = hashlib.sha256(b"locked raw line").hexdigest()
        self.assertEqual(
            stable_item_id(
                trait_slug="risk-averse",
                line_number=1,
                raw_line_sha256=raw_hash,
            ),
            (
                "anthropic-evals-84fcc677-persona-risk-averse-"
                f"l000001-{raw_hash[:12]}"
            ),
        )
        with self.assertRaisesRegex(G1PersonaAssetError, "positive integer"):
            stable_item_id(
                trait_slug="risk-averse",
                line_number=0,
                raw_line_sha256=raw_hash,
            )

    def test_real_byte_hashes_and_jsonl_schema_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = write_trait(
                root,
                "trait-a",
                [source_record("First"), source_record("Second", matching=" No")],
            )
            trait, items = read_candidate_file(root, spec)
            self.assertEqual(trait["source_row_count"], 2)
            self.assertEqual(len(items), 2)
            self.assertTrue(items[0]["stable_source_item_id"].startswith(
                "anthropic-evals-84fcc677-persona-trait-a-l000001-"
            ))

            path = root / spec.source_path
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaisesRegex(G1PersonaAssetError, "SHA256 mismatch"):
                read_candidate_file(root, spec)

    def test_cross_trait_nfkc_case_whitespace_duplicates_exclude_all_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = write_trait(
                root,
                "trait-a",
                [source_record("ＣＡＦÉ   Test"), source_record("unique A")],
            )
            second = write_trait(
                root,
                "trait-b",
                [source_record("café\ttest", matching=" No"), source_record("unique B")],
            )
            trait_a, _ = read_candidate_file(root, first)
            trait_b, _ = read_candidate_file(root, second)
            report = audit_candidate_duplicates([trait_a, trait_b])
            self.assertEqual(report["normalization_rule_id"], NORMALIZATION_RULE_ID)
            self.assertEqual(
                report["summary"]["cross_trait_normalized_duplicate_groups"], 1
            )
            self.assertEqual(
                report["summary"]["rows_in_cross_trait_normalized_duplicate_groups"],
                2,
            )
            self.assertEqual(report["summary"]["label_conflict_groups"], 1)
            statuses = Counter(
                item["g1_candidate_item_status"]
                for trait in (trait_a, trait_b)
                for item in trait["source_items"]
            )
            self.assertEqual(statuses[DUPLICATE_ITEM_STATUS], 2)
            self.assertEqual(statuses[UNIQUE_ITEM_STATUS], 2)

    def test_within_trait_duplicates_are_also_excluded_before_item_role_split(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = write_trait(
                root,
                "trait-a",
                [
                    source_record("Repeated statement"),
                    source_record(" repeated\tstatement "),
                    source_record("unique statement"),
                ],
            )
            trait, _ = read_candidate_file(root, spec)
            report = audit_candidate_duplicates([trait])
            summary = report["summary"]
            self.assertEqual(summary["normalized_duplicate_groups"], 1)
            self.assertEqual(summary["within_trait_normalized_duplicate_groups"], 1)
            self.assertEqual(
                summary["rows_in_within_trait_normalized_duplicate_groups"], 2
            )
            self.assertEqual(summary["retained_globally_unique_candidate_rows"], 1)
            statuses = Counter(
                item["g1_candidate_item_status"] for item in trait["source_items"]
            )
            self.assertEqual(statuses[DUPLICATE_ITEM_STATUS], 2)
            self.assertEqual(statuses[UNIQUE_ITEM_STATUS], 1)


class GeneratedG1PersonaAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.public_path = MANIFEST_DIR / PUBLIC_SOURCES_FILENAME
        cls.pool_path = MANIFEST_DIR / CANDIDATE_POOL_FILENAME
        cls.frame_path = MANIFEST_DIR / SAMPLING_FRAME_FILENAME
        cls.report_path = REPORT_DIR / "persona_dedup_v2_3.json"
        cls.public_bytes = cls.public_path.read_bytes()
        cls.pool_bytes = cls.pool_path.read_bytes()
        cls.frame_bytes = cls.frame_path.read_bytes()
        cls.report_bytes = cls.report_path.read_bytes()
        cls.public = yaml.safe_load(cls.public_bytes)
        cls.pool = yaml.safe_load(cls.pool_bytes)
        cls.frame = yaml.safe_load(cls.frame_bytes)
        cls.report = json.loads(cls.report_bytes)

    def test_source_snapshot_and_license_are_pinned_but_g1_remains_open(self) -> None:
        self.assertEqual(self.public["g1_gate_status"], G1_OPEN_STATUS)
        self.assertFalse(self.public["execution_authorized"])
        source = self.public["source"]
        self.assertEqual(source["repository_commit"], SOURCE_COMMIT)
        self.assertEqual(source["license"]["spdx_id"], "CC-BY-4.0")
        observed = source["observed_dataset"]
        self.assertEqual(observed["persona_jsonl_file_count"], 135)
        self.assertEqual(observed["persona_total_row_count"], 133_204)
        self.assertEqual(len(observed["persona_files"]), 135)
        self.assertTrue(
            any(
                discrepancy["id"] == "persona-count-133-vs-135"
                for discrepancy in source["documentation_discrepancies"]
            )
        )

    def test_candidate_pool_has_exact_real_24_by_1000_hash_only_items(self) -> None:
        self.assertEqual(self.pool["g1_gate_status"], G1_OPEN_STATUS)
        self.assertEqual(self.pool["pool_status"], "CANDIDATE_NOT_ADJUDICATED")
        self.assertFalse(self.pool["execution_authorized"])
        self.assertTrue(self.pool["selection_outcome_blind"])
        traits = self.pool["candidate_traits"]
        self.assertEqual(len(traits), 24)
        self.assertEqual(self.pool["candidate_source_item_count"], 24_000)
        self.assertEqual({item.slug for item in TRAIT_CANDIDATES}, {
            trait["source_trait_slug"] for trait in traits
        })
        item_ids = []
        for trait in traits:
            self.assertEqual(trait["source_row_count"], 1_000)
            self.assertRegex(trait["source_git_blob_sha1"], r"^[0-9a-f]{40}$")
            self.assertRegex(trait["source_file_sha256"], r"^[0-9a-f]{64}$")
            for item in trait["source_items"]:
                item_ids.append(item["stable_source_item_id"])
                self.assertRegex(item["raw_line_sha256"], r"^[0-9a-f]{64}$")
                self.assertIn(
                    item["g1_candidate_item_status"],
                    {UNIQUE_ITEM_STATUS, DUPLICATE_ITEM_STATUS},
                )
        self.assertEqual(len(item_ids), 24_000)
        self.assertEqual(len(set(item_ids)), 24_000)
        candidate_paths = {trait["source_path"] for trait in traits}
        self.assertNotIn("persona/high-discount-factor.jsonl", candidate_paths)
        self.assertNotIn("persona/low-discount-factor.jsonl", candidate_paths)

    def test_draft_frame_and_dedup_counts_are_not_pass_or_final_assignments(self) -> None:
        self.assertEqual(self.frame["g1_gate_status"], G1_OPEN_STATUS)
        self.assertEqual(self.frame["sampling_frame_status"], "DRAFT_NOT_FROZEN")
        self.assertFalse(self.frame["execution_authorized"])
        self.assertEqual(len(self.frame["families"]), 4)
        self.assertEqual(
            {family["candidate_trait_count"] for family in self.frame["families"]},
            {6},
        )
        summary = self.report["summary"]
        self.assertEqual(summary["raw_candidate_rows"], 24_000)
        self.assertEqual(summary["unique_normalized_statements"], 23_837)
        self.assertEqual(summary["normalized_duplicate_groups"], 152)
        self.assertEqual(summary["rows_in_normalized_duplicate_groups"], 315)
        self.assertEqual(summary["cross_trait_normalized_duplicate_groups"], 148)
        self.assertEqual(summary["rows_in_cross_trait_normalized_duplicate_groups"], 307)
        self.assertEqual(summary["within_trait_normalized_duplicate_groups"], 4)
        self.assertEqual(summary["rows_in_within_trait_normalized_duplicate_groups"], 8)
        self.assertEqual(summary["retained_globally_unique_candidate_rows"], 23_685)
        self.assertEqual(summary["label_conflict_groups"], 29)
        self.assertEqual(summary["rows_in_label_conflict_groups"], 62)

    def test_cross_manifest_hash_bindings_and_g1_only_schema(self) -> None:
        public_sha = hashlib.sha256(self.public_bytes).hexdigest()
        pool_sha = hashlib.sha256(self.pool_bytes).hexdigest()
        report_sha = hashlib.sha256(self.report_bytes).hexdigest()
        self.assertEqual(self.pool["public_sources_manifest_sha256"], public_sha)
        self.assertEqual(self.report["candidate_pool_manifest_sha256"], pool_sha)
        self.assertEqual(self.frame["public_sources_manifest_sha256"], public_sha)
        self.assertEqual(self.frame["candidate_pool_manifest_sha256"], pool_sha)
        self.assertEqual(self.frame["dedup_report_sha256"], report_sha)

        forbidden_schema_keys = {
            "persona_prompt_variants",
            "prompt_variants",
            "item_role",
            "item_roles",
            "persona_item_role",
            "held_out_family_id",
            "held_out_trait_ids",
        }
        for payload in (self.public, self.pool, self.frame, self.report):
            self.assertTrue(forbidden_schema_keys.isdisjoint(all_mapping_keys(payload)))

    def test_raw_source_directory_is_gitignored(self) -> None:
        ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/raw/", ignore.splitlines())


if __name__ == "__main__":
    unittest.main()
