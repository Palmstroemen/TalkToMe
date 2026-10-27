# Talk to me

[![Tests](https://github.com/Palmstroemen/TalkToMe/actions/workflows/test.yml/badge.svg)](https://github.com/Palmstroemen/TalkToMe/actions/workflows/test.yml)

Local, multilingual voice control for FreeCAD 1.x. Spoken commands run FreeCAD's own commands;
nothing is generated, and speech is recognized on your computer. Design: see [DESIGN.md](DESIGN.md).

**Status: beta, looking for testers.** Tested on Linux with the FreeCAD 1.1.4 AppImage, without a GPU,
in German and English. Windows and macOS are untested.

The microphone button listens continuously while switched on. Spoken commands of the current
context ("Rechteck", "Schließe den Sketch", "Rückansicht", "Wechsle zu Part Design", "Abbrechen")
are executed; the result shows in the status bar. What works:

- commands of the current workbench, edit mode and dialog, by their name, a synonym or a description
  of what they do ("Extrudiere das und ziehe es vom Körper ab" → Pocket)
- several commands in one sentence ("Wechsle zu Part Design, erstelle einen Körper und dann eine Skizze")
- values for sketcher tools and PartDesign dialogs ("Rechteck 50 mal 30", "Aufpolsterung 12 mm"),
  the plane of a new sketch ("in der XY-Ebene"), renaming ("Den nennen wir Bodenplatte")
- talk is ignored ("Der Kreis ist zu groß"); when not sure, a menu next to the mouse pointer asks
- training of how the speech recognition hears you, a vocabulary editor, speech output, settings
- languages: German, English

Not yet: dialogs of other workbenches than PartDesign, push-to-talk, a level meter for the microphone.

## Install

You need a Python 3.10 or newer on your system (not FreeCAD's): the speech service runs in an
environment of its own. On Debian, Ubuntu and Mint:

```bash
sudo apt install python3-venv libportaudio2
```

1. **Add the addon.** Until it is in FreeCAD's addon index: Edit → Preferences → Addon Manager →
   Custom repositories, add `https://github.com/Palmstroemen/TalkToMe` with branch `main`. Then
   Tools → Addon manager, find "Talk to me", install it and restart FreeCAD.
2. **Install the speech service.** Press the microphone button in the toolbar "Talk to me", or
   Edit → Preferences → Talk to me → General → Install…. The dialog says what it downloads, then
   creates the environment and installs the packages (a few minutes).
3. **Switch on the microphone.** Its first start downloads the speech model; the status bar says
   when it listens.

"Update…" in the same place installs newer packages after an update of the addon.

### Size and downloads

The addon itself is a few MB. Speech recognition needs much more, about as much as FreeCAD:

| What | Size | Where | From |
|---|---|---|---|
| Speech service (faster-whisper, Piper, numpy, …) | ~550 MB | `<UserAppDataDir>/TalkToMe/venv` | pypi.org |
| Speech model, downloaded on first use | `tiny` ~75 MB, `base` ~150 MB (default without GPU), `small` ~500 MB (default with GPU), `medium` ~1.5 GB | `~/.cache/huggingface` | huggingface.co |
| Voice of the speech output, per language | ~60 MB | `~/.cache/talktome/voices` | huggingface.co |
| GPU support, optional: NVIDIA's CUDA libraries (cuBLAS, cuDNN 9) | ~1.3 GB download, ~2.2 GB on disk | `<UserAppDataDir>/TalkToMe/venv` | pypi.org |

A usual installation without GPU takes about 750 MB.

**NVIDIA graphics card (Windows, Linux):** when the install dialog finds NVIDIA's driver, it offers
"Also install the GPU support". Only the graphics driver has to be installed, not CUDA. Without
the GPU support, or when the GPU does not work (an old driver, for example), the speech service
uses the CPU and the status bar says "no usable GPU found, using the CPU". **Macs** recognize on
the CPU: faster-whisper has no support for Apple's GPU.

These downloads are the only connections to the internet. What you say, the documents and
what Talk to me learns stay on your computer.

The default voices are free: Thorsten (German, CC0) and LJSpeech (English, public domain). Any
other Piper voice works too (`Voice` parameter); check its license yourself.

### Remove

Edit → Preferences → Talk to me → General → Remove… deletes the speech service. Models and voices
stay in the caches above (another program may use the models); delete them by hand if you don't
need them. Then uninstall the addon in the Addon Manager. Your settings and what you taught it are
in `<UserAppDataDir>/TalkToMe`.

## Development

```bash
git clone https://github.com/Palmstroemen/TalkToMe ~/Development/TalkToMe
ln -s ~/Development/TalkToMe "<UserAppDataDir>/Mod/TalkToMe"
sudo apt install python3-venv libportaudio2
python3 -m venv service/.venv
service/.venv/bin/pip install -r service/requirements.txt pytest
```

FreeCAD's Python console shows the folder with `App.getUserAppDataDir()` (FreeCAD 1.1 on Linux:
`~/.local/share/FreeCAD/v1-1/`). The addon uses `service/.venv` as long as the speech service is
not installed in the user folder; the tools below need it.

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
| Windows, macOS | Untested. The installer looks for `python.exe`/`py` (Windows) and for Python of python.org or Homebrew (macOS). Reports welcome. |

## Use in FreeCAD

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

Settings: Edit → Preferences → Talk to me (speech service, language, microphone, volume, model,
GPU/CPU, question menu, speech output and voice, word lists of the language, training). Changes
the speech service needs restart it. The page writes these parameters (`BaseApp/Preferences/Mod/TalkToMe`):

| Parameter | Default | Meaning |
|---|---|---|
| `Language` | FreeCAD's language, else `en` | Spoken language: `de` or `en` (a folder in `lang/`) |
| `Microphone` | system default | Input device name |
| `Volume` | `40` | Volume of tones and voice in percent |
| `Model` | by hardware | `tiny`, `base`, `small`, ... |
| `Device` | `auto` | `auto`, `cuda`, `cpu` |
| `ServicePython` | the installed one | Python of the speech service: `<UserAppDataDir>/TalkToMe/venv`, else `service/.venv` |
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
| `speech.json` | what Talk to me says, and its default voice |
| `corpus.jsonl`, `contexts/` | test sentences with their expected result, played in recorded FreeCAD states |

Packs exist for German and English. Misheard words that sound like a command still find it:
German compares by Cologne phonetics ("Richtig" ≈ "Rechteck"), English by Metaphone
("Pat" ≈ "Pad"); the settings page explains this for the chosen language. Your own changes go to the same files in
`<UserAppDataDir>/TalkToMe/lang/<code>/`: a list there replaces the pack's list, patterns there
come first. A variant such as `de-AT` names its base (`"base": "de"`) and holds only what differs.

A new language or dialect: [docs/ADDING_A_LANGUAGE.md](docs/ADDING_A_LANGUAGE.md). Check a pack
with `python tools/check_pack.py <code>`; `python tools/corpus.py <code> --coverage` shows how
well each command is reached by voice.

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

On every push, GitHub Actions runs them on Linux, Windows and macOS, installs the speech service
as the addon does and says one command to it: `python tools/smoke_install.py --venv <folder>`
(downloads about 750 MB).

## Contributing

Reports, corpus sentences, language packs and code are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

LGPL-2.1-or-later, see [LICENSE](LICENSE).
