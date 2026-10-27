# SPDX-License-Identifier: LGPL-2.1-or-later
"""GPU and CPU profiles for the speech recognition. See DESIGN.md, section 12.1."""

from dataclasses import dataclass

DEVICES = ("auto", "cuda", "cpu")


@dataclass
class Profile:
    device: str
    compute_type: str
    model: str
    fallback: bool = False       # a GPU was requested but isn't usable


def select_profile(requested, cuda_devices, model=None):
    """Choose device, precision and default model from the request and the hardware."""
    if requested not in DEVICES:
        raise ValueError("unknown device {!r}, expected one of {}".format(requested, DEVICES))
    use_gpu = requested in ("auto", "cuda") and cuda_devices > 0
    if use_gpu:
        profile = Profile("cuda", "float16", "small")
    else:
        profile = Profile("cpu", "int8", "base", fallback=(requested == "cuda"))
    if model:
        profile.model = model
    return profile
