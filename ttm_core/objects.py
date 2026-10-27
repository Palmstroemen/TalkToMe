# SPDX-License-Identifier: LGPL-2.1-or-later
"""Find a named thing by its spoken name (DESIGN.md 7, Umbenennen).

"Benenne den Körper zwei in Grundplatte um": the user reads the tree, where FreeCAD writes
"Körper002". Names are compared without spaces and punctuation, number words as digits, without
leading zeros; then fuzzily, but numbers must agree ("Körper 7" is not "Körper002").

The same goes for the names an application sends for the slots of its sentence patterns
(find_entity): "Lege das in Eingangsrechnungen ab" names a folder by one of its phrases.
"""

import re
from difflib import SequenceMatcher

from ttm_core.languages import NUMBER_VALUES, STOP_WORDS
from ttm_core.matching import SOUND
from ttm_core.phonetics import PHONETICS
from ttm_core.text import normalize

THRESHOLD = 0.85
MARGIN = 0.05


def key(name, language):
    numbers = NUMBER_VALUES.get(language, {})
    tokens = re.findall(r"\w+", name.lower())
    text = "".join(str(numbers.get(t, t)) for t in tokens)
    return re.sub(r"(?<!\d)0+(?=\d)", "", text)


def find_object(spoken, labels, language):
    """The label meant by spoken, or None if none or more than one fits."""
    wanted = key(spoken, language)
    if not wanted:
        return None
    exact = [label for label in labels if key(label, language) == wanted]
    if exact:
        return exact[0] if len(exact) == 1 else None
    digits = re.findall(r"\d+", wanted)
    scored = sorted(((SequenceMatcher(None, wanted, key(label, language)).ratio(), label)
                     for label in labels if re.findall(r"\d+", key(label, language)) == digits),
                    reverse=True)
    if not scored or scored[0][0] < THRESHOLD:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < MARGIN:
        return None
    return scored[0][1]


def _similarity(spoken, phrase, language, phonetic, stop):
    """0..1; 0 if the numbers differ. Words like articles ("die Ausgaben") don't count."""
    if key(spoken, language) == key(phrase, language):
        return 1.0
    a = [w for w in normalize(spoken).split() if w not in stop]
    b = [w for w in normalize(phrase).split() if w not in stop]
    if not a or not b or re.findall(r"\d+", key(" ".join(a), language)) != re.findall(r"\d+", key(" ".join(b), language)):
        return 0.0
    score = SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    if phonetic and len(a) == len(b):
        codes = [phonetic(w) for w in a]
        if all(codes) and codes == [phonetic(w) for w in b]:
            score = max(score, SOUND)
    return score


def find_entity(spoken, entities, language):
    """The id of the entity meant by spoken, or None if none or more than one fits.

    entities: [{"id": ..., "phrases": [names and synonyms]}], e.g. the folders of a file manager.
    """
    phonetic = PHONETICS.get(language)
    stop = STOP_WORDS.get(language, frozenset())
    if not [w for w in normalize(spoken).split() if w not in stop]:
        return None
    best = {}
    for entity in entities:
        score = max((_similarity(spoken, p, language, phonetic, stop) for p in entity.get("phrases", [])), default=0.0)
        best[entity["id"]] = max(score, best.get(entity["id"], 0.0))
    scored = sorted(((score, id_) for id_, score in best.items()), reverse=True)
    if not scored or scored[0][0] < THRESHOLD:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < MARGIN:
        return None
    return scored[0][1]
