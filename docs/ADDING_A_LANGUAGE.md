# Adding a language

This guide walks through adding French to Talk to me, from an empty folder to a pull request.
Most of it needs no programming: a language pack is a few JSON files, and a test corpus of
sentences. The same steps work for any language Whisper understands.

Contents:

1. [What a language pack is](#1-what-a-language-pack-is)
2. [What you get for free](#2-what-you-get-for-free)
3. [Step by step: French](#3-step-by-step-french)
4. [The corpus: sentences with their expected result](#4-the-corpus-sentences-with-their-expected-result)
5. [What happens automatically](#5-what-happens-automatically)
6. [Variants and dialects](#6-variants-and-dialects)
7. [Ways to help without writing a pack](#7-ways-to-help-without-writing-a-pack)
8. [Pull request checklist](#8-pull-request-checklist)

---

## 1. What a language pack is

Everything language specific lives in `lang/<code>/`. The code is a [BCP 47](https://www.rfc-editor.org/info/bcp47) tag: `fr`,
`es`, `pt-BR`, `de-AT`.

| File | What it holds | Needed? |
|---|---|---|
| `language.json` | word lists and tables, the names of the sound and stemming algorithms | yes |
| `vocab.json` | extra phrases for commands, beyond FreeCAD's own button texts | recommended |
| `patterns.json` | sentence patterns for commands with free text (renaming) and menu picks | recommended |
| `speech.json` | the sentences Talk to me speaks, and its default voice | recommended |
| `corpus.jsonl` | test sentences with their expected result (section 4) | yes, for a pull request |
| `contexts/*.json` | FreeCAD states the corpus is played in (section 4) | yes, for a pull request |

A short look at each, from the English pack:

**`language.json`**, word lists:

```json
{
  "name": "English",
  "phonetics": "metaphone",
  "stemmer": "english",
  "filler_words": ["a", "and", "now", "please", "the", "um", "well"],
  "statement_words": ["is", "are", "was", "looks", "think", "why", "how"],
  "clause_words": ["and", "then", "afterwards", "next"],
  "number_values": {"one": 1, "two": 2, "three": 3},
  "unit_factors": {"mm": 1, "cm": 10, "inch": 25.4},
  "value_names": {"width": 0, "length": 0, "height": 1}
}
```

| Key | Used for |
|---|---|
| `filler_words` | words said around commands; a sentence of only these is ignored ("so, um, well") |
| `statement_words` | statements, questions, opinions: a sentence of 3+ words with one of them is talk, never a command ("The circle **is** too big") |
| `stop_words`, `particles` | words without meaning for finding a command; particles end separable verbs (German "zieht … **ab**") |
| `clause_words` | split a sentence into steps ("pad it **and then** make a fillet") |
| `parameter_words` | numbers and units, left out when comparing with command names ("pocket 5 **mm**") |
| `number_values`, `article_numbers`, `negative_words` | spoken numbers ("twelve"), articles that are numbers too ("a"), "minus" |
| `value_names`, `unit_factors`, `angle_names`, `angle_units`, `radius_words` | values for a running tool: "width 50, height 30", "5 cm", "30 degrees", "radius 20" |
| `pick_words` | picking an entry of the question menu: "the second one" |
| `pattern_leading`, `pattern_trailing` | words around a sentence pattern ("**please** call it lid") |
| `phonetics`, `stemmer` | algorithms by name (section 3, step 6) |

**`vocab.json`**, phrases per FreeCAD command ID:

```json
{
  "PartDesign_Pad":     ["Pad", "extrude", "pull up"],
  "PartDesign_Chamfer": ["Chamfer", "bevel"],
  "ui:mic_off":         ["Mic off", "Stop listening", "Take a short break"]
}
```

Command IDs are the same in every language; FreeCAD shows them in Tools → Customize →
Commands. The `ui:` commands belong to Talk to me itself: `ui:mic_off`, `ui:train`, `ui:cancel`,
`ui:ok`, `ui:rename`, `ui:choose:<entry of a dialog list>`.

**`patterns.json`**, regular expressions matched against a whole clause, case-insensitive.
Allowed groups: `label` (a new name), `target` (the object named), `pick` (a menu entry).
Macros in braces are replaced first:

```json
{
  "macros":   {"pronoun": "(?:it|this|that)"},
  "patterns": [
    ["ui:rename", "(?:let's\\s+)?call\\s+{pronoun}\\s+(?P<label>.+)"],
    ["ui:rename", "rename\\s+(?:the\\s+)?(?P<target>.+?)\\s+to\\s+(?P<label>.+)"],
    ["ui:pick",   "(?:number\\s+|the\\s+)?(?P<pick>\\w+)(?:\\s+one)?"]
  ]
}
```

**`speech.json`**, what Talk to me says, and the voice:

```json
{
  "voice": "en_US-ljspeech-medium",
  "messages": {
    "ready":     {"level": "important", "text": ["I'm listening."]},
    "ambiguous": {"level": "important", "text": ["Do you mean {first} or {second}?"]},
    "done":      {"level": "chatty",    "text": ["Done.", "Okay."]}
  }
}
```

## 2. What you get for free

- **Command names and help texts:** Talk to me reads them from FreeCAD's own user interface, so
  they are already in French when FreeCAD runs in French (Edit → Preferences → General →
  Language). "Protrusion", "Congé", "Chanfrein" work without any entry in `vocab.json`. Run
  FreeCAD in the language you speak; English button texts are always compared too, by spelling.
- **Speech recognition:** Whisper is multilingual; the same model serves every language.
- **Speech output:** [Piper voices](https://huggingface.co/rhasspy/piper-voices) exist for many
  languages; name one in `speech.json`, it is downloaded on first use. Check the voice's license
  in its model card.
- **Commands from any workbench and add-on**, by their IDs.

So a pack mostly adds what FreeCAD cannot know: how people talk around commands, numbers and
units, and sentences for renaming.

## 3. Step by step: French

**Step 1 – the folder.** Create `lang/fr/language.json` with just a name:

```json
{"name": "Français"}
```

Run the check. It works already, and tells you what is missing:

```
$ python tools/check_pack.py fr
fr: 0 error(s), 7 warning(s)
    info    chain: fr
  ! warning missing compared to 'en': phonetics, stemmer, filler_words, parameter_words, clause_words, …
  ! warning no 'phonetics': words are compared by spelling only, not by sound
  ! warning no 'stemmer': help texts are compared word by word
  ! warning no 'voice' in speech.json: no speech output (see https://huggingface.co/rhasspy/piper-voices)
  ! warning speech messages missing compared to 'en': ambiguous, done, failed, inactive, …
    info    no translations/TalkToMe_fr.qm: the user interface stays English
  ! warning no corpus: add lang/fr/corpus.jsonl with sentences and the steps they must give
```

**Step 2 – word lists.** Use `lang/en/language.json` as a model and fill the lists in French.
Start with the ones that matter most:

```json
{
  "name": "Français",
  "filler_words":    ["et", "alors", "euh", "bon", "donc", "le", "la", "les", "un", "une", "maintenant"],
  "statement_words": ["est", "sont", "était", "pourquoi", "comment", "où", "pense", "crois"],
  "clause_words":    ["et", "puis", "ensuite"],
  "parameter_words": ["mm", "cm", "millimètres", "centimètres"],
  "number_values":   {"un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "dix": 10, "douze": 12},
  "unit_factors":    {"mm": 1, "millimètres": 1, "cm": 10, "centimètres": 10, "m": 1000},
  "value_names":     {"largeur": 0, "longueur": 0, "hauteur": 1}
}
```

Tips:

- **Fillers vs. statement words.** Fillers are noise around a command ("**alors**, un chanfrein");
  statement words mark sentences *about* the model ("le cercle **est** trop grand"). Both keep
  talk from triggering commands; the second list is the stronger one.
- Lists are lower case, single words.
- When in doubt, leave a word out and let the corpus show whether it is needed.

**Step 3 – phrases.** Add synonyms people use beyond FreeCAD's button texts:

```json
{
  "PartDesign_Pad":     ["extruder", "protrusion"],
  "PartDesign_Pocket":  ["poche", "enlever de la matière"],
  "PartDesign_Chamfer": ["chanfreiner", "casser l'arête"],
  "ui:mic_off":         ["micro coupé", "arrête d'écouter", "petite pause"],
  "ui:train":           ["entraînement", "ouvre l'entraînement"],
  "ui:cancel":          ["annuler", "stop"],
  "ui:ok":              ["OK", "valider", "terminé"]
}
```

**Step 4 – patterns.** At least renaming ("appelle-le couvercle") and picking a menu entry
("le deuxième"); see `lang/en/patterns.json` and `lang/de/patterns.json`. Test a pattern with
the corpus (section 4) rather than by eye.

**Step 5 – speech.** Copy `lang/en/speech.json`, translate the texts (keep the `{first}`,
`{second}` placeholders), and choose a voice, e.g. `"fr_FR-siwis-medium"`.

**Step 6 – sound and stems.** Two algorithms make recognition robust and are code, not data:

- `phonetics`: compares by sound, so a misheard "Phase" still finds "Fase". Available:
  `cologne` (German), `metaphone` (English). Without one, words are compared by spelling, which
  works, only less forgivingly.
- `stemmer`: lets "extrude", "extrudes", "extruded" count as one word when comparing with help
  texts. Available: `german`, `english`.

For a new language, leave them out first. Adding one is a Python contribution in
`ttm_core/phonetics.py` or `ttm_core/stemming.py` (a function word → code or word → stem, added
to `ALGORITHMS`); open an issue to discuss it.

**Step 7 – record contexts.** The corpus plays sentences in real FreeCAD states. Record them in
FreeCAD running in French:

1. Bring FreeCAD into the state: e.g. a new document with a body in PartDesign; or a sketch in
   edit; or the pad dialog open.
2. Macro → Macros… → choose `tools/record_context.py` from the Talk to me folder → Execute.
3. Give it a name (`fc114_partdesign`); it writes `lang/fr/contexts/fc114_partdesign.json`.

A context is the raw state: toolbars, button texts, help texts, what is active, the open
dialog. It holds no vocabulary, so the corpus always tests the pack as it is now. The German
and English packs have six contexts each; recording the same six is a good start.

**Step 8 – the corpus.** Write `lang/fr/corpus.jsonl` (next section), then:

```
$ python tools/check_pack.py fr
$ python tools/corpus.py fr --coverage --context fc114_partdesign
```

**Step 9 – the user interface (optional).** Translate the texts of the settings and training
pages with Qt Linguist; see "Translations of the user interface" in the README, with `fr`
instead of `de`.

**Step 10 – try it.** In FreeCAD: Edit → Preferences → Talk to me → language "Français",
microphone on, speak. Sentences that go wrong are the best new corpus cases.

## 4. The corpus: sentences with their expected result

`corpus.jsonl` has one case per line; `#` starts a comment:

```
# --- Commands by name
{"text": "Protrusion", "context": "fc114_partdesign", "expect": ["PartDesign_Pad"]}
{"text": "Fais un chanfrein", "context": "fc114_partdesign", "expect": ["PartDesign_Chamfer"]}

# --- Sequences and renaming
{"text": "Crée un nouveau corps et appelle-le socle", "context": "fc114_partdesign",
 "expect": ["PartDesign_Body", {"command": "ui:rename", "args": {"label": "Socle"}}]}

# --- Values while a tool runs
{"text": "largeur 50, hauteur 30", "context": "fc114_sketcher_tool",
 "expect": [{"command": "ui:values", "args": {"values": [[0, 50.0, "length"], [1, 30.0, "length"]]}}]}

# --- Talk: must not trigger anything
{"text": "Le cercle est un peu trop grand", "context": "fc114_sketcher", "expect": "ignore"}
{"text": "Tu peux me passer le café ?", "context": "fc114_partdesign", "expect": "ignore"}
```

(Each case is one line in the file; the sequence example is wrapped here for reading.)

| Field | Meaning |
|---|---|
| `text` | the sentence as the speech recognition writes it |
| `context` | a file name in `contexts/`, without `.json` |
| `expect` | the commands executed, in order; an entry may be `{"command": …, "args": {…}}`. Or `"ignore"` (talk, no reaction) or `"not_understood"` (nothing may be executed) |
| `known` | optional, `true`: a known weakness; it is reported but does not fail the tests |
| `note` | optional: why the case is there, or why it is known |
| `model` | optional: the speech model a misheard text came from (`"whisper-base"`) |

Each case is judged as **correct**, **unclear** (asks back), **missed** (silent),
**false_trigger** (reacted to talk) or **wrong** (executed something else, the worst).

A command that is recognized but not available right now ("Undo" in a new document) counts as
correct: Talk to me says "isn't possible right now", which is the right reaction.

What makes a good corpus:

- **Talk, a lot of it.** Sentences said while working, with technical words in them: "the hole
  is in the wrong place", "this edge is too sharp". They are the hardest part and the most
  valuable.
- **Real alternatives, not repetitions.** "Chanfrein" and "casser l'arête" are two ways to say
  it; "fais un chanfrein" and "Fais un chanfrein." are one.
- **Long, natural commands**: "il me faut un cercle ici".
- **Sentences as they were heard**, misspellings included, with `model`.

`python tools/corpus.py fr --coverage` shows how well each command is reached by voice: red
(no sentence recognized), yellow, green (5 different sentences recognized, each without
itself in the vocabulary and clearly ahead of the next command). It also names the commands
each one is confused with.

## 5. What happens automatically

- `python -m pytest tests` plays the corpus of every pack. A case that fails and is not marked
  `known` fails the tests; so does a `known` case that is correct now (remove the mark).
- `tools/check_pack.py` checks the files: valid JSON, lists are lists, patterns compile and use
  only the allowed groups, contexts of the corpus exist.
- A change to the code is tested against all packs, so a language nobody in the core team
  speaks stays intact.
- `python tools/corpus.py fr --with <folder>` compares the corpus without and with a user's
  Talk to me folder (its changed lists and the forms learned in training): what gets better,
  what worse. This is how shared corrections are checked before they go into a pack.

## 6. Variants and dialects

A variant inherits from its base and holds only what differs. `lang/fr-CA/language.json`:

```json
{"name": "Français (Canada)", "base": "fr", "+filler_words": ["là", "fait que"]}
```

Rules along the chain `fr` → `fr-CA` → the user's own changes:

- `language.json`: a value replaces; a table (`number_values`, …) is merged; a list replaces,
  `"+filler_words"` adds to the inherited list. `name` is not inherited.
- `vocab.json`, `patterns.json`: the variant's entries come first, the base's follow.
- `speech.json`: single messages and the voice replace the base's.
- The variant plays its base's corpus too, so it cannot break what works in the base.
- Without an official code, use a private-use tag: `de-x-saxon`.
- The speech recognition gets the base language (Whisper knows `fr`, not `fr-CA`).

The speech model writes standard language even for a dialect, as well as it can. So a variant
mostly collects *how the model hears* its speakers, which is why corpus cases from dialects
should name the `model`.

## 7. Ways to help without writing a pack

- **Corpus sentences** for an existing language, especially talk and real alternatives.
- **Contexts** of more workbenches and add-ons (section 3, step 7).
- **Reports** of sentences that went wrong: the issue templates ask for the sentence, what was
  heard (the training page shows it), what you meant and the FreeCAD state.
- **Your corrections**: what you taught Talk to me on the training page is in
  `<UserAppDataDir>/TalkToMe/custom.<language>.json`. Attach it to an issue; it is checked
  with `tools/corpus.py --with` before it goes into a pack.
- **Translations** of the user interface with Qt Linguist.

## 8. Pull request checklist

- [ ] `python tools/check_pack.py <code>` shows no error.
- [ ] `python -m pytest tests` passes.
- [ ] The corpus has commands, sequences, values and talk; weaknesses you could not fix are
      marked `known` with a `note`.
- [ ] Contexts were recorded in FreeCAD running in the pack's language; the FreeCAD version is
      in their file names (`fc114_…`).
- [ ] The voice's license allows its use.
- [ ] One language (or variant) per pull request.
