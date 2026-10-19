"""Language specific word lists used by the matching.

Parameter words (numbers, units) belong to a command's parameters, so they are left
out when comparing a sentence with command phrases: "Tasche 5 mm" matches "Tasche" exactly.
"""

# Words people say around commands ("Zeichne ein Rechteck ... und zwar von hier nach hier").
# A sentence made only of these is narration, not a command: it is ignored without error tone.
# They are NOT removed when scoring phrases, so "von vorne" still matches.
FILLER_WORDS = {
    "de": {
        "und", "zwar", "von", "nach", "bis", "hier", "da", "dort", "dahin", "hierhin", "so", "genau",
        "jetzt", "dann", "mal", "noch", "also", "eben", "halt", "ja", "nein", "nee", "gut", "naja",
        "bitte", "danke", "äh", "ähm", "hm", "hmm", "ach", "oh", "das", "die", "der", "es", "ist",
    },
}

PARAMETER_WORDS = {
    "de": {
        "mm", "cm", "m", "millimeter", "zentimeter", "meter", "grad", "prozent", "komma", "halb",
        "null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn",
        "elf", "zwölf", "zwanzig", "dreißig", "vierzig", "fünfzig", "hundert", "tausend",
    },
}

# Words that join clauses: "Extrudiere das und ziehe es ab" has two clauses.
CLAUSE_WORDS = {
    "de": {"und", "dann", "danach", "anschließend"},
}

# Particles of separable verbs, standing at the end of a clause: "zieht ... ab", "fügt ... hinzu".
PARTICLES = {
    "de": {"ab", "an", "auf", "aus", "ein", "fest", "herum", "hinzu", "mit", "um", "weg", "zu",
           "zurück", "zusammen"},
}

# Words without meaning for identifying a command, left out when comparing with help texts.
STOP_WORDS = {
    "de": FILLER_WORDS["de"] | PARTICLES["de"] | {
        "ein", "eine", "einen", "einem", "einer", "eines", "den", "dem", "des",
        "er", "sie", "ihn", "ihm", "ihr", "ihnen", "ich", "du", "wir", "man", "mir", "mich", "uns",
        "dies", "diese", "dieser", "dieses", "diesen", "diesem", "sein", "seine", "seinen",
        "in", "im", "ins", "am", "an", "auf", "aus", "bei", "beim", "für", "mit", "um", "vom",
        "zum", "zur", "über", "unter", "vor", "hinter", "neben", "zwischen", "durch", "gegen", "ohne",
        "oder", "aber", "wie", "wenn", "als", "auch", "nur", "nicht", "kein", "keine",
        "bin", "sind", "war", "wird", "werden", "wurde", "hat", "haben", "kann", "soll", "will",
        "möchte", "bitte", "mal", "doch", "einfach", "danach", "anschließend",
        "mach", "mache", "machen", "macht", "tu", "tue", "tun",       # say nothing about the command
    },
}
