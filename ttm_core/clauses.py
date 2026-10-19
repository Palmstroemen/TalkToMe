"""Split an utterance into clauses (DESIGN.md 7, sequences).

"Wechsle zu Part Design, erstelle einen Körper und dann speichern" has three clauses.
Clause words ("und", "dann") stay at the start of their clause, so joined clauses read
like the original sentence.
"""

import re

from ttm_core.languages import CLAUSE_WORDS

# Sentence punctuation, except a decimal separator between digits ("12,5 mm").
PUNCTUATION = re.compile(r"(?<!\d)[,;:.!?]|[,;:.!?](?!\d)")


def split_clauses(text, language):
    separators = CLAUSE_WORDS.get(language, set())
    clauses = []
    for part in PUNCTUATION.split(text):
        clause, content = [], False
        for token in part.split():
            if token.lower() in separators and content:
                clauses.append(" ".join(clause))
                clause, content = [], False
            clause.append(token)
            content = content or token.lower() not in separators
        if content:
            clauses.append(" ".join(clause))
    return clauses
