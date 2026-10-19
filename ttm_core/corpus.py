"""Ground-truth corpus: sentences with the steps they must produce (DESIGN.md 16.5).

    lang/<code>/corpus.jsonl        one case per line; "#" starts a comment line
    lang/<code>/contexts/<name>.json  raw FreeCAD contexts, recorded with tools/record_context.py

A case:
    {"text": "Mach eine Fase", "context": "fc114_partdesign", "expect": ["PartDesign_Chamfer"]}
    expect   ["cmd", ...] the executed steps in order (talk between them is skipped), an entry may
             be {"command": "ui:rename", "args": {"label": "Bodenplatte"}} (args must match);
             "ignore" (talk, no reaction) or "not_understood" (nothing may be executed); a last
             command that is recognized but not available in the context ("inactive") counts
    known    optional, true: a known weakness; reported, but no test failure
    model    optional: the speech recognition model a misheard text came from
    note     optional: why the case is there

The candidates are built from the context and the vocabulary of the pack under test, plus the
corrections in a user folder if one is given; so a proposal is judged by playing the corpus
without and with it (tools/corpus.py --with). A variant plays its base's cases too.
"""

import json
import os
from dataclasses import dataclass, field

from ttm_core import langpack
from ttm_core.context import from_snapshot
from ttm_core.decision import Decision
from ttm_core.languages import STOP_WORDS
from ttm_core.matching import command_words
from ttm_core.vocabulary import clean_label
from ttm_core.sequence import plan_utterance
from ttm_core.training import vocabulary

# Outcomes by harm: executing the wrong command is worst, then reacting to talk.
RANK = {"correct": 0, "unclear": 1, "missed": 2, "false_trigger": 3, "wrong": 4}
NOTHING = ("ignore", "not_understood")


@dataclass
class Result:
    case: dict
    outcome: str
    steps: list = field(default_factory=list)       # [(kind, command, args, span)]


def read_cases(path, source):
    cases = []
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                case = json.loads(line)
            except ValueError as e:
                raise ValueError("{}, line {}: {}".format(path, number, e))
            case.update(line=number, source=source)
            cases.append(case)
    return cases


def cases(language):
    """The cases of language and of the packs it inherits from."""
    result = []
    for code in langpack.chain(language):
        path = os.path.join(langpack.LANG_DIR, code, "corpus.jsonl")
        if os.path.isfile(path):
            result += read_cases(path, code)
    return result


