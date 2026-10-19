"""Stage 1b of the matching pipeline: comparison with the help texts of commands (DESIGN.md 7).

FreeCAD describes every command in a status tip, translated into the user's language:

    Vertiefung: "Extrudiert die ausgewählte Skizze ... und zieht das Ergebnis von dem Körper ab"

Sentence and help texts are reduced to word stems ("Extrudiere" and "Extrudiert" → "extrud").
A command scores by how much of the sentence its help text covers; words that are rare among
the help texts weigh more, words found in no help text at all are left out.
"""

import math

from ttm_core.clauses import split_clauses
from ttm_core.languages import PARTICLES, STOP_WORDS
from ttm_core.matching import command_words
from ttm_core.stemming import STEMMERS

JOIN = "+"           # separable verb: "zieht ... ab" → "ab+zieh"


def terms(text, language):
    """Word stems of a sentence, without stop words.

    German separable verbs put their particle at the end of the clause: "zieht das Ergebnis
    von dem Körper ab". Such a particle is joined with the clause's first word, the verb, and
    kept as an additional term, so "abziehen" and "hinzufügen" can be told apart.
    """
    stem = STEMMERS.get(language, lambda w: w)
    stop = STOP_WORDS.get(language, set())
    particles = PARTICLES.get(language, set())
    result = set()
    for clause in (command_words(c, language) for c in split_clauses(text, language)):
        content = [stem(w) for w in clause if w not in stop]
        result.update(content)
        if content and len(clause) > 1 and clause[-1] in particles:
            result.add(clause[-1] + JOIN + content[0])
    return result


class DescriptionIndex:
    """Help texts of the current candidates, {command id: text}."""

    def __init__(self, descriptions, language):
        self.language = language
        self.docs = {cmd: terms(text, language) for cmd, text in descriptions.items() if text}
        df = {}
        for doc in self.docs.values():
            for t in doc:
                df[t] = df.get(t, 0) + 1
        n = len(self.docs)
        self.weight = {t: math.log(1 + n / count) for t, count in df.items()}

    def _known(self, text):
        return {t for t in terms(text, self.language) if t in self.weight}

    def known_terms(self, text):
        """Number of words of the sentence that occur in any help text (joined verbs not counted)."""
        return sum(1 for t in self._known(text) if JOIN not in t)

    def explained(self, text, cmd):
        """Number of words of the sentence found in the help text of cmd (joined verbs not counted)."""
        return sum(1 for t in self._known(text) & self.docs.get(cmd, set()) if JOIN not in t)

    def ranking(self, text):
        """[(command id, coverage 0..1)], best first."""
        known = self._known(text)
        total = sum(self.weight[t] for t in known)
        if not total:
            return [(cmd, 0.0) for cmd in self.docs]
        scores = [(cmd, round(sum(self.weight[t] for t in known & doc) / total, 3))
                  for cmd, doc in self.docs.items()]
        return sorted(scores, key=lambda s: s[1], reverse=True)
