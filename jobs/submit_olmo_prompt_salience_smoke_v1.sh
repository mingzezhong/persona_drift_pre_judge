#!/bin/bash
set -euo pipefail

PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"
ROOT="outputs/cross_model_replication/olmo_prompt_salience_smoke_v1"
if [[ -e "$ROOT" ]]; then
  echo "Refusing to reuse prompt-salience smoke root: $ROOT" >&2
  exit 2
fi
if ! qstat -Bf >/dev/null 2>&1; then
  echo "PBS server is unavailable." >&2
  exit 4
fi
sha256sum -c docs/olmo_prompt_salience_smoke_v1_protocol_files.sha256
mkdir -p "$ROOT"
cp docs/olmo_prompt_salience_smoke_v1_protocol_files.sha256 \
  "$ROOT/protocol_files.sha256"

VALIDATE_JOB="$(qsub jobs/olmo_prompt_salience_smoke_v1_validate.pbs)"
CAUTIOUS_JOB="$(qsub -N olmo-ps-cau -v AXIS=cautious_risk_seeking -W "depend=afterok:${VALIDATE_JOB}" jobs/olmo_prompt_salience_smoke_v1_generate.pbs)"
INDEPENDENT_JOB="$(qsub -N olmo-ps-ind -v AXIS=independent_sycophantic -W "depend=afterok:${VALIDATE_JOB}" jobs/olmo_prompt_salience_smoke_v1_generate.pbs)"
MERGE_JOB="$(qsub -W "depend=afterok:${CAUTIOUS_JOB}:${INDEPENDENT_JOB}" jobs/olmo_prompt_salience_smoke_v1_merge.pbs)"
{
  printf 'validate=%s\n' "$VALIDATE_JOB"
  printf 'generate[cautious_risk_seeking]=%s\n' "$CAUTIOUS_JOB"
  printf 'generate[independent_sycophantic]=%s\n' "$INDEPENDENT_JOB"
  printf 'merge_and_select=%s\n' "$MERGE_JOB"
} | tee "$ROOT/job_ids.txt"
