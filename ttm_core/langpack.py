"""Language packs: what the recognition needs to know about a language (DESIGN.md 13.1).

    lang/<code>/language.json   word lists, number words, names of the phonetic and stemming algorithm
    lang/<code>/patterns.json   sentence patterns for commands with free text
    lang/<code>/vocab.json      phrases for commands (synonyms)
    lang/<code>/speech.json     sentences of the speech output and the default voice

The user's changes live in <user dir>/lang/<code>/ with the same files: a list there replaces the
pack's list, patterns there come before the pack's. Algorithms (phonetics, stemming) stay code;
a pack names the one it uses.
"""

import json
import os

LANG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lang")

_user_dir = None
_cache = {}


def configure(user_dir):
    """Where the user's changes are (FreeCAD's user data dir + "TalkToMe"), or None."""
    global _user_dir
    _user_dir = user_dir
    _cache.clear()


def languages():
    """Codes of the languages with a pack."""
    if not os.path.isdir(LANG_DIR):
        return []
    return sorted(d for d in os.listdir(LANG_DIR) if os.path.isfile(os.path.join(LANG_DIR, d, "language.json")))


def _read(directory, language, name):
    if directory is None:
        return {}
    path = os.path.join(directory, language, name)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


class Pack:
    def __init__(self, language, data, patterns, vocab, speech):
        self.language = language
        self.name = data.get("name", language)
        self.phonetics = data.get("phonetics")
        self.stemmer = data.get("stemmer")
        self.filler_words = set(data.get("filler_words", []))
        self.parameter_words = set(data.get("parameter_words", []))
        self.clause_words = set(data.get("clause_words", []))
        self.particles = set(data.get("particles", []))
        self.stop_words = self.filler_words | self.particles | set(data.get("stop_words", []))
        self.number_values = dict(data.get("number_values", {}))
        self.pick_words = dict(data.get("pick_words", {}))
        self.pattern_leading = set(data.get("pattern_leading", []))
        self.pattern_trailing = set(data.get("pattern_trailing", []))
        self.patterns = patterns
        self.vocab = vocab
        self.voice = speech.get("voice")
        self.messages = speech.get("messages", {})


def _patterns(*sources):
    """[(command, regex)] in order, macros replaced."""
    result = []
    for source in sources:
        macros = source.get("macros", {})
        for command, regex in source.get("patterns", []):
            for name, value in macros.items():
                regex = regex.replace("{" + name + "}", value)
            result.append((command, regex))
    return result


def pack(language):
    if language not in _cache:
        user_dir = os.path.join(_user_dir, "lang") if _user_dir else None
        data = dict(_read(LANG_DIR, language, "language.json"))
        data.update(_read(user_dir, language, "language.json"))
        user_patterns = _read(user_dir, language, "patterns.json")
        pack_patterns = _read(LANG_DIR, language, "patterns.json")
        user_patterns.setdefault("macros", pack_patterns.get("macros", {}))
        patterns = _patterns(user_patterns, pack_patterns)
        vocab = {k: v for k, v in _read(LANG_DIR, language, "vocab.json").items()
                 if not k.startswith("_") and isinstance(v, list)}
        speech = dict(_read(LANG_DIR, language, "speech.json"))
        user_speech = _read(user_dir, language, "speech.json")
        speech["messages"] = dict(speech.get("messages", {}), **user_speech.get("messages", {}))
        if user_speech.get("voice"):
            speech["voice"] = user_speech["voice"]
        _cache[language] = Pack(language, data, patterns, vocab, speech)
    return _cache[language]


class View:
    """One field of all packs, as a read-only mapping language → value: FILLER_WORDS.get("de").
    An empty value counts as missing."""

    def __init__(self, field, convert=None):
        self.field = field
        self.convert = convert

    def get(self, language, default=None):
        if not language:
            return default
        value = getattr(pack(language), self.field)
        if self.convert is not None:
            value = self.convert(value)
        return value if value else default

    def __getitem__(self, language):
        value = self.get(language)
        if value is None:
            raise KeyError(language)
        return value

    def __contains__(self, language):
        return self.get(language) is not None
