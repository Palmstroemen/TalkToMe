"""Language specific word lists used by the matching.

Parameter words (numbers, units) belong to a command's parameters, so they are left
out when comparing a sentence with command phrases: "Tasche 5 mm" matches "Tasche" exactly.
"""

PARAMETER_WORDS = {
    "de": {
        "mm", "cm", "m", "millimeter", "zentimeter", "meter", "grad", "prozent", "komma", "halb",
        "null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn",
        "elf", "zwölf", "zwanzig", "dreißig", "vierzig", "fünfzig", "hundert", "tausend",
    },
}
