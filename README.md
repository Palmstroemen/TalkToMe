# Talk to me

Local, multilingual voice control for FreeCAD 1.x. Status: **Phase 0** (speech recognition spike).
Design: see [DESIGN.md](DESIGN.md).

In Phase 0 the microphone button shows recognized sentences in FreeCAD's status bar.
No FreeCAD command is executed yet.

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

Every recognized sentence is printed with its latency and the matching test command from
`tools/test_commands_de.json` (edit it to add your own phrases). You hear a confirmation tone
when a test command was recognized and an error tone otherwise.

## Measure models

```bash
service/.venv/bin/python tools/measure_stt.py record --out samples/de     # record your voice
service/.venv/bin/python tools/measure_stt.py bench --samples samples/de --models tiny,base,small -v
```

## Use in FreeCAD

Link the repository into FreeCAD's Mod folder and restart FreeCAD. The folder differs between
installations; FreeCAD's Python console shows it with `App.getUserAppDataDir()` (append `Mod`):

```bash
ln -s ~/Development/TalkToMe "<UserAppDataDir>/Mod/TalkToMe"
```

A toolbar "Talk to me" with a microphone button appears in every workbench.
Optional settings (Tools → Edit parameters → `BaseApp/Preferences/Mod/TalkToMe`):

| Parameter | Default | Meaning |
|---|---|---|
| `Language` | `de` | Spoken language |
| `Model` | by hardware | `tiny`, `base`, `small`, ... |
| `Device` | `auto` | `auto`, `cuda`, `cpu` |
| `ServicePython` | `service/.venv/bin/python` | Python of the speech service |

## Tests

```bash
service/.venv/bin/python -m pytest tests
```

## License

LGPL-2.1-or-later, see [LICENSE](LICENSE).
