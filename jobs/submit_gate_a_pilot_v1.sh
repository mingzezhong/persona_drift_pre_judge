#!/bin/bash
set -euo pipefail

PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"

if [[ -e outputs/gate_a/pilot_v1 ]]; then
  echo "Refusing to submit: outputs/gate_a/pilot_v1 already exists." >&2
  exit 1
fi
mkdir -p logs

INDEPENDENT_JOB="$(qsub jobs/gate_a_pilot_independent_v1.pbs)"
CAUTIOUS_JOB="$(qsub jobs/gate_a_pilot_cautious_v1.pbs)"
MERGE_JOB="$(qsub -W depend=afterok:${INDEPENDENT_JOB}:${CAUTIOUS_JOB} jobs/gate_a_pilot_merge_v1.pbs)"
JUDGE_A_JOB="$(qsub -W depend=afterok:${MERGE_JOB} jobs/gate_a_pilot_judge_a_v1.pbs)"
JUDGE_B_JOB="$(qsub -W depend=afterok:${MERGE_JOB} jobs/gate_a_pilot_judge_b_v1.pbs)"
ANALYZE_JOB="$(qsub -W depend=afterok:${JUDGE_A_JOB}:${JUDGE_B_JOB} jobs/gate_a_pilot_analyze_v1.pbs)"

JOB_RECORD="logs/gate_a_pilot_v1_jobs_$(date +%Y%m%d_%H%M%S).txt"
{
  printf 'independent=%s\n' "$INDEPENDENT_JOB"
  printf 'cautious=%s\n' "$CAUTIOUS_JOB"
  printf 'merge=%s\n' "$MERGE_JOB"
  printf 'judge_a=%s\n' "$JUDGE_A_JOB"
  printf 'judge_b=%s\n' "$JUDGE_B_JOB"
  printf 'analyze=%s\n' "$ANALYZE_JOB"
} | tee "$JOB_RECORD"
printf 'record=%s\n' "$JOB_RECORD"
