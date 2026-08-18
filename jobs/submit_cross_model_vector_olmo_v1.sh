#!/bin/bash
# Freeze and submit pre-outcome OLMo vector construction.

set -euo pipefail
PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"
ROOT="outputs/cross_model_replication/olmo_v1"

if [[ -e "$ROOT" ]]; then
  echo "Refusing to reuse cross-model output root: $ROOT" >&2
  exit 2
fi
if ! qstat -Bf >/dev/null 2>&1; then
  echo "PBS server is unavailable." >&2
  exit 4
fi

FILES=(
  configs/cross_model_vector_olmo_v1.yaml
  docs/cross_model_target_amendment_v1.md
  outputs/cross_model_replication/preflight/model_access/config.json
  outputs/extraction/quality_pilot_s0_v4/ai_review/reviewed_manifest.jsonl
  src/persona_drift/activation.py
  src/persona_drift/hardware.py
  src/persona_drift/modeling.py
  scripts/check_hardware.py
  scripts/reencode_persona_vectors.py
  tests/test_reencode_persona_vectors.py
  jobs/cross_model_vector_validate_olmo_v1.pbs
  jobs/cross_model_vector_olmo_v1.pbs
)
for file in "${FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing frozen vector-protocol file: $file" >&2
    exit 2
  fi
done
mkdir -p "$ROOT"
sha256sum "${FILES[@]}" > "$ROOT/vector_protocol_files.sha256"

VALIDATE_JOB="$(qsub jobs/cross_model_vector_validate_olmo_v1.pbs)"
VECTOR_JOB="$(qsub -W depend=afterok:${VALIDATE_JOB} jobs/cross_model_vector_olmo_v1.pbs)"
{
  printf 'validate=%s\n' "$VALIDATE_JOB"
  printf 'vector=%s\n' "$VECTOR_JOB"
} | tee "$ROOT/vector_job_ids.txt"

