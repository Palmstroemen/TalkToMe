# Talk to me

Local, multilingual voice control for FreeCAD 1.x. Status: **Phase 1** (single commands).
Design: see [DESIGN.md](DESIGN.md).

The microphone button listens continuously while switched on. Spoken commands of the current
context ("Rechteck", "Schließe den Sketch", "Rückansicht", "Wechsle zu Part Design", "Abbrechen")
are executed; the result shows in the status bar. Set the parameter `DryRun` to only show what
would be executed.

## Setup (Linux)

```bash
sudo apt install libportaudio2                       # audio library for sounddevice
python3 -m venv service/.venv
service/.venv/bin/pip install -r service/requirements.txt pytest
```

The first start downloads the speech model (`base`: ~150 MB, `small`: ~500 MB) to `~/.cache/huggingface`
and the voice of the speech output (~60 MB) to `~/.cache/talktome/voices`. The default voices are
free: Thorsten (German, CC0) and LJSpeech (English, public domain). Any other Piper voice works
too (`Voice` parameter); check its license yourself.

## Try it outside FreeCAD

```bash
service/.venv/bin/python tools/try_talktome.py               # microphone on, Ctrl+C to stop
service/.venv/bin/python tools/try_talktome.py --model small
```

Every recognized sentence is printed with its latency and the service's decision, using the
vocabulary in `lang/de/vocab.json` (edit it to add your own phrases). You hear a confirmation tone
when a command was recognized and an error tone when it was close but not clear.

## Measure models

```bash
service/.venv/bin/python tools/measure_stt.py record --out samples/de     # record your voice
service/.venv/bin/python tools/measure_stt.py bench --samples samples/de --models tiny,base,small -v
```

## Which FreeCAD?

FreeCAD **1.x** is the target; 0.19 works as far as tested, but without newer sketcher features.

| Installation | Works with Talk to me? |
|---|---|
| **AppImage** from [FreeCAD's releases](https://github.com/FreeCAD/FreeCAD/releases) | **Yes, recommended.** Runs directly on the system, so it can start the speech service and use the microphone. |
| Flatpak, Snap | **Not yet.** FreeCAD runs in a sandbox: the service's venv points to the system's Python, which doesn't exist inside the sandbox, and microphone access is restricted. |
| `apt install freecad` | Works, but Debian/Ubuntu/Mint LTS releases ship an old version (Ubuntu 22.04 / Mint 21: FreeCAD 0.19). |

## Use in FreeCAD

Link the repository into FreeCAD's Mod folder and restart FreeCAD. The folder differs between
installations; FreeCAD's Python console shows it with `App.getUserAppDataDir()` (append `Mod`):

```bash
ln -s ~/Development/TalkToMe "<UserAppDataDir>/Mod/TalkToMe"
```

A toolbar "Talk to me" with a microphone button appears in every workbench. To give it a
keyboard shortcut (or a foot pedal key), assign one to the command "Talk to me" in
Tools → Customize → Keyboard. The microphone key of a laptop keyboard mutes the microphone in
the system; the button then turns orange.
While a sketcher tool runs, say its values: after the first corner of a rectangle "50 mal 30"
or "Breite 50, Höhe 30", for a line "40 mm und 30 Grad", for a circle "Radius 20". Said with
the command ("Zeichne ein Rechteck 50 mal 30"), they wait for your first click. The same goes
for PartDesign dialogs: "Aufpolsterung 12 mm", "Verrundung Radius 3", "Fase 2"; the dialog stays
open, confirm with "OK".

When something is not clear, a small menu next to the mouse pointer offers the likely commands;
pick one by mouse or by voice ("die zweite"). The choice is executed and remembered: next time
the same mishearing is understood. Say "Lass uns das mal trainieren" ("Let's train that"), pick
"None of these – train…" in the menu or press "Training…" in the settings to open a page to teach
it on purpose: pick what you meant, say it three times. Learned forms are stored in
`<UserAppDataDir>/TalkToMe/custom.<language>.json`. The vocabulary editor (button "Vocabulary…"
on the training page and in the settings) shows them by command: delete them, or move a form
learned for the wrong command to the right one.

Settings: Edit → Preferences → Talk to me (language, microphone, volume, model, GPU/CPU, question
menu, speech output and voice, word lists of the language, training). Changes the speech service
needs restart it. The page writes these parameters (`BaseApp/Preferences/Mod/TalkToMe`):

| Parameter | Default | Meaning |
|---|---|---|
| `Language` | `de` | Spoken language: `de` or `en` (a folder in `lang/`) |
| `Microphone` | system default | Input device name |
| `Volume` | `40` | Volume of tones and voice in percent |
| `Model` | by hardware | `tiny`, `base`, `small`, ... |
| `Device` | `auto` | `auto`, `cuda`, `cpu` |
| `ServicePython` | `service/.venv/bin/python` | Python of the speech service |
| `DryRun` | `false` | Only show recognized commands, don't execute them |
| `AskMenu` | `true` | Question menu next to the mouse pointer when not sure |
| `Speech` | `important` | Speech output: `off` (tones only), `important` (not understood, questions, training), `chatty` (also "Mache ich.") |
| `Voice` | language pack's voice | Piper voice name (downloaded to `~/.cache/talktome/voices` on first use) or path to an `.onnx` file |

## Languages

Everything language specific of the recognition is in a language pack, `lang/<code>/`:

| File | Content |
|---|---|
| `language.json` | word lists (fillers, stop words, number and unit words, clause words, verb particles), names of the phonetic and stemming algorithm |
| `patterns.json` | sentence patterns for commands with free text, e.g. renaming |
| `vocab.json` | synonyms for commands |

Packs exist for German and English. Misheard words that sound like a command still find it:
German compares by Cologne phonetics ("Richtig" ≈ "Rechteck"), English by Metaphone
("Pat" ≈ "Pad"); the settings page explains this for the chosen language. Your own changes go to the same files in
`<UserAppDataDir>/TalkToMe/lang/<code>/`: a list there replaces the pack's list, patterns there
come first. A new language starts with a copy of `lang/en/`; without a phonetic algorithm,
words are compared by spelling only.

## Translations of the user interface

The user interface follows FreeCAD's language (Edit → Preferences → General), independent of the
spoken language. Texts are marked with `translate("TalkToMe", ...)`; translations live in
`translations/TalkToMe_<language>.ts` and are compiled to `.qm` files, which FreeCAD loads.
With PySide6's tools (`pip install pyside6`):

```bash
pyside6-lupdate talktome/*.py -source-language en -target-language de -ts translations/TalkToMe_de.ts -no-obsolete
# translate the new texts, e.g. with Qt Linguist (pyside6-linguist translations/TalkToMe_de.ts)
pyside6-lrelease translations/TalkToMe_de.ts -qm translations/TalkToMe_de.qm
```

A new language: the same with its code instead of `de`.

## Tests

```bash
service/.venv/bin/python -m pytest tests
```

## License

LGPL-2.1-or-later, see [LICENSE](LICENSE).
