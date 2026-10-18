"""Start the speech service.

    TTM_TOKEN=<secret> python -m talktome_service --language de

The service prints "TTM_PORT=<port>" on stdout once it accepts connections.
"""

import argparse
import os
import sys

from talktome_service.profiles import DEVICES, select_profile


def log(*args):
    print("[talktome]", *args, file=sys.stderr, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="talktome_service")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0, help="0 = choose a free port")
    ap.add_argument("--language", default="de")
    ap.add_argument("--device", choices=DEVICES, default="auto")
    ap.add_argument("--model", help="whisper model, e.g. tiny, base, small (default by profile)")
    ap.add_argument("--beam", type=int, default=1)
    ap.add_argument("--threads", type=int, default=0, help="CPU threads, 0 = automatic")
    ap.add_argument("--mic", help="input device name or index (see --list-devices)")
    ap.add_argument("--input-wav", nargs="+", help="play these WAV files instead of the microphone")
    ap.add_argument("--volume", type=float, default=0.4)
    ap.add_argument("--list-devices", action="store_true")
    args = ap.parse_args(argv)

    if args.list_devices:
        import sounddevice as sd
        print(sd.query_devices())
        return 0

    token = os.environ.get("TTM_TOKEN")
    if not token:
        log("TTM_TOKEN is not set")
        return 2

    from talktome_service.audio import Microphone, WavSource
    from talktome_service.server import Service
    from talktome_service.stt import Transcriber, cuda_device_count
    from talktome_service.tones import TonePlayer
    from talktome_service.vad import SileroVAD

    profile = select_profile(args.device, cuda_device_count(), args.model)
    if profile.fallback:
        log("no usable GPU found, falling back to the CPU profile")
    log("loading model '{}' on {} ({}) ...".format(profile.model, profile.device, profile.compute_type))
    transcriber = Transcriber(profile, args.language, beam_size=args.beam, cpu_threads=args.threads)
    log("model loaded")

    mic = args.mic
    if mic is not None and mic.isdigit():
        mic = int(mic)
    source = WavSource(args.input_wav) if args.input_wav else Microphone(mic)
    info = {"language": args.language, "model": profile.model, "device": profile.device,
            "compute_type": profile.compute_type, "fallback": profile.fallback}

    service = Service(token=token, source=source, vad=SileroVAD(), transcriber=transcriber,
                      tones=TonePlayer(volume=args.volume), host=args.host, port=args.port,
                      info=info, log=log)
    port = service.start()
    print("TTM_PORT={}".format(port), flush=True)
    log("listening on {}:{}".format(args.host, port))
    try:
        service.wait()
    except KeyboardInterrupt:
        pass
    service.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
