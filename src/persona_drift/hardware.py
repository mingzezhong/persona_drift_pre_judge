"""Runtime inspection and validation for CUDA experiment hardware."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import torch


@dataclass(frozen=True)
class GPUInfo:
    index: int
    name: str
    total_memory_gib: float
    capability: tuple[int, int]
    bf16_supported: bool


def inspect_gpus() -> list[GPUInfo]:
    """Describe visible CUDA devices without changing CUDA settings."""

    devices: list[GPUInfo] = []
    for index in range(torch.cuda.device_count()):
        properties = torch.cuda.get_device_properties(index)
        with torch.cuda.device(index):
            bf16_supported = bool(
                hasattr(torch.cuda, "is_bf16_supported")
                and torch.cuda.is_bf16_supported()
            )
        devices.append(
            GPUInfo(
                index=index,
                name=properties.name,
                total_memory_gib=properties.total_memory / (1024**3),
                capability=(properties.major, properties.minor),
                bf16_supported=bf16_supported,
            )
        )
    return devices


def validate_cuda_hardware(
    *,
    expected_gpu_count: int = 2,
    expected_name_substring: str | None = None,
    require_bf16: bool = False,
    min_memory_gib: float | None = None,
) -> list[GPUInfo]:
    """Validate the visible devices against the experiment configuration."""

    devices = inspect_gpus()
    rendered = [asdict(device) for device in devices]
    if len(devices) != expected_gpu_count:
        raise RuntimeError(
            f"expected {expected_gpu_count} visible GPUs, found {len(devices)}: "
            f"{rendered}"
        )
    if expected_name_substring is not None and any(
        expected_name_substring.casefold() not in device.name.casefold()
        for device in devices
    ):
        raise RuntimeError(
            f"expected GPU names containing {expected_name_substring!r}: {rendered}"
        )
    if require_bf16 and any(not device.bf16_supported for device in devices):
        raise RuntimeError(f"BF16 is required but not supported by every GPU: {rendered}")
    if min_memory_gib is not None and any(
        device.total_memory_gib < min_memory_gib for device in devices
    ):
        raise RuntimeError(
            f"expected at least {min_memory_gib} GiB per GPU: {rendered}"
        )
    return devices
