# SPDX-License-Identifier: LGPL-2.1-or-later
"""Install the speech service like the addon does and say one command to it (for CI).

    python tools/smoke_install.py --venv /tmp/ttm-venv

1. finds the system's Python and runs the install steps of ttm_core.install,
2. asks the installed service what it finds (--probe, as the settings page does),
3. lets the language pack's voice say a command into a WAV file,
4. plays it to the service (tools/try_talktome.py) and checks that it plans the command.

Steps 3 and 4 download the voice and the speech model. No microphone or speaker is needed.
"""

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_DIR = os.path.join(ROOT, "service")
sys.path.insert(0, ROOT)

from ttm_core import install  # noqa: E402

WINDOWS = os.name == "nt"

SPEAK = r"""
import sys
import numpy as np
from piper import PiperVoice
from talktome_service.audio import SAMPLE_RATE, write_wav
from talktome_service.tones import TonePlayer
from talktome_service.voice import DEFAULT_CACHE, download
model, config = download(sys.argv[1], DEFAULT_CACHE, print)
voice = PiperVoice.load(model, config_path=config)
audio = np.concatenate([c.audio_float_array for c in voice.synthesize(sys.argv[2])])
write_wav(sys.argv[3], TonePlayer(sample_rate=SAMPLE_RATE).resample(audio, voice.config.sample_rate))
"""


def version_of(program, args):
    try:
        out = subprocess.run([program] + list(args) + ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return install.parse_version(out.stdout)


def run(program, args, **kwargs):
    print("$ {} {}".format(program, " ".join(args)), flush=True)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([ROOT, SERVICE_DIR]))
    return subprocess.run([program] + list(args), env=env, check=True, **kwargs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venv", required=True)
    ap.add_argument("--language", default="de")
    ap.add_argument("--sentence", default="Zeichne ein Rechteck")
    ap.add_argument("--expect", default="Sketcher_CreateRectangle")
    ap.add_argument("--model", default="base")
    args = ap.parse_args()

    found = install.find_python(install.search_path(os.environ.get("PATH", "")), version_of, windows=WINDOWS)
    if found is None:
        sys.exit("no Python {}.{} or newer found".format(*install.MIN_PYTHON))
    program, base_args, version = found
    print("system Python: {} {} ({}.{})".format(program, " ".join(base_args), *version))
    venv = os.path.abspath(args.venv)
    for step, prog, step_args in install.install_steps((program, base_args), venv,
                                                       os.path.join(SERVICE_DIR, "requirements.txt"),
                                                       have_venv=os.path.exists(venv), windows=WINDOWS):
        run(prog, step_args)
    python = install.venv_python(venv, WINDOWS)

    probe = run(python, ["-m", "talktome_service", "--probe"], cwd=SERVICE_DIR, capture_output=True, text=True)
    print("probe:", probe.stdout.strip())
    json.loads(probe.stdout)

    from ttm_core import langpack
    wav = os.path.join(venv, "command.wav")
    run(python, ["-c", SPEAK, langpack.pack(args.language).voice, args.sentence, wav], cwd=SERVICE_DIR)

    out = run(python, [os.path.join(ROOT, "tools", "try_talktome.py"), "--language", args.language,
                       "--model", args.model, "--volume", "0", "--input-wav", wav, "--exit-after", "1"],
              cwd=ROOT, capture_output=True, text=True, timeout=900, encoding="utf-8")
    print(out.stdout)
    if args.expect not in out.stdout:
        sys.exit("expected the command {} for »{}«".format(args.expect, args.sentence))
    print("ok: »{}« → {}".format(args.sentence, args.expect))


if __name__ == "__main__":
    main()
