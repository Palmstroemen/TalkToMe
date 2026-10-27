# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for choosing between the GPU and the CPU profile."""

import pytest

from talktome_service.profiles import select_profile


def test_auto_without_gpu_uses_cpu_profile():
    p = select_profile("auto", cuda_devices=0)
    assert (p.device, p.compute_type, p.model) == ("cpu", "int8", "base")
    assert not p.fallback


def test_auto_with_gpu_uses_gpu_profile():
    p = select_profile("auto", cuda_devices=1)
    assert (p.device, p.compute_type, p.model) == ("cuda", "float16", "small")


def test_requested_cuda_without_gpu_falls_back_to_cpu():
    p = select_profile("cuda", cuda_devices=0)
    assert p.device == "cpu"
    assert p.fallback


def test_requested_cpu_with_gpu_stays_on_cpu():
    assert select_profile("cpu", cuda_devices=2).device == "cpu"


def test_model_override():
    assert select_profile("auto", cuda_devices=0, model="small").model == "small"


def test_unknown_device():
    with pytest.raises(ValueError):
        select_profile("tpu", cuda_devices=0)
