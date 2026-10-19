"""Piper voices for the speech output (DESIGN.md 10.1).

A voice is a name from https://huggingface.co/rhasspy/piper-voices ("de_DE-thorsten-medium"),
downloaded into a cache on first use like the Whisper models, or a path to an .onnx file the user
got elsewhere. Loading takes a few seconds; until then the service gives tones only.
"""

import os
import threading
import urllib.request

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
DEFAULT_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "talktome", "voices")


def voice_url(name, suffix):
    """Download URL of a file of a named voice: <lang>_<REGION>-<speaker>-<quality>."""
    parts = name.split("-")
    if len(parts) != 3 or "_" not in parts[0]:
        raise ValueError("not a Piper voice name: {!r}".format(name))
    locale, speaker, quality = parts
    language = locale.split("_")[0]
    return "{}/{}/{}/{}/{}/{}{}".format(BASE_URL, language, locale, speaker, quality, name, suffix)


def voice_files(voice, cache_dir):
    """(model, config) paths of a voice given by path or by name."""
    if voice.endswith(".onnx") or os.sep in voice:
        return voice, voice + ".json"
    model = os.path.join(cache_dir, voice + ".onnx")
    return model, model + ".json"


def download(voice, cache_dir, log):
    model, config = voice_files(voice, cache_dir)
    if os.path.exists(model) and os.path.exists(config):
        return model, config
    os.makedirs(cache_dir, exist_ok=True)
    for path, suffix in ((config, ".onnx.json"), (model, ".onnx")):
        if os.path.exists(path):
            continue
        log("downloading voice {} ({}) ...".format(voice, suffix))
        partial = path + ".part"
        with urllib.request.urlopen(voice_url(voice, suffix), timeout=30) as response, open(partial, "wb") as f:
            while True:
                block = response.read(1 << 16)
                if not block:
                    break
                f.write(block)
        os.replace(partial, path)
    return model, config


class LazySpeaker:
    """Loads the voice in the background; synth() raises until it is ready, so callers fall back
    to tones. Synthesized sentences are cached: the fixed ones come without delay."""

    def __init__(self, voice, cache_dir=DEFAULT_CACHE, log=print, warm_up=()):
        self.voice = voice
        self.cache_dir = cache_dir
        self.log = log
        self._piper = None
        self._cache = {}
        self._lock = threading.Lock()
        if voice:
            threading.Thread(target=self._load, args=(tuple(warm_up),), daemon=True).start()

    def _load(self, warm_up):
        try:
            from piper import PiperVoice
            model, config = download(self.voice, self.cache_dir, self.log)
            self._piper = PiperVoice.load(model, config_path=config)
            self.log("voice {} loaded".format(self.voice))
            for text in warm_up:
                self.synth(text)
        except Exception as e:
            self.log("speech output not available ({}): tones only".format(e))

    def synth(self, text):
        if self._piper is None:
            raise RuntimeError("voice not ready")
        with self._lock:
            if text not in self._cache:
                import numpy as np
                chunks = list(self._piper.synthesize(text))
                audio = np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32)
                self._cache[text] = (audio, self._piper.config.sample_rate)
            return self._cache[text]
