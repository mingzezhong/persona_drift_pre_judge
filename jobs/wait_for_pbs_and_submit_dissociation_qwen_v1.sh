#!/bin/bash
# Wait for CETUS PBS recovery, then submit the frozen confirmation pipeline once.

set -euo pipefail
PROJECT_DIR="${1:-/shared/homes/u24524629/persona_drift_pre_judge}"
cd "$PROJECT_DIR"
LOCK_DIR="logs/.dissociation_confirmation_qwen_v1_submit_watch.lock"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-720}"
POLL_SECONDS="${POLL_SECONDS:-60}"

mkdir -p logs
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "A submission watcher is already active: $LOCK_DIR" >&2
  exit 2
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
  if [[ -e outputs/gate_c/dissociation_confirmation/qwen_v1 ]]; then
    echo "$(date -Is) output root exists; refusing duplicate submission"
    exit 2
  fi
  if qstat -Bf >/dev/null 2>&1; then
    echo "$(date -Is) PBS is available; submitting frozen pipeline"
    exec jobs/submit_dissociation_confirmation_qwen_v1.sh "$PROJECT_DIR"
  fi
  echo "$(date -Is) PBS unavailable (attempt $attempt/$MAX_ATTEMPTS)"
  sleep "$POLL_SECONDS"
done

echo "$(date -Is) PBS did not recover within the watcher window" >&2
exit 3

