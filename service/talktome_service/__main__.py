"""Start the speech service.

    TTM_TOKEN=<secret> python -m talktome_service --language de

TTM_USER_DIR (optional) is where the user's changes to the language packs are (DESIGN.md 13.1).

The service prints "TTM_PORT=<port>" on stdout once it accepts connections.
"""

import argparse
import json
import os
import sys

from talktome_service.profiles import DEVICES, select_profile


def log(*args):
    print("[talktome]", *args, file=sys.stderr, flush=True)


def probe():
    """What the settings page can offer: input devices, CUDA devices, speech output."""
    result = {"microphones": [], "default_microphone": None, "cuda_devices": 0, "speech": False}
    try:
        import sounddevice as sd
        default_input = sd.default.device[0]
        for index, device in enumerate(sd.query_devices()):
            if device["max_input_channels"] > 0:
                result["microphones"].append({"index": index, "name": device["name"]})
        result["default_microphone"] = default_input if default_input is not None and default_input >= 0 else None
    except Exception as e:
        result["error"] = str(e)
    try:
        from talktome_service.stt import cuda_device_count
        result["cuda_devices"] = cuda_device_count()
    except Exception:
        pass
    try:
        import piper  # noqa: F401
        result["speech"] = True
    except ImportError:
        pass
    return result


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
    ap.add_argument("--speech", choices=("off", "important", "chatty"), default="important",
                    help="speech output: off (tones only), important moments, or chatty")
    ap.add_argument("--voice", help="Piper voice name (downloaded on first use) or path to an .onnx file "
                                    "(default: the language pack's voice)")
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--probe", action="store_true",
                    help="print microphones, CUDA devices and voice support as JSON (for the settings page)")
    args = ap.parse_args(argv)

    if args.probe:
        print(json.dumps(probe()))
        return 0

    if args.list_devices:
        import sounddevice as sd
        print(sd.query_devices())
        return 0

    token = os.environ.get("TTM_TOKEN")
    if not token:
        log("TTM_TOKEN is not set")
        return 2

    from ttm_core import langpack
    langpack.configure(os.environ.get("TTM_USER_DIR") or None)
    if args.language not in langpack.languages():
        log("no language pack for '{}': recognition works, but without word lists and patterns".format(args.language))

    from talktome_service.audio import Microphone, WavSource
    from talktome_service.server import Service
    from talktome_service.stt import Transcriber, cuda_device_count
    from talktome_service.tones import TonePlayer
    from talktome_service.vad import SileroVAD
    from talktome_service.voice import LazySpeaker
    from ttm_core.speech import phrase

    profile = select_profile(args.device, cuda_device_count(), args.model)
    if profile.fallback:
        log("no usable GPU found, falling back to the CPU profile")
    log("loading model '{}' on {} ({}) ...".format(profile.model, profile.device, profile.compute_type))
    # A variant ("de-AT") is recognized in its base's language: Whisper only knows "de".
    transcriber = Transcriber(profile, langpack.pack(args.language).recognition_language, beam_size=args.beam, cpu_threads=args.threads)
    log("model loaded")

    mic = args.mic
    if mic is not None and mic.isdigit():
        mic = int(mic)
    source = WavSource(args.input_wav) if args.input_wav else Microphone(mic)
    info = {"language": args.language, "model": profile.model, "device": profile.device,
            "compute_type": profile.compute_type, "fallback": profile.fallback}

    speaker = None
    voice = args.voice or langpack.pack(args.language).voice
    if args.speech != "off" and voice:
        fixed = [phrase(kind, args.language, args.speech)              # said without delay later
                 for kind in ("ready", "not_understood", "failed", "done", "train_done")]
        speaker = LazySpeaker(voice, log=log, warm_up=[t for t in fixed if t])

    service = Service(token=token, source=source, vad=SileroVAD(), transcriber=transcriber,
                      tones=TonePlayer(volume=args.volume), host=args.host, port=args.port,
                      info=info, log=log, speaker=speaker, speech_level=args.speech)
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
