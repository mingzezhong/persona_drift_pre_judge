from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
HARDWARE_JOB = ROOT / "jobs/g1_reviewer_hardware_smoke.pbs"
MODEL_JOB = ROOT / "jobs/g1_reviewer_model_smoke.pbs"
REGISTRY = ROOT / "configs/g1_reviewer_registry_v2_3.yaml"


def test_smoke_jobs_reserve_all_gpus_on_two_gpu_shared_nodes() -> None:
    hardware = HARDWARE_JOB.read_text(encoding="utf-8")
    model = MODEL_JOB.read_text(encoding="utf-8")

    assert "#PBS -l select=1:ncpus=4:ngpus=2:mem=32gb" in hardware
    assert "#PBS -l select=1:ncpus=6:ngpus=2:mem=64gb" in model
    assert 'ASSIGNED_NGPUS=2' in hardware
    assert 'ASSIGNED_NGPUS=2' in model
    assert 'payload["gpu_count"] != assigned_gpu_count' in hardware
    assert "for device_index in range(assigned_gpu_count)" in hardware
    assert 'device=f"cuda:{device_index}"' in hardware
    assert "torch.cuda.device_count() != assigned_gpu_count" in model


def test_hardware_smoke_records_visibility_and_probes_float16() -> None:
    script = HARDWARE_JOB.read_text(encoding="utf-8")

    assert 'echo "cuda_visible_devices=${CUDA_VISIBLE_DEVICES:-scheduler-default}"' in script
    assert 'echo "pbs_gpufile=${PBS_GPUFILE:-unavailable}"' in script
    assert '"bf16_supported": bool(torch.cuda.is_bf16_supported())' in script
    assert "dtype=torch.float16" in script
    assert '"required_model_dtype": "float16"' in script
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    assert registry["runtime"]["dtype"] == "float16"


def test_smoke_jobs_accept_frozen_commit_without_requiring_git_on_compute() -> None:
    for path in (HARDWARE_JOB, MODEL_JOB):
        script = path.read_text(encoding="utf-8")
        assert 'SOURCE_COMMIT="${G1_SOURCE_COMMIT:-}"' in script
        assert "command -v git" in script
        assert 'SOURCE_COMMIT="${SOURCE_COMMIT:-unavailable}"' in script
        assert 'echo "commit=$(git rev-parse HEAD)"' not in script
