"""Find the next step of a spoken command sequence (DESIGN.md 7, sequences).

"Wechsle zu Part Design, erstelle einen Körper" becomes two steps. They are decided one after
the other, each in the context left by the step before: the workbench switch brings the
commands of Part Design.

A command may stretch over several clauses ("Extrudiere das und ziehe es vom Körper ab"), so
the first one to max_span clauses are tried together; the span explaining the most words wins.
"""

from ttm_core.clauses import split_clauses
from ttm_core.decision import Decision, decide, explains
from ttm_core.matching import command_words
from ttm_core.params import parse
from ttm_core.values import parse_values

# Steps that change the candidates; what follows them is decided in the new context.
CONTEXT_CHANGING = ("workbench:",)

# Commands that replace everything else said with them: "Ok, kurze Pause" must not press OK.
EXCLUSIVE = ("ui:mic_off",)

# Values for a running tool: "50 mal 30", "Höhe 30" (DESIGN.md 6.5).
VALUES = "ui:values"


def _join(clauses):
    return ", ".join(clauses)


def next_step(clauses, candidates, language=None, max_span=3, patterns=None, **decide_args):
    """(Decision, number of clauses it consumes) for the start of clauses.

    A longer span only counts if every clause is part of the command: in "Klaus, Speichern"
    the span finds Save, but so does "Speichern" alone; in "erstelle einen Körper, den nennen wir
    Bodenplatte" the second clause explains nothing more about the body.
    """
    pattern = parse(clauses[0], language, patterns)
    if pattern is not None:                    # a command with free text: one clause, no rivals
        command, args = pattern
        return Decision("execute", command, score=1.0, level="global", via="pattern",
                        words=len(command_words(clauses[0], language)), args=args), 1
    by_id = {c["id"]: c for c in candidates}
    best = None
    for n in range(1, min(max_span, len(clauses)) + 1):
        d = decide(_join(clauses[:n]), candidates, language, **decide_args)
        if n == 1 and d.kind == "execute" and d.command.startswith(CONTEXT_CHANGING):
            return d, 1
        if d.kind != "execute" or (best is not None and d.words <= best[0].words):
            continue
        if n > 1:
            rest = decide(_join(clauses[1:n]), candidates, language, **decide_args)
            if rest.kind == "execute" and rest.command == d.command and rest.words >= d.words:
                continue
            candidate = by_id[d.command]
            if explains(_join(clauses[:n]), candidate, language) <= explains(_join(clauses[:n - 1]), candidate, language):
                continue
        best = (d, n)
    if best is not None:
        return best
    return decide(clauses[0], candidates, language, **decide_args), 1


# --- a whole utterance ------------------------------------------------------------------------
# The service decides step by step, each step in the context the step before left; the corpus
# (DESIGN.md 16.5) plays a whole utterance in one context. Both use these functions.

def start_utterance(text, candidates, language=None, patterns=None, tool_running=False):
    """(clauses to decide, None) or ([], the ignore decision) when the whole is talk."""
    pending = split_clauses(text, language)
    whole = decide(text, candidates, language)
    has_pattern = any(parse(c, language, patterns) for c in pending)
    values = tool_running and parse_values(text, language)
    if whole.kind == "ignore" and not has_pattern and not values:   # its clauses alone would look like short attempts
        return [], whole
    if whole.kind == "execute" and whole.command in EXCLUSIVE:
        return [text], None                    # one step, decided as a whole
    return pending, None


def values_step(clause, language=None, tool_running=False):
    """A step with values for the running tool, or None."""
    if not tool_running:
        return None
    values = parse_values(clause, language)
    if not values:
        return None
    return Decision("execute", VALUES, score=1.0, level="tool", via="values",
                    args={"values": [list(v) for v in values]})


def step(pending, candidates, language=None, patterns=None, tool_running=False):
    """(Decision, number of clauses) for the start of pending: a command name wins; otherwise
    numbers fill the running tool."""
    d, n = next_step(pending, candidates, language, patterns=patterns)
    if d.kind != "execute":
        values = values_step(pending[0], language, tool_running)
        if values is not None:
            return values, 1
    return d, n


def plan_utterance(text, candidates, language=None, patterns=None, tool_running=False):
    """[(Decision, span)] of an utterance, all decided in one context. Ends after an unclear
    clause, like the service does."""
    pending, ignored = start_utterance(text, candidates, language, patterns, tool_running)
    if ignored is not None:
        return [(ignored, text)]
    steps = []
    while pending:
        d, n = step(pending, candidates, language, patterns, tool_running)
        steps.append((d, _join(pending[:n])))
        pending = pending[n:]
        if d.kind == "not_understood":
            break
    return steps
