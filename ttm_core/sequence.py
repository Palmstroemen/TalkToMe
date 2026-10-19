"""Find the next step of a spoken command sequence (DESIGN.md 7, sequences).

"Wechsle zu Part Design, erstelle einen Körper" becomes two steps. They are decided one after
the other, each in the context left by the step before: the workbench switch brings the
commands of Part Design.

A command may stretch over several clauses ("Extrudiere das und ziehe es vom Körper ab"), so
the first one to max_span clauses are tried together; the span explaining the most words wins.
"""

from ttm_core.decision import Decision, decide, explains
from ttm_core.matching import command_words
from ttm_core.params import parse

# Steps that change the candidates; what follows them is decided in the new context.
CONTEXT_CHANGING = ("workbench:",)

# Commands that replace everything else said with them: "Ok, kurze Pause" must not press OK.
EXCLUSIVE = ("ui:mic_off",)


def _join(clauses):
    return ", ".join(clauses)


def next_step(clauses, candidates, language=None, max_span=3, **decide_args):
    """(Decision, number of clauses it consumes) for the start of clauses.

    A longer span only counts if every clause is part of the command: in "Klaus, Speichern"
    the span finds Save, but so does "Speichern" alone; in "erstelle einen Körper, den nennen wir
    Bodenplatte" the second clause explains nothing more about the body.
    """
    pattern = parse(clauses[0], language)
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
