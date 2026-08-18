#!/bin/bash
# Submit frozen anchored measurement-development pipeline.

set -euo pipefail
PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"
ROOT="outputs/measurement/development_v1"

if [[ ! -f "$ROOT/data/dataset_summary.json" ]]; then
  echo "Measurement dataset has not been built and validated." >&2
  exit 2
fi
if [[ -d "$ROOT/judges" || -d "$ROOT/analysis" ]]; then
  echo "Refusing to reuse existing judge or analysis outputs." >&2
  exit 2
fi
if ! qstat -Bf >/dev/null 2>&1; then
  echo "PBS server is unavailable." >&2
  exit 4
fi

FILES=(
  configs/persona_measurement_development_v1.yaml
  configs/ai_judges_measurement_development_v1.yaml
  configs/extraction_judge_rubric_v2.yaml
  docs/persona_measurement_development_v1_protocol.md
  src/persona_drift/judging.py
  src/persona_drift/measurement.py
  scripts/judge_extraction.py
  scripts/create_measurement_anchors.py
  scripts/create_measurement_dataset.py
  scripts/validate_measurement_dataset.py
  scripts/analyze_measurement_development.py
  tests/test_judging.py
  tests/test_measurement.py
  tests/test_measurement_development_design.py
  "$ROOT/data/anchors.jsonl"
  "$ROOT/data/anchor_summary.json"
  "$ROOT/data/combined_manifest.jsonl"
  "$ROOT/data/dataset_summary.json"
  "$ROOT/review/measurement_a.csv"
  "$ROOT/review/measurement_b.csv"
  "$ROOT/review/measurement_c.csv"
  jobs/measurement_validate_v1.pbs
  jobs/measurement_judge_a_v1.pbs
  jobs/measurement_judge_b_v1.pbs
  jobs/measurement_judge_c_v1.pbs
  jobs/measurement_analyze_v1.pbs
)
for file in "${FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing frozen measurement file: $file" >&2
    exit 2
  fi
done
sha256sum "${FILES[@]}" > "$ROOT/protocol_files.sha256"

VALIDATE_JOB="$(qsub jobs/measurement_validate_v1.pbs)"
JUDGE_A_JOB="$(qsub -W depend=afterok:${VALIDATE_JOB} jobs/measurement_judge_a_v1.pbs)"
JUDGE_B_JOB="$(qsub -W depend=afterok:${VALIDATE_JOB} jobs/measurement_judge_b_v1.pbs)"
JUDGE_C_JOB="$(qsub -W depend=afterok:${VALIDATE_JOB} jobs/measurement_judge_c_v1.pbs)"
ANALYZE_JOB="$(qsub -W depend=afterok:${JUDGE_A_JOB}:${JUDGE_B_JOB}:${JUDGE_C_JOB} jobs/measurement_analyze_v1.pbs)"
{
  printf 'validate=%s\n' "$VALIDATE_JOB"
  printf 'judge_a=%s\n' "$JUDGE_A_JOB"
  printf 'judge_b=%s\n' "$JUDGE_B_JOB"
  printf 'judge_c=%s\n' "$JUDGE_C_JOB"
  printf 'analyze=%s\n' "$ANALYZE_JOB"
} | tee "$ROOT/job_ids.txt"

