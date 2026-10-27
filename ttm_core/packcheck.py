# SPDX-License-Identifier: LGPL-2.1-or-later
"""Check a language pack before a pull request (DESIGN.md 16.1, tools/check_pack.py).

check(language) returns [(level, message)]: "error" (the pack is broken or its corpus fails),
"warning" (works, but something is missing) or "info".
"""

import json
import os
import re

from ttm_core import corpus, langpack
from ttm_core.phonetics import ALGORITHMS as PHONETIC_ALGORITHMS
from ttm_core.stemming import ALGORITHMS as STEMMING_ALGORITHMS

REFERENCE = "en"           # the pack a new language is compared with
FILES = ("language.json", "patterns.json", "vocab.json", "speech.json")
GROUPS = {"label", "target", "pick"}
LISTS = ("filler_words", "parameter_words", "clause_words", "particles", "stop_words", "statement_words",
         "negative_words", "article_numbers", "radius_words", "angle_names", "angle_units",
         "pattern_leading", "pattern_trailing")
TABLES = ("number_values", "pick_words", "value_names", "unit_factors")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(code, name):
    """(data, error message or None); data is {} for a missing file."""
    path = os.path.join(langpack.LANG_DIR, code, name)
    if not os.path.isfile(path):
        return {}, None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        return {}, "{}/{}: not valid JSON: {}".format(code, name, e)
    if not isinstance(data, dict):
        return {}, "{}/{}: must be a JSON object".format(code, name)
    return data, None


def check(language):
    out = []
    error = lambda m: out.append(("error", m))
    warn = lambda m: out.append(("warning", m))
    info = lambda m: out.append(("info", m))

    if not os.path.isfile(os.path.join(langpack.LANG_DIR, language, "language.json")):
        error("{}: no lang/{}/language.json".format(language, language))
        return out
    own, problem = _load(language, "language.json")
    if problem:
        error(problem)
        return out
    base = own.get("base")
    if base and not os.path.isfile(os.path.join(langpack.LANG_DIR, base, "language.json")):
        error("{}: base pack '{}' does not exist".format(language, base))
    for code in langpack.chain(language):
        for name in FILES[1:]:
            if _load(code, name)[1]:
                error(_load(code, name)[1])
    if any(level == "error" for level, _ in out):
        return out

    chain = langpack.chain(language)
    info("chain: " + " → ".join(chain))
    pack = langpack.pack(language)
    data = {}
    for code in chain:
        layer, _ = _load(code, "language.json")
        langpack._merge(data, layer)

    # word lists and tables
    for code in chain:
        layer, _ = _load(code, "language.json")
        for key, value in layer.items():
            name = key.lstrip("+")
            if name in LISTS and not (isinstance(value, list) and all(isinstance(w, str) for w in value)):
                error("{}/language.json: '{}' must be a list of words".format(code, key))
            if name in TABLES and not isinstance(value, dict):
                error("{}/language.json: '{}' must be a table (word → number)".format(code, key))
    reference, _ = _load(REFERENCE, "language.json")
    missing = [k for k in reference if not k.startswith("_") and k not in ("name", "base") and k not in data]
    if missing and language != REFERENCE:
        warn("missing compared to '{}': {}".format(REFERENCE, ", ".join(missing)))
    if "name" not in own:
        warn("no 'name' in language.json: the settings page shows the code")

    # algorithms
    if not pack.phonetics:
        warn("no 'phonetics': words are compared by spelling only, not by sound")
    elif pack.phonetics not in PHONETIC_ALGORITHMS:
        warn("phonetics '{}' is unknown (known: {}): comparing by spelling only".format(
            pack.phonetics, ", ".join(sorted(PHONETIC_ALGORITHMS))))
    if not pack.stemmer:
        warn("no 'stemmer': help texts are compared word by word")
    elif pack.stemmer not in STEMMING_ALGORITHMS:
        warn("stemmer '{}' is unknown (known: {})".format(pack.stemmer, ", ".join(sorted(STEMMING_ALGORITHMS))))

    # patterns
    for code in chain:
        patterns, _ = _load(code, "patterns.json")
        macros = patterns.get("macros", {})
        for entry in patterns.get("patterns", []):
            if not (isinstance(entry, list) and len(entry) == 2):
                error("{}/patterns.json: each pattern is [command, regular expression]: {}".format(code, entry))
                continue
            command, regex = entry
            for name, value in macros.items():
                regex = regex.replace("{" + name + "}", value)
            try:
                compiled = re.compile(regex)
            except re.error as e:
                error("{}/patterns.json: pattern for {} does not compile: {}".format(code, command, e))
                continue
            unknown = set(compiled.groupindex) - GROUPS
            if unknown:
                error("{}/patterns.json: unknown group(s) {} for {} (allowed: {})".format(
                    code, ", ".join(sorted(unknown)), command, ", ".join(sorted(GROUPS))))

    # vocabulary
    for code in chain:
        vocab, _ = _load(code, "vocab.json")
        for command, phrases in vocab.items():
            if command.startswith("_"):
                continue
            if not (isinstance(phrases, list) and all(isinstance(p, str) for p in phrases)):
                error("{}/vocab.json: '{}' must be a list of phrases".format(code, command))

    # speech output
    if not pack.voice:
        warn("no 'voice' in speech.json: no speech output (see https://huggingface.co/rhasspy/piper-voices)")
    reference_speech, _ = _load(REFERENCE, "speech.json")
    missing = sorted(set(reference_speech.get("messages", {})) - set(pack.messages))
    if missing and language != REFERENCE:
        warn("speech messages missing compared to '{}': {}".format(REFERENCE, ", ".join(missing)))

    # translation of the user interface
    root = chain[0]
    if root != REFERENCE and not os.path.isfile(os.path.join(ROOT, "translations", "TalkToMe_{}.qm".format(root))):
        info("no translations/TalkToMe_{}.qm: the user interface stays English".format(root))

    # corpus
    try:
        cases = corpus.cases(language)
    except ValueError as e:
        error(str(e))
        return out
    if not cases:
        warn("no corpus: add lang/{}/corpus.jsonl with sentences and the steps they must give".format(language))
        return out
    usable = []
    for case in cases:
        try:
            corpus.context(language, case["context"])
            usable.append(case)
        except KeyError:
            error("{}:{}: context '{}' not found (record it with tools/record_context.py)".format(
                case["source"], case["line"], case["context"]))
    results = corpus.run(language, usable)
    counts = corpus.summary(results)
    info("corpus: {} cases – {}".format(len(results), ", ".join("{} {}".format(n, o) for o, n in counts.items() if n)))
    for r in results:
        if r.outcome != "correct" and not r.case.get("known"):
            error(corpus.describe(r))
        elif r.outcome == "correct" and r.case.get("known"):
            warn("fixed – remove \"known\": " + corpus.describe(r))
    return out