def context(language, name):
    """A recorded context; a variant uses its base's."""
    for code in reversed(langpack.chain(language)):
        path = os.path.join(langpack.LANG_DIR, code, "contexts", name + ".json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise KeyError("no context '{}' for {}".format(name, language))


def _custom(user_dir, language):
    if not user_dir:
        return {}
    try:
        with open(os.path.join(user_dir, "custom.{}.json".format(language)), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _matches(expected, decision):
    if isinstance(expected, str):
        return decision.command == expected
    if decision.command != expected.get("command"):
        return False
    args = decision.args or {}
    return all(args.get(k) == v for k, v in expected.get("args", {}).items())


def judge(expect, steps):
    """Outcome of one case: steps are [(Decision, span)] as plan_utterance returns them."""
    # A command recognized but not available now ("Rückgängig" in a new document) counts as
    # recognized: the service says so, which is the right reaction.
    inactive = [d for d, _ in steps if d.kind == "not_understood" and d.reason == "inactive" and d.alternatives]
    executed = [d for d, _ in steps if d.kind == "execute"]
    unclear = any(d.kind == "not_understood" for d, _ in steps)
    if expect in NOTHING:
        if executed:
            return "false_trigger"
        return "unclear" if expect == "ignore" and unclear else "correct"
    for i, wanted in enumerate(expect):
        if i >= len(executed):
            if i == len(executed) == len(expect) - 1 and inactive and \
                    _matches(wanted, Decision("execute", inactive[0].alternatives[0][0])):
                return "correct"
            return "unclear" if unclear else "missed"
        if not _matches(wanted, executed[i]):
            return "wrong"
    return "wrong" if len(executed) > len(expect) else "correct"


class _Setup:
    """The pack's vocabulary (and a user's corrections) and the contexts built with it."""

    def __init__(self, language, user_dir=None):
        self.language = language
        self.vocab, self.heard, self.patterns = vocabulary(langpack.pack(language).vocab, _custom(user_dir, language))
        self.built = {}

    def context(self, name):
        """(candidates, tool running)"""
        if name not in self.built:
            data = context(self.language, name)
            self.built[name] = (from_snapshot(data["context"], self.vocab, self.heard, self.language), bool(data.get("tool_running")))
        return self.built[name]

    def plan(self, text, candidates, tool_running):
        return plan_utterance(text, candidates, self.language, self.patterns, tool_running)


def run(language, case_list, user_dir=None):
    """Play the cases; user_dir: a Talk to me folder whose changes and corrections are used."""
    langpack.configure(user_dir)
    try:
        setup, results = _Setup(language, user_dir), []
        for case in case_list:
            candidates, tool_running = setup.context(case["context"])
            steps = setup.plan(case["text"], candidates, tool_running)
            results.append(Result(case, judge(case["expect"], steps),
                                  [(d.kind, d.command, d.args, span) for d, span in steps]))
        return results
    finally:
        langpack.configure(None)


# --- coverage: how well each command is reached by voice (DESIGN.md 16.7) ------------------------

GREEN_SENTENCES = 5        # distinct sentences recognized ...
GREEN_MARGIN = 0.1         # ... each with this distance to the closest other command


@dataclass
class Coverage:
    command: str
    label: str = ""
    sentences: int = 0          # cases with this command as their only step
    distinct: int = 0           # of them with different meaningful words
    recognized: int = 0         # recognized without themselves in the vocabulary
    distinct_recognized: int = 0
    min_margin: float = None    # smallest distance to the closest other command
    rivals: list = field(default_factory=list)      # the closest other commands, most often first
    light: str = "red"


def light(distinct_recognized, min_margin):
    if distinct_recognized >= GREEN_SENTENCES and min_margin is not None and min_margin >= GREEN_MARGIN:
        return "green"
    return "yellow" if distinct_recognized else "red"


def _without(candidates, command, text):
    """The candidates with text removed from command's phrases and heard forms. FreeCAD's own
    name stays: a sentence is to prove more than the name and the help text."""
    gone = clean_label(text).lower()
    result = []
    for c in candidates:
        if c["id"] == command:
            name = (c.get("label") or "").lower()
            c = dict(c, phrases=[p for p in c["phrases"] if p.lower() != gone or p.lower() == name],
                     heard=[h for h in c.get("heard", []) if clean_label(h).lower() != gone])
        result.append(c)
    return result


def _margin(decision, command):
    """(score of command minus the best other's, the best other command)"""
    scores = dict(decision.alternatives)
    others = [(cmd, score) for cmd, score in decision.alternatives if cmd != command]
    if not others:
        return scores.get(command, 0.0), None
    return scores.get(command, 0.0) - others[0][1], others[0][0]


def coverage(language, case_list, user_dir=None):
    """{command: Coverage} for the cases with one plain command, and every command of their
    contexts; commands without sentences are red."""
    langpack.configure(user_dir)
    try:
        setup, rows, rivals, words = _Setup(language, user_dir), {}, {}, {}
        stop = STOP_WORDS.get(language, frozenset())
        for case in case_list:
            candidates, tool_running = setup.context(case["context"])
            for c in candidates:
                rows.setdefault(c["id"], Coverage(c["id"], c.get("label", "")))
            expect = case["expect"]
            if not (isinstance(expect, list) and len(expect) == 1 and isinstance(expect[0], str)):
                continue
            command = expect[0]
            row = rows.setdefault(command, Coverage(command))
            row.sentences += 1
            meaning = frozenset(w for w in command_words(case["text"], language) if w not in stop)
            seen = words.setdefault(command, {})
            steps = setup.plan(case["text"], _without(candidates, command, case["text"]), tool_running)
            ok = judge(expect, steps) == "correct"
            seen[meaning] = seen.get(meaning, False) or ok
            row.recognized += ok
            first = steps[0][0]
            margin, rival = _margin(first, command)
            if rival is not None:
                rivals.setdefault(command, {}).setdefault(rival, 0)
                rivals[command][rival] += 1
            if ok:
                row.min_margin = margin if row.min_margin is None else min(row.min_margin, margin)
        for command, row in rows.items():
            seen = words.get(command, {})
            row.distinct, row.distinct_recognized = len(seen), sum(seen.values())
            counted = rivals.get(command, {})
            row.rivals = sorted(counted, key=lambda r: -counted[r])
            row.light = light(row.distinct_recognized, row.min_margin)
        return rows
    finally:
        langpack.configure(None)


def summary(results):
    counts = {outcome: 0 for outcome in RANK}
    for r in results:
        counts[r.outcome] += 1
    return counts


def by_command(results):
    """{expected command: {outcome: count}}; "(talk)" for cases expecting no reaction."""
    table = {}
    for r in results:
        expect = r.case["expect"]
        names = ["(talk)"] if expect in NOTHING else \
            [e if isinstance(e, str) else e.get("command") for e in expect]
        for name in names:
            row = table.setdefault(name, {outcome: 0 for outcome in RANK})
            row[r.outcome] += 1
    return table


def compare(before, after):
    """(worse, better): [(before, after)] of the cases whose outcome changed, by harm."""
    worse, better = [], []
    for a, b in zip(before, after):
        if RANK[b.outcome] > RANK[a.outcome]:
            worse.append((a, b))
        elif RANK[b.outcome] < RANK[a.outcome]:
            better.append((a, b))
    return worse, better


def describe(result):
    """One line for a report."""
    got = "; ".join("{} {}{}".format(kind, command or "", " " + json.dumps(args, ensure_ascii=False) if args else "")
                    for kind, command, args, _ in result.steps) or "nothing"
    return "{}:{} [{}] »{}« ({}) expected {} – got {}".format(
        result.case["source"], result.case["line"], result.outcome, result.case["text"],
        result.case["context"], json.dumps(result.case["expect"], ensure_ascii=False), got)
