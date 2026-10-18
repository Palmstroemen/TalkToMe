"""Phrases for commands, from button texts and vocabulary files (DESIGN.md, section 8)."""

import re


def clean_label(text):
    """A button or menu text as a spoken phrase: "Save &As..." -> "Save As"."""
    text = text.replace("&&", "\0").replace("&", "").replace("\0", "&")
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text)          # trailing shortcut hint "(V, F)"
    text = text.strip().rstrip(".…").strip()
    return " ".join(text.split())


def merge_phrases(*sources):
    """Merge phrase lists in priority order: cleaned, without empties and duplicates (ignoring case)."""
    seen, phrases = set(), []
    for source in sources:
        for raw in source or []:
            phrase = clean_label(raw)
            if phrase and phrase.lower() not in seen:
                seen.add(phrase.lower())
                phrases.append(phrase)
    return phrases
