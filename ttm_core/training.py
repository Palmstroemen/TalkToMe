"""Training: learn how the speech recognition hears the user (DESIGN.md 8.7).

The user says what was meant a few times; what the recognizer made of it is stored as "heard"
forms of the command. They count when comparing, sound-alikes included, but are not given to
Whisper as hints: that would teach it to write "X-Upsilom" for everybody's "XY".
"""

from ttm_core.decision import decide
from ttm_core.matching import command_words

HEARD = "_heard"          # key in the user's vocabulary file: {command: [heard forms]}
PATTERNS = "_patterns"    # {command: [learned templates]}, e.g. "nenndas {label}"


def classify(text, target, candidates, language):
    """What a training recording means for target:

    ok        already understood as target
    learn     not understood (or ambiguous): store it as a heard form of target
    conflict  understood as another command: storing it would make that one unreachable
    empty     nothing recognized
    """
    if not command_words(text, language):
        return "empty"
    everything_active = [dict(c, active=True) for c in candidates]
    d = decide(text, everything_active, language)
    if d.kind == "execute":
        return "ok" if d.command == target else "conflict"
    return "learn"


def _add(phrases, new):
    known = {p.lower() for p in phrases}
    for p in new:
        if p and p.lower() not in known:
            known.add(p.lower())
            phrases.append(p)


def learn(custom, command, heard=(), typed=None, patterns=()):
    """Add heard forms, a typed sentence and learned patterns to the user's vocabulary data (in place)."""
    if heard:
        _add(custom.setdefault(HEARD, {}).setdefault(command, []), heard)
    if patterns:
        _add(custom.setdefault(PATTERNS, {}).setdefault(command, []), patterns)
    if typed:
        _add(custom.setdefault(command, []), [typed.strip()])
    return custom


def options(alternatives, candidates, min_score=0.6, limit=3):
    """Commands for the question menu after a not understood utterance: [(id, active)].

    Only likely ones (min_score), only those that exist in the situation; inactive ones are kept,
    the menu shows them greyed out with the reason.
    """
    active = {c["id"]: c.get("active", True) for c in candidates}
    result = []
    for command, score in alternatives:
        if score >= min_score and command in active and command not in [r[0] for r in result]:
            result.append((command, active[command]))
    return result[:limit]


def unlearn(custom, command, heard, patterns=()):
    """Remove heard forms and learned patterns of command again (a wrong assignment in training)."""
    for key, drop in ((HEARD, heard), (PATTERNS, patterns)):
        forms = custom.get(key, {}).get(command)
        if forms is None:
            continue
        drop = {d.lower() for d in drop}
        forms[:] = [f for f in forms if f.lower() not in drop]
        if not forms:
            del custom[key][command]
    return custom
