#!/bin/bash
set -euo pipefail

PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"
ROOT="outputs/cross_model_replication/olmo_qc_v1"
MANIFEST="docs/cross_model_replication_olmo_qc_v1_protocol_files.sha256"

if [[ -e "$ROOT" ]]; then
  echo "Refusing to reuse formal OLMo QC root: $ROOT" >&2
  exit 2
fi
if ! qstat -Bf >/dev/null 2>&1; then
  echo "PBS server is unavailable." >&2
  exit 4
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Refusing to submit with uncommitted tracked changes." >&2
  exit 2
fi
sha256sum -c "$MANIFEST"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate persona-drift
PYTHONPATH=src:. python scripts/validate_cross_model_replication.py \
  --config configs/cross_model_replication_olmo_qc_v1.yaml
PYTHONPATH=src:. python scripts/validate_olmo_qc_formal_replication.py \
  --config configs/cross_model_replication_olmo_qc_v1.yaml

mkdir -p "$ROOT"
cp "$MANIFEST" "$ROOT/protocol_files.sha256"
VALIDATE_JOB="$(qsub jobs/cross_model_validate_olmo_qc_v1.pbs)"
declare -a GENERATION_JOBS=()
declare -a GENERATION_LABELS=()
for axis in cautious_risk_seeking independent_sycophantic; do
  for topic in municipal_water_reuse coastal_ferry_ticketing regional_food_cold_chain; do
    axis_short=cau
    if [[ "$axis" == independent_sycophantic ]]; then axis_short=ind; fi
    case "$topic" in
      municipal_water_reuse) topic_short=wat ;;
      coastal_ferry_ticketing) topic_short=fer ;;
      regional_food_cold_chain) topic_short=foo ;;
      *) echo "Unexpected frozen topic: $topic" >&2; exit 2 ;;
    esac
    job_id="$(qsub -N "oqc-${axis_short}-${topic_short}" \
      -v "AXIS=$axis,TOPIC=$topic" \
      -W "depend=afterok:${VALIDATE_JOB}" \
      jobs/cross_model_generate_olmo_qc_v1.pbs)"
    GENERATION_JOBS+=("$job_id")
    GENERATION_LABELS+=("${axis}/${topic}")
  done
done
GENERATION_DEPENDENCY="$(IFS=:; echo "${GENERATION_JOBS[*]}")"
MERGE_JOB="$(qsub -W "depend=afterok:${GENERATION_DEPENDENCY}" jobs/cross_model_merge_olmo_qc_v1.pbs)"
DISPATCHER_JOB="$(qsub -W "depend=afterok:${MERGE_JOB}" jobs/cross_model_submit_downstream_olmo_qc_v1.pbs)"
{
  printf 'validate=%s\n' "$VALIDATE_JOB"
  for index in "${!GENERATION_JOBS[@]}"; do
    printf 'generate[%s]=%s\n' "${GENERATION_LABELS[$index]}" "${GENERATION_JOBS[$index]}"
  done
  printf 'merge_and_generation_qc=%s\n' "$MERGE_JOB"
  printf 'downstream_dispatcher=%s\n' "$DISPATCHER_JOB"
} | tee "$ROOT/formal_job_ids.txt"
