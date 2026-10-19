"""Stage 1 of the matching pipeline: comparison with a vocabulary (DESIGN.md, section 7).

commands maps a command ID to the phrases that may trigger it:
    {"Sketcher_CreateCircle": ["Kreis"], ...}

A phrase is compared with every stretch of the sentence, by spelling (fuzzy) and, if the
language has a phonetic algorithm, by sound ("Richtig" sounds like "Rechteck").
"""

import re
from difflib import SequenceMatcher

from ttm_core.languages import PARAMETER_WORDS, STOP_WORDS
from ttm_core.phonetics import PHONETICS
from ttm_core.text import normalize

PARTIAL = 0.95       # a phrase found inside a longer sentence scores a bit lower than an exact match
SOUND = 0.9          # same sound, different spelling: good, but below an exact match
SHORT_CODE = 2       # sound codes this short ("Fase" = 38) only count if they make up the whole sentence

NUMBER = re.compile(r"^\d+([.,]\d+)?$")


def command_words(text, language=None):
    """Normalized words of a sentence without parameters (numbers, units)."""
    params = PARAMETER_WORDS.get(language, set())
    return [w for w in normalize(text).split() if not NUMBER.match(w) and w not in params]


def phrase_score(text_words, phrase_words, phonetic=None, stop=frozenset()):
    """Similarity of a phrase with the best matching stretch of the text, 0..1.

    Stretches made only of stop words are skipped inside longer sentences: "und" sounds like
    "Undo", "gut" looks like "Cut".
    """
    n = len(phrase_words)
    if not text_words or not n:
        return 0.0
    phrase = " ".join(phrase_words)
    phrase_codes = [phonetic(w) for w in phrase_words] if phonetic else None
    best = 0.0
    for i in range(max(1, len(text_words) - n + 1)):
        window = text_words[i:i + n]
        partial = len(window) < len(text_words)
        if partial and all(w in stop for w in window):
            continue
        score = SequenceMatcher(None, " ".join(window), phrase).ratio()
        if phrase_codes and all(phrase_codes) and len(window) == n:
            same_sound = [phonetic(w) for w in window] == phrase_codes
            too_short = partial and len("".join(phrase_codes)) <= SHORT_CODE
            if same_sound and not too_short:
                score = max(score, SOUND)
        if partial:
            score *= PARTIAL
        best = max(best, score)

    # Compound words: "Part Design" vs. "PartDesign", "Teil Konstruktion" vs. "Teilkonstruktion".
    # Compare without spaces, with windows one word shorter or longer than the phrase.
    compact = "".join(phrase_words)
    for size in (n - 1, n + 1):
        if not 1 <= size <= len(text_words):
            continue
        for i in range(len(text_words) - size + 1):
            window = text_words[i:i + size]
            if size < len(text_words) and all(w in stop for w in window):
                continue
            score = SequenceMatcher(None, "".join(window), compact).ratio()
            if size < len(text_words):
                score *= PARTIAL
            best = max(best, score)
    return best


def match(text, commands, threshold=0.75, language=None):
    """Best matching command for text: (command_id, score), or (None, best score) below threshold.

    On equal scores the longer, more specific phrase wins.
    """
    words = command_words(text, language)
    if not words:
        return None, 0.0
    phonetic = PHONETICS.get(language)
    stop = STOP_WORDS.get(language, frozenset())
    best_key, best_cmd = (0.0, 0), None
    for cmd, phrases in commands.items():
        for phrase in phrases:
            phrase_words = command_words(phrase, language)
            key = (phrase_score(words, phrase_words, phonetic, stop), len(phrase_words))
            if key > best_key:
                best_key, best_cmd = key, cmd
    score = round(best_key[0], 3)
    return (best_cmd, score) if score >= threshold else (None, score)


def hotwords(phrases, max_chars=400):
    """Phrases as a hint for the speech recognition: unique, in order, limited in length.

    Whisper's prompt is limited (about 220 tokens), and long prompts slow recognition down.
    Returns None if there is nothing to hint.
    """
    seen, parts, length = set(), [], 0
    for phrase in phrases:
        phrase = " ".join(phrase.split())
        key = phrase.lower()
        if not phrase or key in seen:
            continue
        extra = len(phrase) + (2 if parts else 0)
        if length + extra > max_chars:
            break
        seen.add(key)
        parts.append(phrase)
        length += extra
    return ", ".join(parts) or None
