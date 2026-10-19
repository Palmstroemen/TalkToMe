"""Commands with free-text parameters, recognized by sentence patterns (DESIGN.md 7).

"Den nennen wir Bodenplatte" renames an object. The name is free text, so it can't be matched
fuzzily against phrases like command names; instead each language lists sentence patterns
with a named group for the parameter:

    label   free text, e.g. a new name
    target  free text naming the object it is about ("benenne den Körper2 in X um")
    pick    an entry of the question menu ("die zweite"); number words are parameters
            elsewhere, so they can't be phrases

Training adds learned patterns per user: how the recognizer heard such a sentence, with the
parameter cut out ("nenndas {label}"). Their fixed part may differ a little next time.
"""

import re
from difflib import SequenceMatcher

from ttm_core.languages import CLAUSE_WORDS, STOP_WORDS
from ttm_core.phonetics import PHONETICS

LABEL = "{label}"
SIMILAR = 0.8        # fixed part of a learned pattern: spelling similarity needed (or same sound)

_PRONOUN = r"(?:den|die|das|ihn|sie|es|diesen|diese|dieses)"

PATTERNS = {
    "de": [
        ("ui:rename", rf"(?:{_PRONOUN}\s+)?(?:nennen\s+wir|nenne\s+ich|nennen|nenne|nenn)\s+"
                      rf"(?:{_PRONOUN}\s+)?(?:jetzt\s+|mal\s+)?(?P<label>.+)"),
        ("ui:rename", rf"(?:{_PRONOUN}\s+)?(?:benenne|benenn)\s+(?:{_PRONOUN}\s+)?um\s+(?:in|zu|auf)\s+(?P<label>.+)"),
        ("ui:rename", r"(?:benenne|benenn)\s+(?:doch\s+)?(?:mal\s+)?(?:bitte\s+)?(?:(?:den|die|das)\s+)?"
                      r"(?P<target>.+?)\s+(?:um\s+)?(?:in|zu|auf)\s+(?P<label>.+?)(?:\s+um)?"),
        ("ui:rename", r"(?:umbenennen|umbenannt)\s+(?:in|zu|auf)\s+(?P<label>.+)"),
        ("ui:rename", r"(?:der|die|das|er|sie|es|dieser|diese|dieses)\s+(?:soll|sollte)\s+(?P<label>.+?)\s+heißen"),
        ("ui:rename", r"(?:der|die|das|er|sie|es)\s+heißt\s+(?P<label>.+)"),
        ("ui:rename", r"(?:gib|gebe|geben\s+wir)\s+(?:ihm|ihr)\s+den\s+namen\s+(?P<label>.+)"),
        ("ui:rename", r"name\s+(?P<label>.+)"),
        ("ui:pick", r"(?:nummer\s+|die\s+|den\s+|das\s+)?(?P<pick>\w+)"),
    ],
}

PICK_WORDS = {
    "de": {"1": 1, "eins": 1, "erste": 1, "ersten": 1, "erstes": 1, "erstens": 1,
           "2": 2, "zwei": 2, "zweite": 2, "zweiten": 2, "zweites": 2, "zweitens": 2,
           "3": 3, "drei": 3, "dritte": 3, "dritten": 3, "drittes": 3, "drittens": 3},
}

# Words around the pattern that belong to neither command nor parameter.
LEADING = {"bitte", "jetzt", "mal", "also"}
TRAILING = {"bitte"}


def _strip(words, language):
    lead = CLAUSE_WORDS.get(language, set()) | LEADING
    while words and words[0].lower() in lead:
        words = words[1:]
    while words and words[-1].lower() in TRAILING:
        words = words[:-1]
    return words


def _words(text):
    return re.sub(r"[.,;:!?]+", " ", text).split()


def make_template(heard, label, language):
    """A learned pattern from a heard sentence and the part that was the parameter:
    ("Nenndas Bodenplatte", "Bodenplatte") → "nenndas {label}". None if the label isn't in
    the sentence or nothing else is."""
    words = [w.lower() for w in _strip(_words(heard), language)]
    name = [w.lower() for w in _words(label)]
    n = len(name)
    if not n:
        return None
    for i in range(len(words) - n + 1):
        if words[i:i + n] == name:
            fixed = words[:i] + [LABEL] + words[i + n:]
            return " ".join(fixed) if len(fixed) > 1 else None
    return None


def _similar(words, fixed, language):
    if len(words) != len(fixed):
        return False
    if not fixed:
        return True
    a, b = " ".join(words).lower(), " ".join(fixed)
    if SequenceMatcher(None, a, b).ratio() >= SIMILAR:
        return True
    phonetic = PHONETICS.get(language)
    return phonetic is not None and [phonetic(w) for w in words] == [phonetic(w) for w in fixed]


def _learned(words, templates, language):
    """The label if words match one of the learned templates, else None."""
    for template in templates:
        parts = template.split()
        if LABEL not in parts:
            continue
        i = parts.index(LABEL)
        prefix, suffix = parts[:i], parts[i + 1:]
        if len(words) <= len(prefix) + len(suffix):
            continue
        end = len(words) - len(suffix)
        if _similar(words[:len(prefix)], prefix, language) and _similar(words[end:], suffix, language):
            return " ".join(words[len(prefix):end])
    return None


def parse(clause, language, learned=None):
    """(command, args) if the clause matches a pattern, else None.

    learned: {command: [templates]} from training, tried after the built-in patterns.
    """
    words = _strip(_words(clause), language)
    text = " ".join(words)
    stop = STOP_WORDS.get(language, set())
    for command, pattern in PATTERNS.get(language, []):
        m = re.fullmatch(pattern, text, re.IGNORECASE)
        if not m:
            continue
        if "pick" in m.groupdict():
            n = PICK_WORDS.get(language, {}).get(m.group("pick").lower())
            if n is not None:
                return command, {"pick": n}
            continue
        label = m.group("label").strip()
        if not label or all(w.lower() in stop for w in label.split()):
            continue                           # "Wie nennen wir das": no name, a pronoun
        args = {"label": label[0].upper() + label[1:]}
        target = (m.groupdict().get("target") or "").strip()
        if target and not all(w.lower() in stop for w in target.split()):
            args["target"] = target            # "ihn", "das": no name, the addon decides
        return command, args
    for command, templates in (learned or {}).items():
        label = _learned(words, templates, language)
        if label and not all(w.lower() in stop for w in label.split()):
            return command, {"label": label[0].upper() + label[1:]}
    return None
