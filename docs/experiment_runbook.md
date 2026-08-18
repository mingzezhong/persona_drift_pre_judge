# Experiment runbook

## Canonical project and environment

- Project: `/shared/homes/u24524629/persona_drift_pre_judge`
- Conda environment: `persona-drift`
- Model cache: `$HOME/.cache/huggingface`
- Scheduler: PBS Pro; do not use the obsolete `gpuq` queue name.

Reusable experiment code belongs in `src/`, command-line entry points in
`scripts/`, PBS specifications in `jobs/`, and frozen experiment settings in
`configs/`. Generated tensors and metadata go to `outputs/`; scheduler and
application logs go to `logs/`. Both generated directories are ignored.

## Validation gate

From a two-GPU compute allocation:

```bash
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate persona-drift
cd /shared/homes/u24524629/persona_drift_pre_judge

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python -m pytest -p no:cacheprovider
PYTHONPATH=src python scripts/check_hardware.py
```

Do not start data collection unless tests pass and both visible GPUs report
Blackwell, at least 90 GiB, and BF16 support.

## Qwen activation smoke test

Interactive execution:

```bash
export HF_HOME="$HOME/.cache/huggingface"
export TOKENIZERS_PARALLELISM=false
PYTHONPATH=src python scripts/smoke_qwen_capture.py
```

The command writes `activations.pt`, `response.txt`, and `metadata.json` under
`outputs/smoke/qwen_capture/`. It refuses to overwrite a non-empty output
directory unless `--overwrite` is supplied.

Batch execution from the project root:

```bash
qsub jobs/smoke_qwen_capture.pbs
```

The acceptance criteria for Qwen2.5-7B-Instruct are BF16 model parameters,
finite tensors, and both activation shapes equal to `[28, 3584]`.

The gate passed in PBS job `42615.hpc-head01`; see
`docs/experiment_ledger.md`. The verified model commit is frozen in
`configs/pilot.yaml`.

## Extraction smoke test

The extraction smoke selects one prompt, both persona axes, both polarities,
and one seed, for four examples total:

```bash
qsub jobs/smoke_extraction.pbs
```

Its immutable output location is `outputs/extraction/smoke/`. Do not use these
engineering examples to estimate final persona vectors.
