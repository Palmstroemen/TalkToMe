"""Stage 1 of the matching pipeline: fuzzy comparison with a vocabulary (DESIGN.md, section 7).

commands maps a command ID to the phrases that may trigger it:
    {"Sketcher_CreateCircle": ["Kreis"], ...}
"""

from difflib import SequenceMatcher

from ttm_core.text import normalize

PARTIAL = 0.95       # a phrase found inside a longer sentence scores a bit lower than an exact match


def phrase_score(text_words, phrase_words):
    """Similarity of a phrase with the best matching stretch of the text, 0..1."""
    n = len(phrase_words)
    if not text_words or not n:
        return 0.0
    phrase = " ".join(phrase_words)
    best = 0.0
    for i in range(max(1, len(text_words) - n + 1)):
        window = text_words[i:i + n]
        ratio = SequenceMatcher(None, " ".join(window), phrase).ratio()
        if len(window) < len(text_words):
            ratio *= PARTIAL
        best = max(best, ratio)
    return best


def match(text, commands, threshold=0.75):
    """Best matching command for text: (command_id, score), or (None, best score) below threshold.

    On equal scores the longer, more specific phrase wins.
    """
    words = normalize(text).split()
    if not words:
        return None, 0.0
    best_key, best_cmd = (0.0, 0), None
    for cmd, phrases in commands.items():
        for phrase in phrases:
            phrase_words = normalize(phrase).split()
            key = (phrase_score(words, phrase_words), len(phrase_words))
            if key > best_key:
                best_key, best_cmd = key, cmd
    score = round(best_key[0], 3)
    return (best_cmd, score) if score >= threshold else (None, score)
