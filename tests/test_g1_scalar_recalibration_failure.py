import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/reports/g1_persona_scalar_recalibration_1_failure_v2_3.json"


def test_recalibration_stops_when_cross_reviewer_alpha_fails():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["status"] == "FAIL_CLOSED_STOP_AND_AMEND"
    assert report["g1_passed"] is False
    assert report["blind_repeat"] == {
        "exact_rating_vector_match_count": 9,
        "minimum_exact_rating_vector_agreement": 0.85,
        "mismatches": [],
        "observed_exact_rating_vector_agreement": 1.0,
        "passed": True,
        "repeat_count": 9,
    }
    agreement = report["agreement_evaluation"]["krippendorff_alpha_ordinal"]
    assert agreement["statistic_id"] == "krippendorff_alpha_ordinal"
    assert agreement["overall_observed"] < agreement["overall_minimum"] == 0.67
    assert agreement["overall_passed"] is False
    assert agreement["each_dimension_minimum"] == 0.50
    assert agreement["each_dimension_passed"] is False
    assert all(value < 0.50 for value in agreement["per_dimension"].values())
    assert report["agreement_evaluation"]["implementation_cross_check"] == {
        "all_values_exact_match": True,
        "independent_package": "krippendorff",
        "package_version": "0.8.2",
    }
    assert report["protocol_actions"]["recalibration_cycles_completed"] == 1
    assert report["protocol_actions"]["maximum_recalibration_cycles"] == 1
    assert report["protocol_actions"]["pair_review_must_not_start"] is True
    assert report["pair_stage"] == {
        "active_packet_absent": True,
        "authorized": False,
        "review_executed": False,
    }
    assert not (ROOT / "data/stages/persona_pair_input_v2_3.jsonl").exists()
