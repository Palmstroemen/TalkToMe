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
