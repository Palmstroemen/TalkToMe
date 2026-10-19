# Contributing to Talk to me

Thank you for helping. There are three ways in, from no code at all to Python.

## Without code

- **Report what went wrong.** Use the issue templates: "Not understood" when Talk to me did
  nothing or asked back, "Wrong command" when it did something you did not mean. The training
  page (say "Training" or use the settings) shows what the speech recognition heard; please copy
  it exactly, misspellings included.
- **Add sentences to a corpus.** `lang/<code>/corpus.jsonl` holds sentences with the result they
  must give. Sentences said while working that must *not* trigger anything are especially
  welcome ("the hole is in the wrong place"). Format: [docs/ADDING_A_LANGUAGE.md, section 4](docs/ADDING_A_LANGUAGE.md#4-the-corpus-sentences-with-their-expected-result).
- **Record contexts** of more workbenches and add-ons with `tools/record_context.py`, a macro.
- **Share your corrections.** What you taught Talk to me is in
  `<UserAppDataDir>/TalkToMe/custom.<language>.json`; attach it to a "Language pack improvement"
  issue.
- **A new language or dialect:** [docs/ADDING_A_LANGUAGE.md](docs/ADDING_A_LANGUAGE.md).

## Translating the user interface

The settings and training pages are translated with Qt Linguist; see "Translations of the
user interface" in the [README](README.md).

## Python

Setup and tests: see the [README](README.md). The design and its reasons are in
[DESIGN.md](DESIGN.md); lessons learned on the way in [LEARNINGS.md](LEARNINGS.md).

| Part | Where | Rule |
|---|---|---|
| Recognition and decisions | `ttm_core/` | standard library only; runs in FreeCAD and in the service |
| FreeCAD add-on | `talktome/`, `InitGui.py` | Qt via `talktome/qt.py`; user-visible texts in `translate("TalkToMe", …)` |
| Speech service | `service/talktome_service/` | its own venv (`service/requirements.txt`) |
| Language data | `lang/<code>/` | no language specifics in code: word lists belong in a pack |

How we work:

- **Test first.** A behavior change starts with a failing test.
- **The corpus decides.** A change to how sentences are decided is checked with
  `python tools/corpus.py de` (and `en`) and with `python tools/corpus.py de --coverage`. It may
  not make anything worse; new weaknesses it reveals are marked `known` with a `note`.
- **Rather silent than wrong.** Doing nothing or asking back is fine; executing the wrong
  command or reacting to talk is not.
- **General rules, not special cases.** A fix for one misheard word belongs in the training or
  a language pack, not in the code. If a fix in the code is needed, it should explain a whole
  class of sentences.
- **Real FreeCAD.** Behavior inside FreeCAD is checked in a real FreeCAD, headless if needed
  (`QT_QPA_PLATFORM=offscreen`, with a copy of the user config).

Before a pull request:

```bash
service/.venv/bin/python -m pytest tests
python tools/check_pack.py --all
```

## License

Contributions are under the project's license, LGPL-2.1-or-later. Voices and models you add a
reference to must allow their use; name their license in the pull request.
