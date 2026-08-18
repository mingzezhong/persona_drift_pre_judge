#!/bin/bash
# Freeze and submit execution-v2 partitioning of the OLMo replication.

set -euo pipefail
PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"
ROOT="outputs/cross_model_replication/olmo_v1"

if [[ ! -f "$ROOT/vectors/persona_vectors.pt" || ! -f "$ROOT/vectors/summary.json" ]]; then
  echo "Frozen OLMo vectors are not complete." >&2
  exit 2
fi
for path in "$ROOT/shards_v2" "$ROOT/trajectories.jsonl" "$ROOT/probes.jsonl" "$ROOT/generation_quality.json" "$ROOT/merge_summary.json" "$ROOT/review" "$ROOT/judges" "$ROOT/analysis" "$ROOT/execution_v2_protocol_files.sha256" "$ROOT/execution_v2_job_ids.txt"; do
  if [[ -e "$path" ]]; then
    echo "Refusing to reuse execution-v2 path: $path" >&2
    exit 2
  fi
done
if grep -q "PENDING_" configs/cross_model_replication_olmo_v1.yaml; then
  echo "Replication config still contains an unresolved hash placeholder." >&2
  exit 2
fi
if ! qstat -Bf >/dev/null 2>&1; then
  echo "PBS server is unavailable." >&2
  exit 4
fi

# Prove that the original frozen scientific protocol remains untouched.
sha256sum -c "$ROOT/replication_protocol_files.sha256"

FILES=(
  "$ROOT/replication_protocol_files.sha256"
  docs/cross_model_replication_olmo_v1_execution_amendment.md
  scripts/generate_partitioned_gate_a_trajectories.py
  scripts/merge_partitioned_gate_a_shards.py
  tests/test_cross_model_execution_v2.py
  jobs/cross_model_generate_partition_olmo_v2.pbs
  jobs/cross_model_merge_olmo_v2.pbs
  jobs/submit_cross_model_replication_olmo_v2.sh
)
for file in "${FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing execution-v2 frozen file: $file" >&2
    exit 2
  fi
done
sha256sum "${FILES[@]}" > "$ROOT/execution_v2_protocol_files.sha256"
sha256sum -c "$ROOT/execution_v2_protocol_files.sha256"

VALIDATE_JOB="$(qsub jobs/cross_model_validate_olmo_v1.pbs)"
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
    job_id="$(qsub -N "ol2-${axis_short}-${topic_short}" -v "AXIS=$axis,TOPIC=$topic" -W "depend=afterok:${VALIDATE_JOB}" jobs/cross_model_generate_partition_olmo_v2.pbs)"
    GENERATION_JOBS+=("$job_id")
    GENERATION_LABELS+=("${axis}/${topic}")
  done
done
GENERATION_DEPENDENCY="$(IFS=:; echo "${GENERATION_JOBS[*]}")"
MERGE_JOB="$(qsub -W "depend=afterok:${GENERATION_DEPENDENCY}" jobs/cross_model_merge_olmo_v2.pbs)"
JUDGE_A_JOB="$(qsub -W "depend=afterok:${MERGE_JOB}" jobs/cross_model_judge_a_olmo_v1.pbs)"
JUDGE_B_JOB="$(qsub -W "depend=afterok:${MERGE_JOB}" jobs/cross_model_judge_b_olmo_v1.pbs)"
JUDGE_C_JOB="$(qsub -W "depend=afterok:${MERGE_JOB}" jobs/cross_model_judge_c_olmo_v1.pbs)"
ANALYZE_JOB="$(qsub -W "depend=afterok:${JUDGE_A_JOB}:${JUDGE_B_JOB}:${JUDGE_C_JOB}" jobs/cross_model_analyze_olmo_v1.pbs)"
{
  printf 'validate=%s\n' "$VALIDATE_JOB"
  for index in "${!GENERATION_JOBS[@]}"; do
    printf 'generate[%s]=%s\n' "${GENERATION_LABELS[$index]}" "${GENERATION_JOBS[$index]}"
  done
  printf 'merge=%s\n' "$MERGE_JOB"
  printf 'judge_a=%s\n' "$JUDGE_A_JOB"
  printf 'judge_b=%s\n' "$JUDGE_B_JOB"
  printf 'judge_c=%s\n' "$JUDGE_C_JOB"
  printf 'analyze=%s\n' "$ANALYZE_JOB"
} | tee "$ROOT/execution_v2_job_ids.txt"
