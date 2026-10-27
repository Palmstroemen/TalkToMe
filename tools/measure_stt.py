# SPDX-License-Identifier: LGPL-2.1-or-later
"""Measure latency and accuracy of the speech recognition (Phase 0).

Record your own voice (one utterance per phrase, cut automatically by the VAD):

    service/.venv/bin/python tools/measure_stt.py record --out samples/de

Compare models on the recordings:

    service/.venv/bin/python tools/measure_stt.py bench --samples samples/de --models tiny,base,small

A sample folder contains WAV files (16 kHz, mono, 16 bit) and an index.json:
    [{"file": "01.wav", "refs": ["Zeichne ein Rechteck"]}, ...]
"""

import argparse
import json
import os
import queue
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "service"))

import numpy as np  # noqa: E402

from talktome_service.audio import Microphone, read_wav, write_wav  # noqa: E402
from talktome_service.metrics import best_wer  # noqa: E402
from talktome_service.profiles import DEVICES, select_profile  # noqa: E402
from talktome_service.segmenter import Segmenter  # noqa: E402
from talktome_service.server import FRAME_MS  # noqa: E402

DEFAULT_PHRASES = os.path.join(ROOT, "tools", "phrases_de.txt")


def load_phrases(path):
    phrases = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                phrases.append([alt.strip() for alt in line.split("|")])
    return phrases


def record(args):
    from talktome_service.vad import SileroVAD
    os.makedirs(args.out, exist_ok=True)
    frames = queue.Queue()
    mic = Microphone(args.mic)
    vad, seg = SileroVAD(), Segmenter(frame_ms=FRAME_MS)
    index = []
    mic.start(frames.put)
    try:
        for i, refs in enumerate(load_phrases(args.phrases), 1):
            input("\n[{:2}] Enter drücken, dann sagen:  »{}«".format(i, refs[0]))
            while not frames.empty():
                frames.get_nowait()
            vad.reset()
            seg.reset()
            while True:
                frame = frames.get()
                utterance = seg.push(frame, vad.prob(frame))
                if utterance is not None:
                    break
            name = "{:02}.wav".format(i)
            write_wav(os.path.join(args.out, name), np.concatenate(utterance.frames))
            index.append({"file": name, "refs": refs})
            print("     aufgenommen: {:.1f} s".format(len(utterance.frames) * FRAME_MS / 1000))
    finally:
        mic.stop()
    with open(os.path.join(args.out, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print("\n{} Aufnahmen in {}".format(len(index), args.out))


def bench(args):
    from talktome_service.stt import Transcriber, cuda_device_count
    with open(os.path.join(args.samples, "index.json"), encoding="utf-8") as f:
        index = json.load(f)
    samples = [(e, read_wav(os.path.join(args.samples, e["file"]))) for e in index]
    cuda = cuda_device_count()
    rows = []
    for model in args.models.split(","):
        for beam in [int(b) for b in args.beams.split(",")]:
            profile = select_profile(args.device, cuda, model)
            t0 = time.monotonic()
            tr = Transcriber(profile, args.language, beam_size=beam, cpu_threads=args.threads)
            load_s = time.monotonic() - t0
            tr.transcribe(np.zeros(16000, dtype=np.float32))        # warm-up
            lat, rtf, wers = [], [], []
            for entry, audio in samples:
                r = tr.transcribe(audio)
                w = best_wer(entry["refs"], r["text"])
                lat.append(r["stt_ms"])
                rtf.append(r["stt_ms"] / (len(audio) / 16))
                wers.append(w)
                if args.verbose:
                    mark = "ok " if w == 0 else "ERR"
                    print("  {} {:>5} ms  {:<35} → {}".format(mark, r["stt_ms"], entry["refs"][0], r["text"]))
            lat_sorted = sorted(lat)
            rows.append({
                "model": model, "beam": beam, "device": profile.device, "compute": profile.compute_type,
                "load_s": round(load_s, 1),
                "mean_ms": round(statistics.mean(lat)),
                "p90_ms": lat_sorted[min(len(lat) - 1, int(0.9 * len(lat)))],
                "rtf": round(statistics.mean(rtf), 2),
                "wer": round(statistics.mean(wers), 3),
                "exact": "{}/{}".format(sum(w == 0 for w in wers), len(wers)),
            })
            print(rows[-1], flush=True)
    print()
    cols = ["model", "beam", "device", "compute", "load_s", "mean_ms", "p90_ms", "rtf", "wer", "exact"]
    print(" | ".join(cols))
    print(" | ".join("---" for _ in cols))
    for r in rows:
        print(" | ".join(str(r[c]) for c in cols))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="record test phrases from the microphone")
    rec.add_argument("--out", required=True)
    rec.add_argument("--phrases", default=DEFAULT_PHRASES)
    rec.add_argument("--mic")
    b = sub.add_parser("bench", help="compare models on recorded samples")
    b.add_argument("--samples", required=True)
    b.add_argument("--models", default="tiny,base,small")
    b.add_argument("--beams", default="1")
    b.add_argument("--device", choices=DEVICES, default="auto")
    b.add_argument("--language", default="de")
    b.add_argument("--threads", type=int, default=0)
    b.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    record(args) if args.cmd == "record" else bench(args)


if __name__ == "__main__":
    main()
