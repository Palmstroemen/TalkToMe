"""Try "Talk to me" outside FreeCAD.

Starts the speech service, switches the microphone on and prints every recognized
sentence with its latency and the matching test command. Confirmation and error
tones are played just like they will be in FreeCAD.

    service/.venv/bin/python tools/try_talktome.py
    service/.venv/bin/python tools/try_talktome.py --model small
    service/.venv/bin/python tools/try_talktome.py --input-wav a.wav b.wav     # without microphone

The test commands come from tools/test_commands_de.json (command ID -> phrases).
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

from ttm_core.matching import match  # noqa: E402
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


def show_transcript(msg, commands, threshold):
    text = msg.get("text", "")
    stt_ms = msg.get("stt_ms", 0)
    stamp = time.strftime("%H:%M:%S")
    timing = "Erkennung {} ms · Antwortzeit ≈ {} ms · gesprochen {:.1f} s".format(
        stt_ms, END_SILENCE_MS + stt_ms, msg.get("speech_ms", 0) / 1000)
    if not text:
        print("{}  {}   {}".format(stamp, color(90, "(nichts verstanden)"), color(90, timing)))
        return False
    cmd, score = match(text, commands, threshold)
    print("{}  »{}«".format(stamp, color(1, text)))
    if cmd:
        print("          → {}  {}".format(color(32, cmd), color(90, "(Übereinstimmung {:.2f})".format(score))))
    else:
        print("          → {}  {}".format(color(31, "kein Testbefehl"), color(90, "(bester Wert {:.2f})".format(score))))
    hints = "no_speech {}  logprob {}".format(msg.get("no_speech_prob"), msg.get("avg_logprob"))
    print("          {}   {}".format(color(90, timing), color(90, hints)))
    return cmd is not None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--language", default="de")
    ap.add_argument("--model", help="tiny, base, small, ... (default by hardware profile)")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--mic", help="input device name or index")
    ap.add_argument("--input-wav", nargs="+", help="use WAV files instead of the microphone")
    ap.add_argument("--commands", default=os.path.join(ROOT, "tools", "test_commands_de.json"))
    ap.add_argument("--threshold", type=float, default=0.75)
    ap.add_argument("--volume", type=float, default=0.4, help="tone volume, 0 = silent")
    ap.add_argument("--exit-after", type=int, default=0, help="stop after N sentences (for scripts)")
    args = ap.parse_args()

    with open(args.commands, encoding="utf-8") as f:
        commands = json.load(f)

    token = secrets.token_hex(16)
    print(color(90, "Starte Sprachdienst (beim ersten Mal wird das Modell heruntergeladen) ..."))
    proc, port = start_service(args, token)
    sock = socket.create_connection(("127.0.0.1", port))
    sock.sendall(encode(make_message("hello", token=token, version=VERSION, language=args.language)))
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
                    ok = show_transcript(msg, commands, args.threshold)
                    sock.sendall(encode(make_message("result", ok=ok)))
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
