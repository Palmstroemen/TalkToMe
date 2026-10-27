# SPDX-License-Identifier: LGPL-2.1-or-later
"""Language packs: what the recognition needs to know about a language (DESIGN.md 13.1).

    lang/<code>/language.json   word lists, number words, names of the phonetic and stemming algorithm
    lang/<code>/patterns.json   sentence patterns for commands with free text
    lang/<code>/vocab.json      phrases for commands (synonyms)
    lang/<code>/speech.json     sentences of the speech output and the default voice

A variant ("de-AT", "de-x-saxon") names its base in language.json ("base": "de") and holds only
what differs (DESIGN.md 16.3). The chain is read from the base to the variant:
    language.json   a value replaces, a table (number_values, ...) is merged, a list replaces;
                    "+filler_words" adds to the inherited list. "name" is not inherited.
    patterns.json   the variant's patterns come first; macros are inherited
    vocab.json      the variant's phrases come first, the base's follow
    speech.json     single messages and the voice replace the base's

The user's changes live in <user dir>/lang/<code>/ with the same files, on top of the chain: a
list there replaces the pack's list, patterns there come before the pack's. Algorithms
(phonetics, stemming) stay code; a pack names the one it uses.
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


FALLBACK = "en"


def default_language(ui_language, available=None):
    """The spoken language before the user chose one: the user interface's (its pack, or the pack
    of its base: "de_CH" → "de"), else English."""
    available = languages() if available is None else available
    code = (ui_language or "").replace("_", "-")
    for candidate in (code, code.split("-")[0], FALLBACK):
        if candidate in available:
            return candidate
    return available[0] if available else FALLBACK


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


def _merge(data, layer):
    """Apply one layer of language.json to the data inherited so far."""
    for key, value in layer.items():
        if key.startswith("+"):
            continue
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = dict(data[key], **value)
        else:
            data[key] = value
    for key, value in layer.items():
        if key.startswith("+") and isinstance(value, list):
            inherited = list(data.get(key[1:], []))
            data[key[1:]] = inherited + [v for v in value if v not in inherited]
    return data


def chain(language):
    """Codes from the root pack to language: ["de", "de-AT"]. A missing or circular base ends it."""
    result = [language]
    while True:
        base = _read(LANG_DIR, result[0], "language.json").get("base")
        if not base or base in result or not os.path.isfile(os.path.join(LANG_DIR, base, "language.json")):
            return result
        result.insert(0, base)


def _shipped(language):
    """language.json as the packs ship it, the chain merged, without the user's changes."""
    data = {}
    for code in chain(language):
        layer = _read(LANG_DIR, code, "language.json")
        data.pop("name", None)
        _merge(data, layer)
    return data


class Pack:
    def __init__(self, language, data, patterns, vocab, speech, chain=None):
        self.language = language
        self.chain = chain or [language]
        self.name = data.get("name", language)
        # What the speech recognition is told: Whisper knows "de", not "de-AT".
        self.recognition_language = data.get("recognition_language") or self.chain[0]
        self.phonetics = data.get("phonetics")
        self.stemmer = data.get("stemmer")
        self.filler_words = set(data.get("filler_words", []))
        self.parameter_words = set(data.get("parameter_words", []))
        self.clause_words = set(data.get("clause_words", []))
        self.statement_words = set(data.get("statement_words", []))
        self.particles = set(data.get("particles", []))
        self.stop_words = self.filler_words | self.particles | set(data.get("stop_words", []))
        self.number_values = dict(data.get("number_values", {}))
        self.pick_words = dict(data.get("pick_words", {}))
        self.value_names = dict(data.get("value_names", {}))
        self.unit_factors = dict(data.get("unit_factors", {}))
        self.negative_words = set(data.get("negative_words", []))
        self.article_numbers = set(data.get("article_numbers", []))
        self.angle_names = set(data.get("angle_names", []))
        self.angle_units = set(data.get("angle_units", [])) | {"°"}
        self.radius_words = set(data.get("radius_words", []))
        self.pattern_leading = set(data.get("pattern_leading", []))
        self.pattern_trailing = set(data.get("pattern_trailing", []))
        self.patterns = patterns
        self.vocab = vocab
        self.voice = speech.get("voice")
        self.messages = speech.get("messages", {})


def _patterns(sources, macros):
    """[(command, regex)] in order, macros replaced."""
    result = []
    for source in sources:
        for command, regex in source.get("patterns", []):
            for name, value in macros.items():
                regex = regex.replace("{" + name + "}", value)
            result.append((command, regex))
    return result


def pack(language):
    if language not in _cache:
        user_dir = os.path.join(_user_dir, "lang") if _user_dir else None
        codes = chain(language)
        data = _merge(_shipped(language), _read(user_dir, language, "language.json"))
        if "name" not in _read(LANG_DIR, language, "language.json"):
            data.pop("name", None)

        sources = [_read(user_dir, language, "patterns.json")]
        sources += [_read(LANG_DIR, code, "patterns.json") for code in reversed(codes)]
        macros = {}
        for source in reversed(sources):                     # the more specific wins
            macros.update(source.get("macros", {}))
        patterns = _patterns(sources, macros)

        vocab = {}
        for code in codes:
            for cmd, phrases in _read(LANG_DIR, code, "vocab.json").items():
                if not cmd.startswith("_") and isinstance(phrases, list):
                    vocab[cmd] = phrases + [p for p in vocab.get(cmd, []) if p not in phrases]

        speech = {"messages": {}}
        for source in [_read(LANG_DIR, code, "speech.json") for code in codes] + [_read(user_dir, language, "speech.json")]:
            speech["messages"].update(source.get("messages", {}))
            if source.get("voice"):
                speech["voice"] = source["voice"]
        _cache[language] = Pack(language, data, patterns, vocab, speech, codes)
    return _cache[language]


# Word lists a user may change on the settings page (DESIGN.md 13).
EDITABLE_LISTS = ("filler_words", "stop_words", "parameter_words", "clause_words", "particles", "statement_words")


def pack_list(language, key):
    """A word list as the packs ship it (the chain merged), without the user's changes."""
    return sorted(_shipped(language).get(key, []))


def save_list(language, key, words):
    """Store a changed word list in the user's folder; a list equal to the pack's is removed there."""
    if _user_dir is None:
        raise RuntimeError("no user folder configured")
    path = os.path.join(_user_dir, "lang", language, "language.json")
    data = _read(os.path.join(_user_dir, "lang"), language, "language.json")
    words = sorted({w.strip().lower() for w in words if w.strip()})
    if words == pack_list(language, key):
        data.pop(key, None)
    else:
        data[key] = words
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _cache.clear()                      # variants of this language inherit the list


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
