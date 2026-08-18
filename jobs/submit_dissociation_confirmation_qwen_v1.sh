#!/bin/bash
# Submit the frozen Qwen dissociation-confirmation pipeline.

set -euo pipefail
PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"
ROOT="outputs/gate_c/dissociation_confirmation/qwen_v1"

if [[ -e "$ROOT" ]]; then
  echo "Refusing to reuse confirmation output root: $ROOT" >&2
  exit 2
fi

if ! qstat -Bf >/dev/null 2>&1; then
  echo "PBS server is unavailable; refusing to create a partial submission." >&2
  exit 4
fi

FILES=(
  configs/dissociation_confirmation_qwen_v1.yaml
  configs/ai_judges_dissociation_confirmation_qwen_v1.yaml
  configs/dissociation_forecast_qwen_v1.yaml
  data/templates/persona_gate_c_dissociation_confirmation_v1.yaml
  docs/gate_c_dissociation_confirmation_v1_preregistration.md
  docs/gate_c_dissociation_confirmation_v1_power.json
  outputs/gate_c/frozen_predictors/dissociation_v1/predictor.joblib
  outputs/gate_c/frozen_predictors/dissociation_v1/summary.json
  outputs/gate_a/pilot_v1/analysis/summary.json
  scripts/analyze_dissociation_confirmation.py
  scripts/analyze_gate_a.py
  scripts/freeze_dissociation_predictor.py
  scripts/power_dissociation_confirmation.py
  tests/test_dissociation_confirmation.py
  tests/test_dissociation_confirmation_design.py
  tests/test_gate_a_fixed_threshold.py
  jobs/dissociation_validate_qwen_v1.pbs
  jobs/dissociation_generate_independent_qwen_v1.pbs
  jobs/dissociation_generate_cautious_qwen_v1.pbs
  jobs/dissociation_merge_qwen_v1.pbs
  jobs/dissociation_judge_a_qwen_v1.pbs
  jobs/dissociation_judge_b_qwen_v1.pbs
  jobs/dissociation_output_analysis_qwen_v1.pbs
  jobs/dissociation_forecast_analysis_qwen_v1.pbs
  jobs/wait_for_pbs_and_submit_dissociation_qwen_v1.sh
)
for file in "${FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing preregistered file: $file" >&2
    exit 2
  fi
done

mkdir -p "$ROOT" logs
sha256sum "${FILES[@]}" > "$ROOT/preregistered_files.sha256"

VALIDATE_JOB="$(qsub jobs/dissociation_validate_qwen_v1.pbs)"
INDEPENDENT_JOB="$(qsub -W depend=afterok:${VALIDATE_JOB} jobs/dissociation_generate_independent_qwen_v1.pbs)"
CAUTIOUS_JOB="$(qsub -W depend=afterok:${VALIDATE_JOB} jobs/dissociation_generate_cautious_qwen_v1.pbs)"
MERGE_JOB="$(qsub -W depend=afterok:${INDEPENDENT_JOB}:${CAUTIOUS_JOB} jobs/dissociation_merge_qwen_v1.pbs)"
JUDGE_A_JOB="$(qsub -W depend=afterok:${MERGE_JOB} jobs/dissociation_judge_a_qwen_v1.pbs)"
JUDGE_B_JOB="$(qsub -W depend=afterok:${MERGE_JOB} jobs/dissociation_judge_b_qwen_v1.pbs)"
OUTPUT_JOB="$(qsub -W depend=afterok:${JUDGE_A_JOB}:${JUDGE_B_JOB} jobs/dissociation_output_analysis_qwen_v1.pbs)"
FORECAST_JOB="$(qsub -W depend=afterok:${OUTPUT_JOB} jobs/dissociation_forecast_analysis_qwen_v1.pbs)"

{
  printf 'validate=%s\n' "$VALIDATE_JOB"
  printf 'independent=%s\n' "$INDEPENDENT_JOB"
  printf 'cautious=%s\n' "$CAUTIOUS_JOB"
  printf 'merge=%s\n' "$MERGE_JOB"
  printf 'judge_a=%s\n' "$JUDGE_A_JOB"
  printf 'judge_b=%s\n' "$JUDGE_B_JOB"
  printf 'output_analysis=%s\n' "$OUTPUT_JOB"
  printf 'forecast_analysis=%s\n' "$FORECAST_JOB"
} | tee "$ROOT/job_ids.txt"

