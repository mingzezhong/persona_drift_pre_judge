#!/bin/bash
# Submit the frozen Gate C development pipeline with afterok dependencies.

set -euo pipefail
PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"
OUTPUT_ROOT="outputs/gate_c/development_v1"
if [ -e "$OUTPUT_ROOT" ]; then
  echo "Refusing to reuse existing Gate C output root: $OUTPUT_ROOT" >&2
  exit 2
fi
mkdir -p "$OUTPUT_ROOT"
sha256sum \
  configs/gate_c_development_v1.yaml \
  docs/gate_c_development_v1_design.md \
  docs/gate_c_development_v1_implementation_freeze.md \
  src/persona_drift/gate_c.py \
  scripts/build_gate_c_dataset.py \
  scripts/embed_gate_c_prefixes.py \
  scripts/analyze_gate_c_development.py \
  tests/test_gate_c.py \
  tests/test_gate_c_pipeline.py \
  jobs/gate_c_validate_v1.pbs \
  jobs/gate_c_build_dataset_v1.pbs \
  jobs/gate_c_embed_e5_v1.pbs \
  jobs/gate_c_analyze_v1.pbs \
  > "$OUTPUT_ROOT/protocol_files.sha256"

VALIDATE_JOB="$(qsub jobs/gate_c_validate_v1.pbs)"
BUILD_JOB="$(qsub -W depend=afterok:"$VALIDATE_JOB" jobs/gate_c_build_dataset_v1.pbs)"
EMBED_JOB="$(qsub -W depend=afterok:"$BUILD_JOB" jobs/gate_c_embed_e5_v1.pbs)"
ANALYZE_JOB="$(qsub -W depend=afterok:"$EMBED_JOB" jobs/gate_c_analyze_v1.pbs)"
{
  printf 'validate=%s\n' "$VALIDATE_JOB"
  printf 'build=%s\n' "$BUILD_JOB"
  printf 'embed=%s\n' "$EMBED_JOB"
  printf 'analyze=%s\n' "$ANALYZE_JOB"
} > "$OUTPUT_ROOT/job_ids.txt"
cat "$OUTPUT_ROOT/job_ids.txt"
