# SPDX-License-Identifier: LGPL-2.1-or-later
"""Install the speech service: its own Python environment with its packages (README, Setup).

The service runs on a Python of the system, not on FreeCAD's: FreeCAD's Python lacks the
packages, and an AppImage's Python vanishes with the AppImage's mount. The environment lives in
the user's Talk to me folder, so updating or reinstalling the addon keeps it.
"""

import os
import re

MIN_PYTHON = (3, 10)          # oldest Python with wheels of all packages (numpy, av, onnxruntime)

# What the output of a failed step says, and what to do about it (shown by the addon).
PROBLEMS = (
    ("venv", ("ensurepip is not available", "No module named venv", "No module named ensurepip")),
    ("portaudio", ("PortAudio library not found",)),
    ("network", ("Failed to establish a new connection", "Temporary failure in name resolution",
                 "Network is unreachable", "Read timed out")),
    ("disk", ("No space left on device",)),
    ("python_version", ("No matching distribution found", "Could not find a version that satisfies")),
)


def venv_dir(user_dir):
    return os.path.join(user_dir, "venv")


def venv_python(venv, windows=False):
    if windows:
        return os.path.join(venv, "Scripts", "python.exe")
    return os.path.join(venv, "bin", "python")


def default_python(user_dir, service_dir, exists=os.path.exists, windows=False):
    """The environment in the user folder; an older one in the addon's service/.venv while it is
    the only one (installed by hand, as the README described it before)."""
    new = venv_python(venv_dir(user_dir), windows)
    old = venv_python(os.path.join(service_dir, ".venv"), windows)
    if not exists(new) and exists(old):
        return old
    return new


def search_path(path, appdir=None):
    """Folders of PATH to look for a Python in, without those of an AppImage: it puts its own
    Python first, which is gone once FreeCAD is closed."""
    dirs = [d for d in path.split(os.pathsep) if d]
    if appdir:
        root = os.path.join(appdir, "")
        dirs = [d for d in dirs if not os.path.join(d, "").startswith(root)]
    return dirs


def parse_version(text):
    match = re.match(r"\s*(\d+)\.(\d+)\s*$", text or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def _foreign(program):
    """A Python that belongs to an application bundle or is Windows' store alias."""
    return ".app/Contents/" in program.replace("\\", "/") or "WindowsApps" in program


def find_python(dirs, version_of, windows=False, isfile=os.path.isfile, join=os.path.join):
    """(program, args, version) of the first Python new enough, or None.

    version_of(program, args) runs it and returns its (major, minor) or None. On Windows the
    launcher py.exe ("py -3") is tried after python.exe."""
    names = (("python.exe", []), ("py.exe", ["-3"])) if windows else (("python3", []), ("python", []))
    for name, args in names:
        for d in dirs:
            program = join(d, name)
            if not isfile(program) or _foreign(program):
                continue
            version = version_of(program, args)
            if version is not None and version >= MIN_PYTHON:
                return program, args, version
    return None


def install_steps(base, venv, requirements, have_venv, windows=False):
    """[(step, program, args)]: create the environment unless it exists, install the packages.
    base is (program, args) of the system's Python; installing again adds what newer requirements ask for."""
    steps = []
    if not have_venv:
        program, args = base
        steps.append(("venv", program, list(args) + ["-m", "venv", venv]))
    steps.append(("packages", venv_python(venv, windows),
                  ["-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off",
                   "-r", requirements]))
    return steps


def diagnose(output):
    """Known problems named in the output of a step, e.g. ["venv"]."""
    return [key for key, signs in PROBLEMS if any(sign in output for sign in signs)]
