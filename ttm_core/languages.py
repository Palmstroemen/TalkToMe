"""Language specific word lists used by the matching, read from the language packs (lang/<code>/).

Each name is a view language → value, e.g. FILLER_WORDS.get("de", set()).

FILLER_WORDS      said around commands ("und zwar von hier nach hier"); a sentence of only
                  these is narration. NOT removed when scoring phrases, so "von vorne" matches.
PARAMETER_WORDS   numbers and units, left out when comparing with phrases ("Tasche 5 mm")
CLAUSE_WORDS      join clauses ("Extrudiere das und ziehe es ab")
PARTICLES         of separable verbs at the end of a clause ("zieht ... ab")
STATEMENT_WORDS   mark statements, questions and opinions ("Der Kreis ist zu groß", "Wie spät
                  ist es"): such a sentence is talk, however much it names a command
STOP_WORDS        without meaning for identifying a command (fillers and particles included)
NUMBER_VALUES     number words as values ("Körper zwei" → "Körper002")
"""

from ttm_core.langpack import View

FILLER_WORDS = View("filler_words")
PARAMETER_WORDS = View("parameter_words")
CLAUSE_WORDS = View("clause_words")
PARTICLES = View("particles")
STOP_WORDS = View("stop_words")
STATEMENT_WORDS = View("statement_words")
NUMBER_VALUES = View("number_values")
