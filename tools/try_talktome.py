# SPDX-License-Identifier: LGPL-2.1-or-later
"""Try "Talk to me" outside FreeCAD.

Starts the speech service, switches the microphone on and prints every recognized
sentence with its latency and the matching test command. Confirmation and error
tones are played just like they will be in FreeCAD.

    service/.venv/bin/python tools/try_talktome.py
    service/.venv/bin/python tools/try_talktome.py --model small
    service/.venv/bin/python tools/try_talktome.py --input-wav a.wav b.wav     # without microphone

Commands and phrases come from lang/<language>/vocab.json (command ID -> phrases); the service\ndecides exactly as it will in FreeCAD.
Stop with Ctrl+C.
"""

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_DIR = os.path.join(ROOT, "service")
sys.path.insert(0, ROOT)

from ttm_core.protocol import VERSION, LineDecoder, encode, make_message  # noqa: E402

END_SILENCE_MS = 640     # pause after which the service considers a sentence finished

TTY = sys.stdout.isatty()


def color(code, text):
    return "\033[{}m{}\033[0m".format(code, text) if TTY else text


def start_service(args, token):
    cmd = [sys.executable, "-m", "talktome_service", "--language", args.language, "--device", args.device]
    if args.model:
        cmd += ["--model", args.model]
    if args.mic:
        cmd += ["--mic", args.mic]
    if args.input_wav:
        cmd += ["--input-wav"] + [os.path.abspath(p) for p in args.input_wav]
    cmd += ["--volume", str(args.volume)]
    env = dict(os.environ, TTM_TOKEN=token,
               PYTHONPATH=os.pathsep.join([ROOT, SERVICE_DIR, os.environ.get("PYTHONPATH", "")]))
    proc = subprocess.Popen(cmd, cwd=SERVICE_DIR, env=env, stdout=subprocess.PIPE, text=True)
    for line in proc.stdout:
        if line.startswith("TTM_PORT="):
            return proc, int(line.split("=", 1)[1])
    raise SystemExit("speech service did not start (exit code {})".format(proc.wait()))


def show_transcript(msg):
    text = msg.get("text", "")
    stt_ms = msg.get("stt_ms", 0)
    timing = "Erkennung {} ms · Antwortzeit ≈ {} ms · gesprochen {:.1f} s".format(
        stt_ms, END_SILENCE_MS + stt_ms, msg.get("speech_ms", 0) / 1000)
    print("{}  »{}«   {}".format(time.strftime("%H:%M:%S"), color(1, text) if text else "", color(90, timing)))


def show_decision(msg):
    kind = msg["type"]
    alternatives = ", ".join("{} {:.2f}".format(c, s) for c, s in msg.get("alternatives") or [])
    part = ""
    if msg.get("utterance") and msg.get("text") != msg.get("utterance"):
        part = "»{}« ".format(msg["text"])           # one step of a sequence
    if kind == "plan":
        via = ", aus Hilfstext" if msg.get("via") == "description" else ""
        print("          → {}{}  {}".format(part, color(32, msg["command"]),
                                            color(90, "(Wert {:.2f}{})".format(msg["score"], via))))
    elif kind == "not_understood":
        reasons = {"no_match": "kein passender Befehl", "ambiguous": "mehrdeutig", "inactive": "gerade nicht verfügbar"}
        print("          → {}{}  {}".format(part, color(31, "nicht verstanden: " + reasons.get(msg.get("reason"), str(msg.get("reason")))),
                                          color(90, alternatives)))
    else:
        print("          → {}".format(color(90, "ignoriert (kein Befehl gemeint)")))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--language", default="de")
    ap.add_argument("--model", help="tiny, base, small, ... (default by hardware profile)")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--mic", help="input device name or index")
    ap.add_argument("--input-wav", nargs="+", help="use WAV files instead of the microphone")
    ap.add_argument("--commands", help="vocabulary file (default: lang/<language>/vocab.json)")
    ap.add_argument("--volume", type=float, default=0.4, help="tone volume, 0 = silent")
    ap.add_argument("--no-hotwords", action="store_true", help="don't hint the test vocabulary to Whisper")
    ap.add_argument("--exit-after", type=int, default=0, help="stop after N sentences (for scripts)")
    args = ap.parse_args()

    path = args.commands or os.path.join(ROOT, "lang", args.language, "vocab.json")
    with open(path, encoding="utf-8") as f:
        commands = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

    token = secrets.token_hex(16)
    print(color(90, "Starte Sprachdienst (beim ersten Mal wird das Modell heruntergeladen) ..."))
    proc, port = start_service(args, token)
    sock = socket.create_connection(("127.0.0.1", port))
    sock.sendall(encode(make_message("hello", token=token, version=VERSION, language=args.language)))
    # The vocabulary file stands in for the context FreeCAD will send: all commands, all active.
    candidates = [{"id": cmd, "level": "workbench", "phrases": phrases, "active": True}
                  for cmd, phrases in commands.items()]
    context = make_message("context", candidates=candidates)
    if args.no_hotwords:
        context["hotwords"] = []
    sock.sendall(encode(context))
    sock.sendall(encode(make_message("listen", on=True)))
    decoder = LineDecoder()
    count = 0
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                print("Sprachdienst hat die Verbindung beendet.")
                break
            for msg in decoder.feed(data):
                if msg["type"] == "welcome":
                    print(color(90, "Modell {model} auf {device} ({compute_type}), Sprache {language}".format(**msg)))
                elif msg["type"] == "state" and msg["state"] == "listening" and count == 0:
                    print(color(32, "● Mikrofon an – sprich einen Befehl. Strg+C beendet.\n"))
                elif msg["type"] == "transcript":
                    show_transcript(msg)
                elif msg["type"] in ("plan", "not_understood", "ignored"):
                    show_decision(msg)
                    if msg["type"] == "plan":        # FreeCAD would execute it now
                        sock.sendall(encode(make_message("result", ok=True, id=msg.get("id"))))
                    count += 1
                elif msg["type"] == "error":
                    print(color(31, "Fehler: {}".format(msg.get("message"))))
            if args.exit_after and count >= args.exit_after:
                time.sleep(0.5)      # let the last tone play
                break
    except KeyboardInterrupt:
        print()
    finally:
        try:
            sock.sendall(encode(make_message("bye")))
            sock.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()


if __name__ == "__main__":
    main()
