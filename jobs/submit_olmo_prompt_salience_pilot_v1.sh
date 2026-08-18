#!/bin/bash
set -euo pipefail

PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"
ROOT="outputs/cross_model_replication/olmo_prompt_salience_pilot_v1"
if [[ -e "$ROOT" ]]; then
  echo "Refusing to reuse prompt-salience pilot root: $ROOT" >&2
  exit 2
fi
if ! qstat -Bf >/dev/null 2>&1; then
  echo "PBS server is unavailable." >&2
  exit 4
fi
sha256sum -c docs/olmo_prompt_salience_pilot_v1_protocol_files.sha256
mkdir -p "$ROOT"
cp docs/olmo_prompt_salience_pilot_v1_protocol_files.sha256 \
  "$ROOT/protocol_files.sha256"

VALIDATE_JOB="$(qsub jobs/olmo_prompt_salience_pilot_v1_validate.pbs)"
declare -a GENERATION_JOBS=()
declare -a GENERATION_LABELS=()
for axis in cautious_risk_seeking independent_sycophantic; do
  for topic in municipal_water_reuse coastal_ferry_ticketing regional_food_cold_chain; do
    axis_short="cau"
    if [[ "$axis" == "independent_sycophantic" ]]; then
      axis_short="ind"
    fi
    case "$topic" in
      municipal_water_reuse) topic_short="wat" ;;
      coastal_ferry_ticketing) topic_short="fer" ;;
      regional_food_cold_chain) topic_short="foo" ;;
      *) echo "Unexpected frozen topic: $topic" >&2; exit 2 ;;
    esac
    job_id="$(qsub -N "psp-${axis_short}-${topic_short}" \
      -v "AXIS=$axis,TOPIC=$topic" \
      -W "depend=afterok:${VALIDATE_JOB}" \
      jobs/olmo_prompt_salience_pilot_v1_generate.pbs)"
    GENERATION_JOBS+=("$job_id")
    GENERATION_LABELS+=("${axis}/${topic}")
  done
done
GENERATION_DEPENDENCY="$(IFS=:; echo "${GENERATION_JOBS[*]}")"
MERGE_JOB="$(qsub -W "depend=afterok:${GENERATION_DEPENDENCY}" \
  jobs/olmo_prompt_salience_pilot_v1_merge.pbs)"
{
  printf 'validate=%s\n' "$VALIDATE_JOB"
  for index in "${!GENERATION_JOBS[@]}"; do
    printf 'generate[%s]=%s\n' \
      "${GENERATION_LABELS[$index]}" "${GENERATION_JOBS[$index]}"
  done
  printf 'merge_and_analyze=%s\n' "$MERGE_JOB"
} | tee "$ROOT/job_ids.txt"
