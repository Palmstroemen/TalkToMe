# SPDX-License-Identifier: LGPL-2.1-or-later
"""Commands with free-text parameters, recognized by sentence patterns (DESIGN.md 7).

"Den nennen wir Bodenplatte" renames an object. The name is free text, so it can't be matched
fuzzily against phrases like command names; instead each language lists sentence patterns
with a named group for the parameter:

    label   free text, e.g. a new name
    target  free text naming the object it is about ("benenne den Körper2 in X um")
    pick    an entry of the question menu ("die zweite"); number words are parameters
            elsewhere, so they can't be phrases

An application may send patterns of its own, in the spoken language and with the pack's macros
("lege {pronoun} in (?P<role>.+?) ab"), and lists of names (entities). A group named like a
list is a slot: it takes the id of the name said ("Eingangsrechnungen" → "04_Finanz/Ausgaben"),
and the pattern doesn't apply if none fits or the application sent no such list. Any other group
is free text.

Training adds learned patterns per user: how the recognizer heard such a sentence, with the
parameter cut out ("nenndas {label}"). Their fixed part may differ a little next time.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ttm_core.langpack import View, expand
from ttm_core.languages import CLAUSE_WORDS, STOP_WORDS
from ttm_core.objects import find_entity
from ttm_core.phonetics import PHONETICS

LABEL = "{label}"
SIMILAR = 0.8        # fixed part of a learned pattern: spelling similarity needed (or same sound)

# Built-in patterns per language come from the language packs (lang/<code>/patterns.json).
PATTERNS = View("patterns")
MACROS = View("macros")
PICK_WORDS = View("pick_words")
LEADING = View("pattern_leading")      # words around a pattern that belong to neither command
TRAILING = View("pattern_trailing")    # nor parameter ("bitte")


@dataclass
class Grammar:
    """Patterns beyond the language pack's, and the names their slots take."""
    learned: dict = None                          # {command: [templates]} from training
    own: list = field(default_factory=list)       # [(command, regex)] of the application, tried first
    entities: dict = field(default_factory=dict)  # {list name: [{"id", "phrases"}]}


def _strip(words, language):
    lead = CLAUSE_WORDS.get(language, set()) | LEADING.get(language, set())
    trail = TRAILING.get(language, set())
    while words and words[0].lower() in lead:
        words = words[1:]
    while words and words[-1].lower() in trail:
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


def _slots(m, entities, language, stop):
    """{group: value} of the groups other than label, target and pick; None if a slot has no
    fitting name or a free text is empty. A group is a slot if entities has a list of its name,
    even an empty one (no projects yet)."""
    args = {}
    for name, value in m.groupdict().items():
        if name in ("label", "target", "pick"):
            continue
        value = (value or "").strip()
        if not value or all(w.lower() in stop for w in value.split()):
            return None
        if name in entities:
            value = find_entity(value, entities[name], language)
            if value is None:
                return None
        args[name] = value
    return args


def parse(clause, language, patterns=None):
    """(command, args) if the clause matches a pattern, else None.

    patterns: a Grammar, or only the learned patterns {command: [templates]} from training,
    tried after the built-in ones.
    """
    grammar = patterns if isinstance(patterns, Grammar) else Grammar(learned=patterns)
    words = _strip(_words(clause), language)
    text = " ".join(words)
    stop = STOP_WORDS.get(language, set())
    macros = MACROS.get(language, {})
    own = [(command, expand(regex, macros)) for command, regex in grammar.own or []]
    for command, pattern in own + list(PATTERNS.get(language, [])):
        m = re.fullmatch(pattern, text, re.IGNORECASE)
        if not m:
            continue
        groups = m.groupdict()
        if "pick" in groups:
            n = PICK_WORDS.get(language, {}).get(m.group("pick").lower())
            if n is not None:
                return command, {"pick": n}
            continue
        args = _slots(m, grammar.entities or {}, language, stop)
        if args is None:
            continue
        if "label" in groups:
            label = (m.group("label") or "").strip()
            if not label or all(w.lower() in stop for w in label.split()):
                continue                       # "Wie nennen wir das": no name, a pronoun
            args["label"] = label[0].upper() + label[1:]
        target = (groups.get("target") or "").strip()
        if target and not all(w.lower() in stop for w in target.split()):
            args["target"] = target            # "ihn", "das": no name, the application decides
        return command, args
    for command, templates in (grammar.learned or {}).items():
        label = _learned(words, templates, language)
        if label and not all(w.lower() in stop for w in label.split()):
            return command, {"label": label[0].upper() + label[1:]}
    return None
