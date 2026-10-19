"""Commands with free-text parameters, recognized by sentence patterns (DESIGN.md 7).

"Den nennen wir Bodenplatte" renames an object. The name is free text, so it can't be matched
fuzzily against phrases like command names; instead each language lists sentence patterns
with a named group for the parameter.
"""

import re

from ttm_core.languages import CLAUSE_WORDS, STOP_WORDS

_PRONOUN = r"(?:den|die|das|ihn|sie|es|diesen|diese|dieses)"

PATTERNS = {
    "de": [
        ("ui:rename", rf"(?:{_PRONOUN}\s+)?(?:nennen\s+wir|nenne\s+ich|nennen|nenne|nenn)\s+"
                      rf"(?:{_PRONOUN}\s+)?(?:jetzt\s+|mal\s+)?(?P<label>.+)"),
        ("ui:rename", rf"(?:{_PRONOUN}\s+)?(?:benenne|benenn)\s+(?:{_PRONOUN}\s+)?um\s+(?:in|zu|auf)\s+(?P<label>.+)"),
        ("ui:rename", r"(?:umbenennen|umbenannt)\s+(?:in|zu|auf)\s+(?P<label>.+)"),
        ("ui:rename", r"(?:der|die|das|er|sie|es|dieser|diese|dieses)\s+(?:soll|sollte)\s+(?P<label>.+?)\s+heißen"),
        ("ui:rename", r"(?:der|die|das|er|sie|es)\s+heißt\s+(?P<label>.+)"),
        ("ui:rename", r"(?:gib|gebe|geben\s+wir)\s+(?:ihm|ihr)\s+den\s+namen\s+(?P<label>.+)"),
        ("ui:rename", r"name\s+(?P<label>.+)"),
    ],
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


def parse(clause, language):
    """(command, args) if the clause matches a pattern, else None."""
    words = _strip(re.sub(r"[.,;:!?]+", " ", clause).split(), language)
    text = " ".join(words)
    stop = STOP_WORDS.get(language, set())
    for command, pattern in PATTERNS.get(language, []):
        m = re.fullmatch(pattern, text, re.IGNORECASE)
        if not m:
            continue
        label = m.group("label").strip()
        if not label or all(w.lower() in stop for w in label.split()):
            continue                           # "Wie nennen wir das": no name, a pronoun
        return command, {"label": label[0].upper() + label[1:]}
    return None
