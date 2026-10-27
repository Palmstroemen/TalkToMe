# SPDX-License-Identifier: LGPL-2.1-or-later
"""Word error rate for measuring the speech recognition."""

from ttm_core.text import normalize  # noqa: F401  (re-exported for callers of metrics)


def wer(ref, hyp):
    """Word error rate of hyp against ref (both normalized first)."""
    r, h = normalize(ref).split(), normalize(hyp).split()
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return prev[-1] / len(r)


def best_wer(refs, hyp):
    """Lowest WER against any of several accepted references."""
    return min(wer(r, hyp) for r in refs)
