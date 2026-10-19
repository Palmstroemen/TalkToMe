"""Decide what to do with a recognized sentence (DESIGN.md, sections 7 and 9.3).

    execute         a clear, active command
    not_understood  looks like a command attempt, but no safe match → error tone
    ignore          probably not meant for FreeCAD (empty, or a long unrelated sentence) → silence

Commands are found by name (stage 1) and, if no name fits, by their help text (stage 1b).

Principle: rather do nothing than the wrong thing.
"""

from dataclasses import dataclass, field

from ttm_core.description import DescriptionIndex
from ttm_core.languages import FILLER_WORDS, STOP_WORDS
from ttm_core.matching import command_words, phrase_score
from ttm_core.phonetics import PHONETICS

# Higher levels win over equally good matches in lower levels (DESIGN.md 6.2).
LEVEL_BONUS = {"dialog": 0.03, "edit": 0.02, "workbench": 0.01, "global": 0.0}

# A name matching less than this share of the sentence's meaningful words gives way to a clear
# result from the help texts: in "Extrudiere das und ziehe es vom Körper ab" the name
# "extrudieren" (Pad) explains one word of four, the help text of Pocket all of them.
NAME_EXPLAINS = 0.5


@dataclass
class Decision:
    kind: str                      # "execute", "not_understood" or "ignore"
    command: str = None
    score: float = 0.0
    level: str = None
    reason: str = None             # for not_understood / ignore
    via: str = None                # "name" or "description": how the command was found
    alternatives: list = field(default_factory=list)   # [(command, score)], best first


def decide(text, candidates, language=None, threshold=0.75, margin=0.05,
           ignore_below=0.55, ignore_min_words=4,
           desc_threshold=0.7, desc_margin=0.15, desc_min_known=2):
    """
    threshold         minimal score for executing
    margin            a second command on the same level closer than this makes it ambiguous
    ignore_below      sentences with at least ignore_min_words words scoring below this are
                      treated as talk not meant for FreeCAD: no error tone
    desc_threshold    minimal coverage of the sentence by a help text
    desc_margin       lead a help text needs over the second best; help texts of related
                      commands are much alike ("Vertiefung" and "Aufpolsterung")
    desc_min_known    words of the sentence that must occur in help texts at all
    """
    words = command_words(text, language)
    if not words:
        return Decision("ignore", reason="empty")
    fillers = FILLER_WORDS.get(language, set())
    if fillers and all(w in fillers for w in words):
        return Decision("ignore", reason="filler")
    phonetic = PHONETICS.get(language)
    stop = STOP_WORDS.get(language, frozenset())

    best_per_command = {}
    for c in candidates:
        score, size = max(((phrase_score(words, pw, phonetic, stop), len(pw))
                           for pw in (command_words(p, language) for p in c["phrases"])),
                          default=(0.0, 0))
        ranked = (score + LEVEL_BONUS.get(c["level"], 0.0), score, c, size)
        if c["id"] not in best_per_command or ranked[:2] > best_per_command[c["id"]][:2]:
            best_per_command[c["id"]] = ranked
    if not best_per_command:
        return Decision("ignore", reason="no_candidates")

    ranking = sorted(best_per_command.values(), key=lambda r: r[:2], reverse=True)
    alternatives = [(c["id"], round(score, 3)) for _, score, c, _ in ranking[:3]]
    adjusted, score, best, size = ranking[0]
    result = dict(command=best["id"], score=round(score, 3), level=best["level"],
                  alternatives=alternatives, via="name")

    if score < threshold:
        by_description = _decide_by_description(text, candidates, language,
                                                desc_threshold, desc_margin, desc_min_known)
        if by_description is not None:
            return by_description
        if score < ignore_below and len(words) >= ignore_min_words:
            return Decision("ignore", reason="unrelated", **result)
        return Decision("not_understood", reason="no_match", **result)
    meaningful = [w for w in words if w not in stop] or words
    if min(size, len(meaningful)) / len(meaningful) < NAME_EXPLAINS:
        by_description = _decide_by_description(text, candidates, language,
                                                desc_threshold, desc_margin, desc_min_known)
        if by_description is not None and by_description.reason != "ambiguous":
            return by_description
    if len(ranking) > 1:
        adjusted2, score2, second, _ = ranking[1]
        if score2 >= threshold and second["level"] == best["level"] and adjusted - adjusted2 < margin:
            return Decision("not_understood", reason="ambiguous", **result)
    if not best["active"]:
        return Decision("not_understood", reason="inactive", **result)
    return Decision("execute", **result)


def _decide_by_description(text, candidates, language, threshold, margin, min_known):
    """Decision from the help texts, or None if they don't point anywhere."""
    by_id = {c["id"]: c for c in candidates if c.get("description")}
    if not by_id:
        return None
    index = DescriptionIndex({cmd: c["description"] for cmd, c in by_id.items()}, language)
    if index.known_terms(text) < min_known:
        return None
    ranking = index.ranking(text)
    cmd, score = ranking[0]
    if score < threshold:
        return None
    best = by_id[cmd]
    result = dict(command=cmd, score=score, level=best["level"], alternatives=ranking[:3],
                  via="description")
    if len(ranking) > 1 and score - ranking[1][1] < margin:
        return Decision("not_understood", reason="ambiguous", **result)
    if not best["active"]:
        return Decision("not_understood", reason="inactive", **result)
    return Decision("execute", **result)
