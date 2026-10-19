"""Check a language pack before a pull request (DESIGN.md 16.1).

    python tools/check_pack.py fr          errors, warnings and the corpus result
    python tools/check_pack.py --all       every pack in lang/

Exit code 1 if there is an error: a broken file, a pattern that does not compile, a corpus case
that fails and is not marked "known".
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ttm_core import langpack, packcheck  # noqa: E402

MARK = {"error": "✗ error  ", "warning": "! warning", "info": "  info   "}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("language", nargs="?")
    ap.add_argument("--all", action="store_true", help="check every pack")
    args = ap.parse_args(argv)
    if not args.all and not args.language:
        ap.error("name a language (e.g. fr) or use --all")
    failed = False
    for language in (langpack.languages() if args.all else [args.language]):
        result = packcheck.check(language)
        errors = sum(level == "error" for level, _ in result)
        warnings = sum(level == "warning" for level, _ in result)
        print("{}: {} error(s), {} warning(s)".format(language, errors, warnings))
        for level, message in result:
            print("  {} {}".format(MARK[level], message))
        failed = failed or errors > 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
