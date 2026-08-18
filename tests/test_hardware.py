import pytest

import persona_drift.hardware as hardware
from persona_drift.hardware import GPUInfo, validate_cuda_hardware


def gpu(
    index: int,
    *,
    name: str = "NVIDIA RTX PRO 6000 Blackwell Server Edition",
    memory: float = 95.6,
    bf16: bool = True,
) -> GPUInfo:
    return GPUInfo(index, name, memory, (12, 0), bf16)


def test_blackwell_pair_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hardware, "inspect_gpus", lambda: [gpu(0), gpu(1)])
    devices = validate_cuda_hardware(
        expected_gpu_count=2,
        expected_name_substring="blackwell",
        require_bf16=True,
        min_memory_gib=90,
    )
    assert len(devices) == 2


def test_wrong_device_count_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hardware, "inspect_gpus", lambda: [gpu(0)])
    with pytest.raises(RuntimeError, match="expected 2 visible GPUs"):
        validate_cuda_hardware(expected_gpu_count=2)


def test_missing_bf16_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        hardware,
        "inspect_gpus",
        lambda: [gpu(0), gpu(1, bf16=False)],
    )
    with pytest.raises(RuntimeError, match="BF16 is required"):
        validate_cuda_hardware(expected_gpu_count=2, require_bf16=True)
