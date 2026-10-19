"""Sentences of the speech output (DESIGN.md 10.1), from the language pack's speech.json.

Tones for the everyday, speech where a tone explains too little. Each sentence has a level:

    off         nothing is said, only tones
    important   e.g. "Das habe ich nicht verstanden.", "Meinst du A oder B?" (default)
    chatty      additionally confirmations: "Mache ich."
"""

from ttm_core.langpack import pack

LEVELS = ("off", "important", "chatty")


def phrase(kind, language, level, turn=0, **values):
    """The sentence to say for kind at the setting level, or None. Variants take turns by turn."""
    if not language or level not in LEVELS:
        return None
    message = pack(language).messages.get(kind)
    if not message or LEVELS.index(message.get("level", "chatty")) > LEVELS.index(level) or level == "off":
        return None
    texts = message.get("text") or []
    if not texts:
        return None
    try:
        return texts[turn % len(texts)].format(**values)
    except (KeyError, IndexError):
        return None
