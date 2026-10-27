# SPDX-License-Identifier: LGPL-2.1-or-later
"""Find a document object by its spoken name (DESIGN.md 7, Umbenennen).

"Benenne den Körper zwei in Grundplatte um": the user reads the tree, where FreeCAD writes
"Körper002". Names are compared without spaces and punctuation, number words as digits, without
leading zeros; then fuzzily, but numbers must agree ("Körper 7" is not "Körper002").
"""

import re
from difflib import SequenceMatcher

from ttm_core.languages import NUMBER_VALUES

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
