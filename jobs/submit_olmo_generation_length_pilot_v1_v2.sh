#!/bin/bash
# Freeze and resubmit the token-only OLMo generation-length pilot.

set -euo pipefail
PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"
ROOT="outputs/cross_model_replication/olmo_length_pilot_v1"

for path in "$ROOT/cap256" "$ROOT/cap384" "$ROOT/summary.json" "$ROOT/execution_v2_protocol_files.sha256" "$ROOT/job_ids_v2.txt"; do
  if [[ -e "$path" ]]; then
    echo "Refusing to reuse length-pilot path: $path" >&2
    exit 2
  fi
done
if [[ -d outputs/cross_model_replication/olmo_v1/judges || -d outputs/cross_model_replication/olmo_v1/analysis ]]; then
  echo "Failed source run unexpectedly has outcome analysis." >&2
  exit 2
fi
if ! qstat -Bf >/dev/null 2>&1; then
  echo "PBS server is unavailable." >&2
  exit 4
fi

sha256sum -c outputs/cross_model_replication/olmo_v1/replication_protocol_files.sha256
sha256sum -c outputs/cross_model_replication/olmo_v1/execution_v2_protocol_files.sha256
sha256sum -c outputs/cross_model_replication/olmo_v1/execution_v2_downstream_protocol_files.sha256
sha256sum -c outputs/cross_model_replication/olmo_v1/execution_v3_downstream_protocol_files.sha256
sha256sum -c "$ROOT/protocol_files.sha256"

FILES=(
  "$ROOT/protocol_files.sha256"
  docs/olmo_generation_length_pilot_v1_validation_amendment.md
  jobs/olmo_generation_length_pilot_v1_validate_v2.pbs
  jobs/submit_olmo_generation_length_pilot_v1_v2.sh
)
for file in "${FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing frozen length-pilot file: $file" >&2
    exit 2
  fi
done
sha256sum "${FILES[@]}" > "$ROOT/execution_v2_protocol_files.sha256"
sha256sum -c "$ROOT/execution_v2_protocol_files.sha256"

VALIDATE_JOB="$(qsub jobs/olmo_generation_length_pilot_v1_validate_v2.pbs)"
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
    job_id="$(qsub -N "len-${axis_short}-${topic_short}" -v "AXIS=$axis,TOPIC=$topic" -W "depend=afterok:${VALIDATE_JOB}" jobs/olmo_generation_length_pilot_v1_generate.pbs)"
    GENERATION_JOBS+=("$job_id")
    GENERATION_LABELS+=("${axis}/${topic}")
  done
done
GENERATION_DEPENDENCY="$(IFS=:; echo "${GENERATION_JOBS[*]}")"
MERGE_JOB="$(qsub -W "depend=afterok:${GENERATION_DEPENDENCY}" jobs/olmo_generation_length_pilot_v1_merge.pbs)"
{
  printf 'validate=%s\n' "$VALIDATE_JOB"
  for index in "${!GENERATION_JOBS[@]}"; do
    printf 'generate[%s]=%s\n' "${GENERATION_LABELS[$index]}" "${GENERATION_JOBS[$index]}"
  done
  printf 'merge_and_select=%s\n' "$MERGE_JOB"
} | tee "$ROOT/job_ids_v2.txt"
