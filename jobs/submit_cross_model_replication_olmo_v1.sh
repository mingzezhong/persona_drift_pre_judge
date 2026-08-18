#!/bin/bash
# Freeze and submit untouched OLMo cross-model replication.

set -euo pipefail
PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"
ROOT="outputs/cross_model_replication/olmo_v1"

if [[ ! -f "$ROOT/vectors/persona_vectors.pt" || ! -f "$ROOT/vectors/summary.json" ]]; then
  echo "Frozen OLMo vectors are not complete." >&2
  exit 2
fi
for path in "$ROOT/shards" "$ROOT/trajectories.jsonl" "$ROOT/probes.jsonl" "$ROOT/review" "$ROOT/judges" "$ROOT/analysis"; do
  if [[ -e "$path" ]]; then
    echo "Refusing to reuse cross-model outcome path: $path" >&2
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

FILES=(
  configs/cross_model_replication_olmo_v1.yaml
  configs/ai_judges_cross_model_olmo_v1.yaml
  configs/extraction_judge_rubric_v2.yaml
  data/templates/persona_cross_model_olmo_v1.yaml
  docs/cross_model_target_amendment_v1.md
  docs/cross_model_replication_olmo_v1_preregistration.md
  "$ROOT/vector_protocol_files.sha256"
  "$ROOT/vectors/persona_vectors.pt"
  "$ROOT/vectors/summary.json"
  outputs/measurement/development_v1/analysis/scoring_model.json
  outputs/measurement/development_v1/analysis/summary.json
  src/persona_drift/activation.py
  src/persona_drift/conversation.py
  src/persona_drift/gate_a.py
  src/persona_drift/hardware.py
  src/persona_drift/judging.py
  src/persona_drift/measurement.py
  src/persona_drift/modeling.py
  src/persona_drift/representation.py
  scripts/check_hardware.py
  scripts/generate_gate_a_trajectories.py
  scripts/merge_gate_a_shards.py
  scripts/create_extraction_review_sheet.py
  scripts/judge_extraction.py
  scripts/validate_cross_model_replication.py
  scripts/analyze_cross_model_replication.py
  tests/test_cross_model_replication.py
  tests/test_judging.py
  tests/test_measurement.py
  jobs/cross_model_validate_olmo_v1.pbs
  jobs/cross_model_generate_independent_olmo_v1.pbs
  jobs/cross_model_generate_cautious_olmo_v1.pbs
  jobs/cross_model_merge_olmo_v1.pbs
  jobs/cross_model_judge_a_olmo_v1.pbs
  jobs/cross_model_judge_b_olmo_v1.pbs
  jobs/cross_model_judge_c_olmo_v1.pbs
  jobs/cross_model_analyze_olmo_v1.pbs
)
for file in "${FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing frozen replication file: $file" >&2
    exit 2
  fi
done
sha256sum "${FILES[@]}" > "$ROOT/replication_protocol_files.sha256"

VALIDATE_JOB="$(qsub jobs/cross_model_validate_olmo_v1.pbs)"
INDEPENDENT_JOB="$(qsub -W depend=afterok:${VALIDATE_JOB} jobs/cross_model_generate_independent_olmo_v1.pbs)"
CAUTIOUS_JOB="$(qsub -W depend=afterok:${VALIDATE_JOB} jobs/cross_model_generate_cautious_olmo_v1.pbs)"
MERGE_JOB="$(qsub -W depend=afterok:${INDEPENDENT_JOB}:${CAUTIOUS_JOB} jobs/cross_model_merge_olmo_v1.pbs)"
JUDGE_A_JOB="$(qsub -W depend=afterok:${MERGE_JOB} jobs/cross_model_judge_a_olmo_v1.pbs)"
JUDGE_B_JOB="$(qsub -W depend=afterok:${MERGE_JOB} jobs/cross_model_judge_b_olmo_v1.pbs)"
JUDGE_C_JOB="$(qsub -W depend=afterok:${MERGE_JOB} jobs/cross_model_judge_c_olmo_v1.pbs)"
ANALYZE_JOB="$(qsub -W depend=afterok:${JUDGE_A_JOB}:${JUDGE_B_JOB}:${JUDGE_C_JOB} jobs/cross_model_analyze_olmo_v1.pbs)"
{
  printf 'validate=%s\n' "$VALIDATE_JOB"
  printf 'independent=%s\n' "$INDEPENDENT_JOB"
  printf 'cautious=%s\n' "$CAUTIOUS_JOB"
  printf 'merge=%s\n' "$MERGE_JOB"
  printf 'judge_a=%s\n' "$JUDGE_A_JOB"
  printf 'judge_b=%s\n' "$JUDGE_B_JOB"
  printf 'judge_c=%s\n' "$JUDGE_C_JOB"
  printf 'analyze=%s\n' "$ANALYZE_JOB"
} | tee "$ROOT/replication_job_ids.txt"

