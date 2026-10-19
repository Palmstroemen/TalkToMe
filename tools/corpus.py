"""Play the ground-truth corpus of a language pack (DESIGN.md 16.5) and show the result.

    python tools/corpus.py de                   summary and the cases that are not correct
    python tools/corpus.py de --with DIR        without and with a Talk to me folder (its changes
                                                to the pack and its learned forms): what gets
                                                worse, what better; exit code 1 if anything worse
    python tools/corpus.py de --coverage        how well each command is reached by voice, worst
                                                first (--context NAME: only that context's commands)

Exit code 1 if a case fails that is not marked "known", if a "known" case is correct now (remove
the mark), or with --with if anything got worse.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ttm_core import corpus  # noqa: E402

LIGHTS = {"red": "●red   ", "yellow": "●yellow", "green": "●green "}


def report(language, cases, verbose):
    results = corpus.run(language, cases)
    counts = corpus.summary(results)
    print("{}: {} cases – {}".format(language, len(results), ", ".join(
        "{} {}".format(n, outcome) for outcome, n in counts.items() if n)))
    unexpected = 0
    for r in sorted(results, key=lambda r: -corpus.RANK[r.outcome]):
        if r.outcome == "correct" and r.case.get("known"):
            unexpected += 1
            print("  fixed – remove \"known\": " + corpus.describe(r))
            continue
        if r.outcome == "correct" and not verbose:
            continue
        known = r.case.get("known")
        unexpected += r.outcome != "correct" and not known
        print(("  known   " if known else "  ") + corpus.describe(r))
        if known and r.case.get("note"):
            print("          note: " + r.case["note"])
    return 1 if unexpected else 0


def compare(language, cases, user_dir):
    before = corpus.run(language, cases)
    after = corpus.run(language, cases, user_dir=user_dir)
    worse, better = corpus.compare(before, after)
    print("{}: {} cases, without → with {}".format(language, len(cases), user_dir))
    for name, counts in (("without", corpus.summary(before)), ("with", corpus.summary(after))):
        print("  {:8} {}".format(name, ", ".join("{} {}".format(n, o) for o, n in counts.items() if n)))
    for title, pairs in (("worse", worse), ("better", better)):
        print("{} ({}):".format(title, len(pairs)))
        for a, b in pairs:
            print("  {} → {}".format(a.outcome, corpus.describe(b)))
    return 1 if worse else 0


def coverage(language, cases, context_name):
    rows = corpus.coverage(language, cases)
    if context_name:
        candidates = corpus.context(language, context_name)["context"]
        wanted = {c for items in candidates.get("toolbar_items", {}).values() for c in items}
        rows = {k: v for k, v in rows.items() if k in wanted}
    order = {"red": 0, "yellow": 1, "green": 2}
    print("{}: {} commands – {}".format(language, len(rows), ", ".join(
        "{} {}".format(sum(r.light == l for r in rows.values()), l) for l in order)))
    print("  light    sentences  distinct ok  margin  command (closest rivals)")
    for row in sorted(rows.values(), key=lambda r: (order[r.light], r.distinct_recognized, r.command)):
        margin = "{:.2f}".format(row.min_margin) if row.min_margin is not None else "  – "
        print("  {}  {:4}  {:4}/{:<4}  {:>6}  {} {}{}".format(
            LIGHTS[row.light], row.sentences, row.distinct_recognized, row.distinct, margin, row.command,
            "»{}«".format(row.label) if row.label else "",
            "  (" + ", ".join(row.rivals[:2]) + ")" if row.rivals else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("language")
    ap.add_argument("--with", dest="user_dir", help="a Talk to me folder with changes and learned forms")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--context", help="with --coverage: only the commands of this context")
    ap.add_argument("-v", "--verbose", action="store_true", help="also list the correct cases")
    args = ap.parse_args(argv)
    cases = corpus.cases(args.language)
    if not cases:
        print("no corpus for '{}'".format(args.language))
        return 1
    if args.coverage:
        return coverage(args.language, cases, args.context)
    if args.user_dir:
        return compare(args.language, cases, args.user_dir)
    return report(args.language, cases, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
