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

The first start downloads the speech model (`base`: ~150 MB, `small`: ~500 MB) to `~/.cache/huggingface`.

## Try it outside FreeCAD

```bash
service/.venv/bin/python tools/try_talktome.py               # microphone on, Ctrl+C to stop
service/.venv/bin/python tools/try_talktome.py --model small
```

Every recognized sentence is printed with its latency and the service's decision, using the
vocabulary in `vocab/de.json` (edit it to add your own phrases). You hear a confirmation tone
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
Optional settings (Tools → Edit parameters → `BaseApp/Preferences/Mod/TalkToMe`):

| Parameter | Default | Meaning |
|---|---|---|
| `Language` | `de` | Spoken language |
| `Model` | by hardware | `tiny`, `base`, `small`, ... |
| `Device` | `auto` | `auto`, `cuda`, `cpu` |
| `ServicePython` | `service/.venv/bin/python` | Python of the speech service |
| `DryRun` | `false` | Only show recognized commands, don't execute them |

## Tests

```bash
service/.venv/bin/python -m pytest tests
```

## License

LGPL-2.1-or-later, see [LICENSE](LICENSE).
