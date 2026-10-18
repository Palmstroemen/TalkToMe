"""Decide what to do with a recognized sentence (DESIGN.md, sections 7 and 9.3).

    execute         a clear, active command
    not_understood  looks like a command attempt, but no safe match → error tone
    ignore          probably not meant for FreeCAD (empty, or a long unrelated sentence) → silence

Principle: rather do nothing than the wrong thing.
"""

from dataclasses import dataclass, field

from ttm_core.languages import FILLER_WORDS
from ttm_core.matching import command_words, phrase_score
from ttm_core.phonetics import PHONETICS

# Higher levels win over equally good matches in lower levels (DESIGN.md 6.2).
LEVEL_BONUS = {"dialog": 0.03, "edit": 0.02, "workbench": 0.01, "global": 0.0}


@dataclass
class Decision:
    kind: str                      # "execute", "not_understood" or "ignore"
    command: str = None
    score: float = 0.0
    level: str = None
    reason: str = None             # for not_understood / ignore
    alternatives: list = field(default_factory=list)   # [(command, score)], best first


def decide(text, candidates, language=None, threshold=0.75, margin=0.05,
           ignore_below=0.55, ignore_min_words=4):
    """
    threshold         minimal score for executing
    margin            a second command on the same level closer than this makes it ambiguous
    ignore_below      sentences with at least ignore_min_words words scoring below this are
                      treated as talk not meant for FreeCAD: no error tone
    """
    words = command_words(text, language)
    if not words:
        return Decision("ignore", reason="empty")
    fillers = FILLER_WORDS.get(language, set())
    if fillers and all(w in fillers for w in words):
        return Decision("ignore", reason="filler")
    phonetic = PHONETICS.get(language)

    best_per_command = {}
    for c in candidates:
        score = max((phrase_score(words, command_words(p, language), phonetic) for p in c["phrases"]),
                    default=0.0)
        ranked = (score + LEVEL_BONUS.get(c["level"], 0.0), score, c)
        if c["id"] not in best_per_command or ranked[:2] > best_per_command[c["id"]][:2]:
            best_per_command[c["id"]] = ranked
    if not best_per_command:
        return Decision("ignore", reason="no_candidates")

    ranking = sorted(best_per_command.values(), key=lambda r: r[:2], reverse=True)
    alternatives = [(c["id"], round(score, 3)) for _, score, c in ranking[:3]]
    adjusted, score, best = ranking[0]
    result = dict(command=best["id"], score=round(score, 3), level=best["level"], alternatives=alternatives)

    if score < threshold:
        if score < ignore_below and len(words) >= ignore_min_words:
            return Decision("ignore", reason="unrelated", **result)
        return Decision("not_understood", reason="no_match", **result)
    if len(ranking) > 1:
        adjusted2, score2, second = ranking[1]
        if score2 >= threshold and second["level"] == best["level"] and adjusted - adjusted2 < margin:
            return Decision("not_understood", reason="ambiguous", **result)
    if not best["active"]:
        return Decision("not_understood", reason="inactive", **result)
    return Decision("execute", **result)
