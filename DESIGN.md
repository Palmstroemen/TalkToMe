# Talk to me – Designdokument

*Sprachsteuerung für FreeCAD 1.x – lokal, mehrsprachig, kontextbezogen, anlernbar.*

Stand: 18.10.2026 · Status: Entwurf · Lizenz: LGPL-2.1-or-later (wie FreeCAD)

---

## 1. Ziel

„Talk to me“ ist ein FreeCAD-Addon, mit dem man FreeCAD per Sprache **bedient**. Gesprochene Befehle ersetzen Klicks auf Buttons, Menüs und Ansichtswechsel. Die Modellierarbeit mit Maus und Skizze bleibt beim Nutzer.

Beispiele:

| Gesprochen | Wirkung |
|---|---|
| „Zeichne ein Rechteck“ (im Sketcher) | Rechteck-Werkzeug des Sketchers wird aktiviert, der Nutzer klickt die Punkte |
| „Rechteck“ (in Draft) | Rechteck-Werkzeug von Draft wird aktiviert |
| „Schließe den Sketch und polstere ihn 12 mm auf“ | Sketch verlassen → Pad erzeugen → Länge = 12 mm |
| „Dreh auf die andere Seite“ | Ansicht wechselt auf die Gegenseite |
| „Rückgängig“ | Letzte Aktion wird rückgängig gemacht |

### Abgrenzung zu bestehenden Projekten

Bestehende LLM-Addons für FreeCAD (z. B. `ghbalf/freecad-ai`, diverse MCP-Server) lassen ein LLM **Python-Code erzeugen**, der Geometrie baut, und werden per Text bedient. „Talk to me“ führt dagegen **ausschließlich vorhandene FreeCAD-Befehle** aus einer Whitelist aus. Es entsteht kein generierter Code. Das ist robuster, sicherer und auch mit kleinen lokalen Modellen machbar.

### Nicht-Ziele (vorerst)

- Geometrie aus Beschreibungen generieren („Mach mir ein Zahnrad“)
- Cloud-Dienste jeglicher Art
- FreeCAD-Versionen vor 1.0

---

## 2. Anforderungen

| # | Anforderung | Folge für das Design |
|---|---|---|
| A1 | **Alle Sprachen** | Intern nur sprachneutrale Befehls-IDs. Sprache nur an den Rändern (Erkennung, Wortschatz) |
| A2 | **Kontextbezogen** | Kandidaten werden nach aktuellem Zustand gefiltert und priorisiert (Abschnitt 6) |
| A3 | **Leicht anlernbar** | Wortschatz-Dateien in mehreren Ebenen, Lernen im laufenden Betrieb (Abschnitt 8) |
| A4 | **Nur lokal** | Spracherkennung, Embeddings und LLM laufen auf dem eigenen Rechner |
| A5 | **Feste Sprache pro Nutzer** | Sprache wird eingestellt statt erkannt, was schneller und treffsicherer ist |
| A6 | **Mikrofon-Schalter statt Push-to-Talk** | Ein Button schaltet das Zuhören ein und aus. Eingeschaltet hört das System ständig zu (Abschnitt 9) |
| A7 | **Rückmeldung per Ton, Sprache in wichtigen Momenten** | Bestätigungston bei Erfolg, Fehlerton bei Nichtverstehen; kurze Sätze, wo ein Ton zu wenig erklärt (Abschnitt 10) |
| A8 | **Nur FreeCAD 1.x** | Neuere APIs dürfen genutzt werden, kein Kompatibilitätsballast |
| A9 | **Mit und ohne Grafikkarte** | GPU-Profil als Normalfall, CPU-Profil als vollwertige Rückfallebene (Abschnitt 12.1) |

---

## 3. Grundprinzipien

1. **Befehls-IDs als gemeinsame Sprache.** Intern gibt es nur FreeCAD-Befehls-IDs wie `Sketcher_CreateRectangle`, `Draft_Rectangle` oder `PartDesign_Pad`, plus Parameterschemata wie `Pad(length: mm)`.
2. **Whitelist statt Code.** Ausgeführt wird nur, was als Befehl in FreeCAD existiert, gerade aktiv ist und gültige Parameter hat.
3. **Schnell vor schlau.** Die meisten Befehle werden ohne LLM über den Wortschatz erkannt. Das LLM kommt nur bei zusammengesetzten Sätzen oder Parametern zum Einsatz.
4. **Lieber nichts tun als das Falsche tun.** Bei Unsicherheit wird nichts ausgeführt (Fehlerton oder Stille, siehe 9.3).
5. **Testbare Logik.** Matching, Kontext-Priorisierung und Wortschatz-Verwaltung sind reines Python ohne FreeCAD und Qt und werden testgetrieben entwickelt.

---

## 4. Architektur

Das System besteht aus **zwei Prozessen**:

```
┌───────────── FreeCAD-Addon „Talk to me“ (dünn, Python/Qt) ─────────────┐        ┌──────────── Sprachdienst (eigener Prozess) ─────────────┐
│                                                                        │        │                                                         │
│  Mikrofon-Button (Toolbar, umschaltbar, zeigt Zustand)                 │        │  Audioaufnahme (dauerhaft, solange eingeschaltet)       │
│                                                                        │        │  Sprachaktivitätserkennung (VAD) → Äußerungen           │
│  Kontext-Sammler                                                       │ ─────► │  Spracherkennung (faster-whisper, feste Sprache,        │
│    aktive Workbench, Edit-Modus, Taskdialog, Auswahl,                  │context │    Kontext-Wortschatz als Hotwords)                     │
│    Kandidaten-Befehle mit übersetzten Texten, isActive()               │        │  Matching (Wortschatz → Embeddings → LLM)               │
│                                                                        │        │  Wortschatz & Gelerntes (Dateien)                       │
│  Ausführer                                                             │ ◄───── │  Töne (Bestätigung / Fehler)                            │
│    Gui.runCommand, Eigenschaften setzen, Undo-Transaktionen            │ plan   │                                                         │
│                                                                        │        │                                                         │
│  Lern-Beobachter (QAction.triggered)                                   │ ─────► │                                                         │
│                                                                        │result  │                                                         │
└────────────────────────────────────────────────────────────────────────┘        └─────────────────────────────────────────────────────────┘
                                         lokaler Socket (127.0.0.1), JSON-Nachrichten
```

### Warum zwei Prozesse?

- **Keine Abhängigkeiten in FreeCADs Python.** Pakete wie faster-whisper, ctranslate2, onnxruntime, sounddevice oder die Modelle in FreeCADs mitgelieferte Python-Umgebung (AppImage, Flatpak, Windows-Installer) zu installieren, ist fehleranfällig. Der Sprachdienst läuft in einer eigenen venv.
- **Die Oberfläche bleibt flüssig.** Dauerzuhören, Erkennung und LLM blockieren FreeCAD nicht.
- **Absturzisolation.** Stürzt der Dienst ab, läuft FreeCAD weiter.
- **Modelle bleiben geladen.** Sie werden einmal beim Start des Dienstes geladen, nicht bei jedem Befehl.

### Lebenszyklus

- Das Addon startet den Dienst beim ersten Einschalten des Mikrofons als Unterprozess. Der Pfad zum Python-Interpreter der venv steht in den Einstellungen.
- Das Addon beendet den Dienst, wenn FreeCAD geschlossen wird.
- Ausschalten des Mikrofons stoppt nur die Audioaufnahme. Der Dienst und seine Modelle bleiben geladen, damit das Wiedereinschalten sofort wirkt.

---

## 5. Komponenten

### 5.1 FreeCAD-Addon

| Modul | Aufgabe | FreeCAD-abhängig? |
|---|---|---|
| `InitGui.py` | Registrierung: Toolbar mit Mikrofon-Button, Einstellungsseite | ja |
| `context.py` | Kontext sammeln und als neutrales Datenobjekt liefern | ja (Sammeln) |
| `executor.py` | Plan prüfen und ausführen, Undo-Transaktion | ja |
| `observer.py` | Klicks auf Befehle beobachten (Lernmodus) | ja |
| `client.py` | Socket-Verbindung zum Dienst, Nachrichten, Neuverbindung | nein (Qt-Socket oder Thread) |
| `ttm_core/` | Gemeinsame, reine Logik (siehe 5.3) | **nein** |

### 5.2 Sprachdienst

| Modul | Aufgabe |
|---|---|
| `audio.py` | Aufnahme über `sounddevice`, Ringpuffer |
| `vad.py` | Erkennung von Sprachaktivität (z. B. Silero VAD), Zerlegung in Äußerungen |
| `stt.py` | faster-whisper mit fester Sprache und Kontext-Hotwords |
| `matcher.py` | Stufen 1–3 des Matchings (Abschnitt 7) |
| `llm.py` | Anbindung an ein lokales LLM (Ollama oder llama.cpp) mit JSON-Schema-Ausgabe |
| `vocab.py` | Wortschatz laden, zusammenführen, Gelerntes speichern |
| `tones.py` | Bestätigungs- und Fehlerton erzeugen und abspielen |
| `server.py` | Socket-Server, Nachrichtenverarbeitung |

### 5.3 Gemeinsamer Kern `ttm_core`

Dieser Kern ist reines Python ohne FreeCAD und Qt und vollständig mit pytest getestet:

- Datenmodelle: Kontext, Kandidat, Plan, Ergebnis
- Kontext-Priorisierung (Abschnitt 6)
- Unscharfer Wortschatz-Abgleich (Stufe 1)
- Zusammenführen der Wortschatz-Ebenen
- Prüfung der Parameter gegen die Schemata
- Nachrichtenformat (Serialisierung)

---

## 6. Kontextmodell

### 6.1 Was erfasst wird

| Kontextmerkmal | Quelle in FreeCAD 1.x |
|---|---|
| Aktive Workbench | `Gui.activeWorkbench()` |
| Sichtbare Befehle der Workbench | `Workbench.listToolbars()`, `Workbench.getToolbarItems()` |
| Befehl aktuell ausführbar? | `Gui.Command.get(id).isActive()` |
| Englischer Quelltext eines Befehls | `Gui.Command.get(id).getInfo()` → `menuText`, `toolTip` |
| **Übersetzter** Text eines Befehls | `Gui.Command.get(id).getAction()` → QAction(s) → `text()`, `toolTip()` |
| Bearbeitungsmodus (z. B. im Sketch) | `Gui.ActiveDocument.getInEdit()` |
| Offener Aufgabendialog | `Gui.Control.activeDialog()` |
| Auswahl | `Gui.Selection.getSelectionEx()` |

Laut Quellcode von FreeCAD 1.1.4 (`CommandPyImp.cpp`) liefert `getInfo()` die **unübersetzten** Quelltexte. Die übersetzten Texte der Oberflächensprache liefert nur die QAction aus `getAction()`. QActions entstehen erst, wenn ein Befehl in einer Toolbar oder einem Menü auftaucht. Bei Workbenches, die noch nie aktiviert wurden, fehlen sie daher anfangs, und dann dient der englische Text als Rückfallebene.

### 6.2 Prioritätsebenen

```
Ebene 1  Offener Aufgabendialog   z. B. Pad-Dialog: „12 Millimeter“, „umkehren“, „OK“, „abbrechen“
Ebene 2  Bearbeitungsmodus        z. B. im Sketch: Sketcher-Befehle
Ebene 3  Aktive Workbench         Befehle ihrer Toolbars (= die sichtbaren Buttons)
Ebene 4  Global                   Ansichten, Rückgängig/Wiederholen, Speichern, Workbench wechseln
```

- Gesucht wird von Ebene 1 nach Ebene 4. Ein Treffer in einer höheren Ebene schlägt einen gleich guten in einer tieferen.
- Nicht ausführbare Befehle (`isActive() == False`) werden nicht ausgeführt, sondern vermerkt, z. B. „Pad braucht einen ausgewählten Sketch“.
- Findet sich ein Befehl nur in einer **anderen** Workbench, wird er nicht automatisch ausgeführt. In einer späteren Ausbaustufe kann das System den Wechsel der Workbench anbieten.

### 6.3 Globale Befehle und Workbench-Wechsel

- **Ebene 4 (global)** umfasst die `Std_`-Befehle, die in jeder Workbench gelten, z. B. Speichern, Öffnen, Rückgängig, Ansichten, Zoom, Auswahl. Quelle sind die Standard-Toolbars und -Menüs (`Workbench.listMenus()`, `listToolbars()`) bzw. die Liste aller Befehle (`Gui.Command.listAll()`).
- **Workbench-Wechsel** sind in FreeCAD keine normalen Befehle. Sie werden als virtuelle Befehle `workbench:<Name>` geführt und mit `Gui.activateWorkbench()` ausgeführt. Ihr Wortschatz stammt aus den Menütexten der Workbenches.
- **Mehrdeutigkeit:** Bei Phrasen wie „Öffne den Sketcher“ (Workbench-Wechsel oder `Sketcher_NewSketch`?) entscheidet der Kontext. Ist in PartDesign eine Fläche gewählt, gilt der neue Sketch, sonst der Wechsel. Sind beide Kandidaten gleich gut, wird nichts ausgeführt und der Fehlerton gespielt (Grundprinzip 4).

### 6.4 Zeigewörter („da“, „hier“, „das“)

- **Momentaufnahme:** Zum Zeitpunkt einer Äußerung hält das Addon die **Mausposition in der 3D-Ansicht** und die **Auswahl** fest. Gemeint ist der Beginn der Äußerung, nicht der Moment, in dem der Text vorliegt.
- **Auswertung:** „Zoome da hinein“ zoomt zur Mausposition. „Lösche das“ und „polstere das auf“ wirken auf die Auswahl.
- **Rückfrage statt Raten:** Fehlt der Bezug, z. B. bei „lösche das“ ohne Auswahl, wird nichts ausgeführt und der Fehlerton gespielt.

### 6.5 Werkzeug-Ebene und Folgebefehle

Viele Befehle starten ein **interaktives Werkzeug**, das weitere Eingaben erwartet. Beispiel: Nach „Zeichne ein Rechteck“ läuft das Rechteck-Werkzeug des Sketchers. Der Nutzer klickt die Ecken oder gibt die Seitenlängen genau an.

- **Neue oberste Ebene „Werkzeug“** (über „Dialog“): Solange ein Werkzeug läuft, haben seine Folgeeingaben Vorrang, etwa „Breite 50“, „Höhe 30“, „50 mal 30“, „fertig“, „abbrechen“.
- **Folgebefehle stehen im Wortschatz beim auslösenden Befehl**, mit eigenen Parameterschemata, z. B. `Sketcher_CreateRectangle → { width: mm, height: mm }`.
- **Eingabe der Werte:** FreeCAD 1.x zeigt beim Zeichnen im Sketcher Eingabefelder direkt in der Ansicht (*On-View-Parameters*). Die Werte könnten wie Tastatureingaben dort hineingeschrieben werden (Zahl, Tab, Zahl, Enter).
- **Mausklicks bleiben beim Nutzer.** Sprache und Maus ergänzen sich. Was der Nutzer *während* der Klicks sagt („von hier … nach hier“), ist Begleitsprache und wird ignoriert (Abschnitt 9.4).

**Zu klären in FreeCAD (vor Phase 4):**
1. Lässt sich von Python aus erkennen, **ob und welches Werkzeug gerade läuft**? Falls nicht, muss das Addon es selbst verfolgen: Werkzeug gestartet, bis Escape, Enter oder ein neuer Befehl.
2. Nehmen die **On-View-Parameters** simulierte Tastatureingaben zuverlässig an? Gibt es eine direktere Schnittstelle?
3. Welche Werkzeuge haben welche Folgeeingaben? Das ergibt eine Liste pro Workbench, beginnend mit Sketcher und PartDesign.

### 6.6 Kontext-Synchronisation

Das Addon schickt bei jeder relevanten Änderung einen Kontext-Schnappschuss an den Dienst: Wechsel der Workbench, Betreten oder Verlassen des Bearbeitungsmodus, Öffnen oder Schließen eines Taskdialogs, Änderung der Auswahl. Die Schnappschüsse werden gebündelt, damit nicht jede Mausbewegung einen auslöst. Der Dienst hat damit **vor** jeder Äußerung den aktuellen Kontext und kann ihn der Spracherkennung als Hotwords mitgeben.

---

## 7. Matching-Pipeline

```
Äußerung (Audio)
  │
  ▼
Spracherkennung   faster-whisper, language=<fest>, hotwords=<Wortschatz des Kontexts>
  │  Text
  ▼
Stufe 1  Wortschatz-Abgleich (unscharf) in Kontext-Kandidaten       → Treffer sicher?  → Plan
  │ nein
  ▼
Stufe 1b Abgleich mit den Hilfstexten der Befehle (Wortstämme)      → Treffer sicher?  → Plan
  │ nein
  ▼
Stufe 2  Embedding-Ähnlichkeit (mehrsprachiges Modell)              → Treffer sicher?  → Plan
  │ nein / Satz enthält Parameter oder mehrere Befehle
  ▼
Stufe 3  Kleines LLM: Kandidatenliste + Satz → JSON-Plan (Schema)   → gültig?          → Plan
  │ nein
  ▼
Nicht verstanden  → Fehlerton (oder Stille, siehe 9.3)
```

### Stufe 1b: Hilfstexte

FreeCAD beschreibt jeden Befehl in einem Statustext, übersetzt in die Sprache des Benutzers
(„Vertiefung: Extrudiert die ausgewählte Skizze … und zieht das Ergebnis von dem Körper ab“).
Damit findet „Extrudiere das und ziehe es vom Körper ab“ die Vertiefung, ohne dass ihr Name
fällt (`ttm_core/description.py`):

- Satz und Hilfstexte werden auf Wortstämme reduziert („Extrudiere“, „extrudiert“ → „extrud“),
  Stoppwörter fallen weg.
- Trennbare Verben: Ein Partikel am Satzende wird mit dem Verb am Satzanfang verbunden
  („zieht … ab“ → „ab+zieh“). Nur so unterscheiden sich Vertiefung und Aufpolsterung.
- Ein Befehl punktet mit dem Anteil des Satzes, den sein Hilfstext abdeckt. Seltene Wörter
  zählen mehr. Wörter, die in keinem Hilfstext vorkommen, zählen nicht.
- Sicher heißt: mindestens zwei bekannte Wörter, Abdeckung ≥ 0,7, Vorsprung ≥ 0,15 vor dem
  Zweitbesten. Die Hilfstexte verwandter Befehle sind sich sehr ähnlich.
- Der Name hat Vorrang. Ausnahme: Er erklärt weniger als die Hälfte der bedeutungstragenden
  Wörter, und die Hilfstexte zeigen eindeutig auf einen Befehl („extrudieren“ ist im
  Wortschatz die Aufpolsterung, der ganze Satz beschreibt aber die Vertiefung).
- Abschnitte des Satzes, die nur aus Stoppwörtern bestehen, treffen keinen Namen:
  „und“ klingt wie „Undo“, „gut“ sieht aus wie „Cut“.

Grenze: Andere Wörter als im Hilfstext („mach die Kanten rund“ statt „Verrundung“) findet erst
Stufe 2.

Englische Befehlsnamen („Pad“, „Pocket“) bleiben erkennbar, denn viele sagen sie auch auf
Deutsch. Sie stehen aber getrennt (`foreign`): Sie werden nur nach Schreibweise verglichen, nicht
nach Klang, denn deutsche Lautregeln auf englische Wörter angewandt machen „Ebene“ zu „Open“. Sie
gehen auch nicht als Hinweiswörter an die Spracherkennung.

### Befehlssequenzen

„Wechsle bitte zu Part Design, erstelle einen neuen Körper und dann eine Skizze“ sind drei
Schritte. Ablauf (`ttm_core/clauses.py`, `ttm_core/sequence.py`):

1. Die Äußerung wird in Teilsätze zerlegt: an Satzzeichen (außer dem Dezimalkomma) und an
   „und“, „dann“, „danach“, „anschließend“.
2. Ist die ganze Äußerung Gerede (siehe 9.3), wird sie als Ganzes ignoriert. Einzelne kurze
   Reste wie „finde ich“ würden sonst wie Befehlsversuche aussehen.
3. Der nächste Schritt: Die ersten ein bis drei Teilsätze werden als ein Befehl probiert, denn
   ein Befehl kann sich über mehrere erstrecken („Extrudiere das und ziehe es vom Körper ab“).
   Ein weiterer Teilsatz gehört nur dazu, wenn er für denselben Befehl zusätzliche Wörter erklärt.
   Ein Workbench-Wechsel ist immer ein eigener Schritt.
4. Der Dienst schickt den Schritt als `plan` mit `more`, das Addon führt ihn aus, schickt den
   neuen Kontext und dann `result`. Erst danach wird der nächste Schritt entschieden, im Kontext
   nach dem vorigen: Nach dem Wechsel zu Part Design gibt es den Befehl „Körper“.
5. Gerede-Teilsätze werden übersprungen. Ein unklarer Teilsatz oder ein fehlgeschlagener
   Schritt beendet die Sequenz mit Fehlerton, denn die folgenden Schritte liefen in einem
   unerwarteten Zustand. Der Bestätigungston kommt einmal am Ende.

### Auswahl in Dialogen

Ist ein Aufgabendialog mit Liste offen, sind ihre Einträge Kandidaten auf der höchsten Ebene
(`ui:choose:<Text>`), z. B. die Ebenen für eine neue Skizze: „XY-Ebene“. Der Wortschatz kann
ihnen weitere Phrasen geben, Schlüssel ist der übersetzte Text („Draufsicht“, „von oben“ für
die XY-Ebene).

Steht die Auswahl im selben Teilsatz wie der Befehl, der den Dialog öffnet („mach eine Skizze in
der XY-Ebene“), schickt das Addon nach dem Schritt den neuen Kontext, und der Dienst prüft den
Teilsatz noch einmal gegen die Auswahl des Dialogs. Passt sie sicher, folgt sie als eigener
Schritt.

Die Auswahl markiert den Eintrag. Dialoge, deren Liste genau eine Frage stellt, werden gleich
bestätigt (`AUTO_CONFIRM` im Executor, derzeit die Merkmalsauswahl von PartDesign). Sonst folgt
„OK“.

FreeCAD blendet Aufgabendialoge mit etwa 300 ms Verzögerung ein; ob ein Element zum Dialog
gehört, prüft das Addon deshalb mit `isVisibleTo(TaskView)` statt `isVisible()`.

Erkennung: Das gesprochene „Ypsilon“ schreibt Whisper (base) jedes Mal anders: „Upsilom“,
„Upsalon“, „Übsilon“, „Öpsilon“, „Öpsel“. Statt einer Sonderregel dafür soll das Training
(8.5) solche stimm- und modellabhängigen Verhörer lernen.

Vorsicht bei Ausweichwörtern: Ein einzelnes Wort kann wie ein anderes klingen. „oben“ und
„Ebene“ haben beide den Code 016, dadurch wurde jede Ebene zur XY-Ebene. Ausweichwörter
deshalb als Wortgruppe („von oben“).

### Befehle mit freiem Text: Umbenennen

„Den nennen wir Bodenplatte“: Der Name ist freier Text, er lässt sich nicht unscharf mit
Befehlsnamen vergleichen. Solche Befehle erkennen Satzmuster je Sprache mit einer Lücke für den
Parameter (`ttm_core/params.py`): „nenne ihn X“, „benenne ihn um in X“, „der soll X heißen“,
„gib ihm den Namen X“, „Name X“. Die Muster werden pro Teilsatz vor dem normalen Abgleich
geprüft; ein Teilsatz mit Muster ist nie Gerede.

Worauf sich „den“, „das“, „ihn“ beziehen, entscheidet das Addon:
1. ein Objekt, das ein Schritt derselben Äußerung erzeugt hat („erstelle einen Körper, den nennen
   wir Bodenplatte“),
2. sonst das eine ausgewählte Objekt,
3. sonst das zuletzt per Sprache erzeugte Objekt (auch aus einer früheren Äußerung).

Was ein Schritt erzeugt hat, ergibt der Vergleich der Dokumentobjekte vorher und nachher, ohne
Kinder der neuen Objekte (ein neuer Körper bringt seinen Ursprung mit). Das Label wird in einer
Transaktion gesetzt, „Rückgängig“ stellt den alten Namen wieder her.

### Plan-Format

```json
{
  "utterance": "schließe den Sketch und polstere ihn 12 mm auf",
  "steps": [
    { "command": "Sketcher_LeaveSketch" },
    { "command": "PartDesign_Pad", "params": { "length": 12.0 } }
  ],
  "confidence": 0.86,
  "stage": 3
}
```

### Parameter

- Parametrische Befehle bekommen ein Schema im Wortschatz, z. B. `PartDesign_Pad: { length: mm }`.
- Parameter werden **nicht** über die Felder des Taskdialogs gesetzt, das ist fragil. Stattdessen wird das Objekt erzeugt und seine Eigenschaft direkt gesetzt, z. B. `Pad.Length = 12 mm`, gefolgt von einer Neuberechnung.
- Zahlen und Einheiten werden sprachabhängig normalisiert („zwölf Millimeter“, „12 mm“, „1,2 cm“).

### Ausführung

- Jeder Plan läuft in **einer** Undo-Transaktion. „Rückgängig“ hebt also den ganzen Sprachbefehl auf, nicht nur den letzten Schritt.
- Vor jedem Schritt wird erneut geprüft, ob der Befehl existiert und aktiv ist. Der Kontext kann sich seit dem Schnappschuss geändert haben.
- Schlägt ein Schritt fehl, wird abgebrochen, die Transaktion zurückgenommen und der Fehlerton gespielt.

---

## 8. Wortschatz und Anlernen

### 8.1 Ebenen

```
Priorität hoch   user/learned.<lang>.json     im Betrieb gelernte Phrasen
                 user/custom.<lang>.json      vom Nutzer gepflegte Schlüsselwörter und Makros
                 vocab/<workbench>.<lang>.json  mitgelieferte und teilbare Pakete
Priorität tief   automatisch erzeugt          aus den übersetzten QAction-Texten (+ englische Rückfallebene)
```

### 8.2 Format eines Pakets

```json
{
  "workbench": "PartDesignWorkbench",
  "language": "de",
  "commands": {
    "PartDesign_Pad": {
      "phrases": ["Polster", "aufpolstern", "extrudieren", "hochziehen"],
      "params": { "length": "mm" }
    },
    "PartDesign_Pocket": {
      "phrases": ["Tasche", "Vertiefung", "ausschneiden"],
      "params": { "length": "mm" }
    }
  }
}
```

### 8.3 Anlernen

| Weg | Ablauf |
|---|---|
| **Schlüsselwörter definieren** | Phrasen zu Befehls-IDs in `custom.<lang>.json` eintragen. Später gibt es dafür einen Editor |
| **Pakete pro Workbench** | Pakete für einzelne Workbenches, auch für Addon-Workbenches, können geteilt und installiert werden |
| **Lernmodus** | Nach einer nicht verstandenen Äußerung klickt der Nutzer innerhalb weniger Sekunden den gemeinten Button. Das Addon beobachtet `QAction.triggered` und speichert die Äußerung als Phrase für diesen Befehl |
| **Makros** | Eine Phrase steht für eine Befehlsfolge, z. B. „Standardplatte“ → Sketch auf XY, Rechteck, Pad 12 mm |

Der Lernmodus lässt sich umsetzen, weil `Gui.Command.get(id).getAction()` die QActions der Befehle liefert. Mit deren Signal `triggered` kann man sich verbinden. Das ist laut Quellcode von FreeCAD 1.1.4 verfügbar.

### 8.4 Ziel: normal sprechen statt Befehle auswendig lernen

Nutzer sollen nicht die Befehlsnamen lernen müssen. Manche Bezeichnungen sind ungewohnt, etwa „Aufpolstern“ für Pad. Gemeint ist oft „extrudieren“, „hochziehen“ oder „zieh das in 3D auf“. Dafür arbeiten die Ebenen zusammen:

| Ebene | Deckt ab | Beispiel für `PartDesign_Pad` |
|---|---|---|
| Automatischer Wortschatz | Bezeichnungen der Buttons | „Aufpolstern“, „Pad“ |
| Übersetzungstabelle (Pakete + eigene Einträge) | Gebräuchliche Synonyme und Wendungen | „extrudieren“, „hochziehen“, „in 3D aufziehen“ |
| Embeddings (Stufe 2) | Umschreibungen, die nicht in der Tabelle stehen | „zieh das jetzt nach oben raus“ |
| Lernmodus | Persönliche Ausdrücke und typische Fehlerkennungen | „extrahiere das“ (falsch gehört für „extrudiere“) |

Gespeichert wird im Lernmodus immer der **tatsächlich erkannte** Text, nicht der gemeinte. Damit lernt das System auch die Fehler der Spracherkennung mit.

### 8.5 Lernmodus im Detail

- **Zeitfenster statt Gleichzeitigkeit:** Der Text einer Äußerung liegt erst nach dem Satzende vor. Gepaart werden deshalb die letzte Äußerung und ein Button-Klick, die innerhalb eines Zeitfensters liegen (z. B. ±5 s, einstellbar).
- **Der Klick wird normal ausgeführt.** Der Lernmodus beobachtet nur und unterdrückt nichts.
- **Bestätigung:** Ein Bestätigungston signalisiert, dass eine neue Zuordnung gespeichert wurde. In der Statusleiste steht „»…« → Befehl“. Rückgängig machen lässt sich das über den Wortschatz-Editor (Phase 5).
- **Ein- und ausschalten:** Der Lernmodus ist eigenständig schaltbar. Zusätzlich ist er nach einem Fehlerton kurz automatisch aktiv (siehe 9.3).

### 8.7 Training

Nicht jede Fehlerkennung lässt sich mit einer Regel beheben. Wie Whisper eine Stimme hört,
hängt von Sprecher, Mikrofon und Modell ab (das gesprochene „Ypsilon“ wird bei einem Nutzer zu
„Upsilom“, „Upsalon“, „Öpsilon“). Statt Sonderregeln lernt das System diese Formen pro Nutzer.

**Trainingsseite** (eigenes, nicht-modales Fenster, Befehl `TalkToMe_Training`), von oben
nach unten, jeweils mit kurzem Hilfetext:

1. **Nicht verstandene Sätze** als Tabelle *Zeit | Gehört | Gemeint*. Was schon zugewiesen ist
   (auch über das Rückfrage-Menü), steht als „→ XY-Ebene ✓“ in der letzten Spalte. Jeder Satz
   bringt die Kandidaten seines Moments mit, denn ein Dialog kann inzwischen geschlossen sein.
2. **Noch einmal sprechen** (optional, 3×). Der Dienst schaltet in den Trainingsmodus
   (`train`): Er erkennt nur und führt nichts aus. Man kann auch hier mit einem neuen Satz
   beginnen.
3. **Welcher Befehl war gemeint?** Liste der Befehle der Situation, die wahrscheinlichen oben,
   mit Filter; alternativ den Satz eintippen und suchen. **Assign** oder Doppelklick speichert
   sofort: den gehörten Satz und die Aufnahmen. Jede Form wird eingeordnet: ＋ gelernt,
   ✓ schon verstanden, ⚠ würde einen anderen Befehl treffen (nicht gespeichert).
   **Forget** nimmt eine Zuweisung zurück.

**Gelernte Formen** (`_heard` in der Benutzerdatei) zählen beim Vergleich wie Phrasen, mit
Lautvergleich, sodass auch ähnliche Verhörer passen. Sie gehen aber **nicht als Hinweiswörter**
an Whisper, sonst würde man es zu „Upsilom“ erziehen. Ein eingetippter Satz wird nur dann als
Phrase gespeichert, wenn er den Befehl nicht schon trifft.

### 8.8 Rückfrage-Menü bei Unklarheit

Ist eine Äußerung ein Befehlsversuch, aber nicht eindeutig (mehrdeutig, knapp unter der
Schwelle, Befehl gerade nicht verfügbar), erscheint neben dem Mauszeiger ein kleines Menü mit
den besten Kandidaten:

- **Nicht blockierend:** ein Feld neben dem Mauszeiger, das weder Maus noch Tastatur fängt; es
  verschwindet nach einigen Sekunden oder beim Weiterarbeiten. Ein Rechteck im Sketcher wird
  dadurch nicht unterbrochen.
- **Nur bei Befehlsversuchen** (nicht bei ignoriertem Gerede) und nur mit Kandidaten über einem
  Mindestwert.
- **Per Maus oder Stimme:** Einträge sind nummeriert („eins“, „die zweite“).
- **Nicht verfügbare Befehle** erscheinen ausgegraut mit Grund („Vertiefung – erst eine Skizze
  wählen“).
- **Die Wahl ist Training:** Der gewählte Befehl wird ausgeführt, und der gehörte Text wird als
  gelernte Form gespeichert. Beim nächsten Mal ist keine Rückfrage mehr nötig. Das ersetzt den
  Lernmodus per Button-Klick (8.5) für die häufigsten Fälle.
- **Letzter Eintrag:** „Keins davon – trainieren…“ öffnet die Trainingsseite mit diesem Satz.
- **In Befehlsfolgen** wartet die Folge auf die Wahl und läuft dann weiter; ohne Wahl bricht sie
  ab.

Ein Ringmenü (wie das Addon „PieMenu“) wäre mit der Maus schneller; für den Anfang eine kleine
Liste, die sich auch per Stimme gut bedienen lässt.

### 8.6 Makros

- **Makros mit Toolbar-Button** sind für FreeCAD normale Befehle mit eigener QAction. Sie werden vom Lernmodus genauso erkannt und über `Gui.runCommand` ausgeführt.
- **Makros ohne Button** werden in der Übersetzungstabelle als eigener Eintragstyp hinterlegt, der auf die Makro-Datei verweist (`{"macro": "MeinMakro.FCMacro", "phrases": [...]}`). Sie werden über FreeCADs Makro-Ausführung gestartet.
- **Gesprochene Makros aus Befehlsfolgen** („Standardplatte“ → Sketch, Rechteck, Pad 12 mm) bleiben wie in 8.3 beschrieben möglich.

---

## 9. Dauerzuhören (Mikrofon-Schalter)

### 9.1 Bedienung

- **Ein Toolbar-Button** mit Mikrofon-Symbol schaltet das Zuhören ein und aus (umschaltbar). Er ist ein FreeCAD-Befehl (`TalkToMe_Microphone`): Unter *Werkzeuge → Anpassen → Tastatur* bekommt er eine beliebige Taste, auch die eines Fußpedals, und er lässt sich in andere Toolbars ziehen.
- **Die Mikrofon-Taste der Tastatur** (viele Laptops, z. B. Fn+F4) schaltet das Mikrofon im System stumm. Der Dienst bekommt dann exakte Nullen, echtes Mikrofonrauschen ist nie genau null. Nach 0,5 s Nullen zeigt der Button „stumm (System)“ in Orange; die Spracherkennung überspringt die Nullen sofort. Externe Tastaturen haben diese Taste meist nicht, dafür gibt es das Tastenkürzel des Buttons.
- **Der Zustand ist deutlich sichtbar:** Das Symbol unterscheidet die Zustände aus, hört zu, verarbeitet gerade und Dienst nicht erreichbar.
- **Optional:** Das Zuhören pausiert automatisch, solange FreeCAD nicht das aktive Fenster ist. Das ist nützlich bei Videokonferenzen.
- **Ausschalten per Sprache:** „Mikro aus“, „kurze Pause“, „Stoppe mal die Aufnahme“, „Höre nicht mehr zu“ (`ui:mic_off`, immer verfügbar). Steckt der Befehl in einer Äußerung, wird nur er ausgeführt: „Ok, kurze Pause“ drückt in einem Dialog nicht erst OK. Ein Fehlalarm ist harmlos, das Mikrofon ist dann aus. Zum Einschalten gibt es bewusst keinen Sprachbefehl, dafür ist der Button da.

#### Betriebsart Sprechtaste (später, für laute Umgebungen)

Für laute Umgebungen oder Großraumbüros ist das Mikrofon wahlweise eine Sprechtaste (Push-to-Talk) statt eines Schalters (Einstellung `Mode`: `toggle` / `push`):

- **Auslöser:** eine Taste der Tastatur. Fußpedale melden sich meist als Tastatur und senden eine einstellbare Taste (oft F13–F24, die auf normalen Tastaturen fehlen und nicht mit FreeCAD-Kürzeln kollidieren). Gedrückt halten des Buttons mit der Maus geht ebenso.
- **Technik:** Ein Ereignisfilter auf der FreeCAD-Anwendung fängt Drücken und Loslassen der Taste ab. Automatische Tastenwiederholung wird ignoriert. Er wirkt nur, solange FreeCAD das aktive Fenster ist; systemweite Tasten bräuchten betriebssystemabhängigen Code.
- **Ablauf:** Drücken = Aufnahme an. Loslassen = Äußerung sofort beenden und erkennen, nicht auf die Pause der VAD warten (neue Nachricht `listen` mit `flush`). Was zwischen Drücken und Loslassen gesagt wird, ist eine Äußerung; Gerede-Erkennung und Ignorieren entfallen weitgehend, denn wer die Taste drückt, meint einen Befehl.
- **Vorteil neben der Ruhe:** Die Antwort kommt schneller, weil die Wartezeit auf das Ende der Äußerung (etwa 0,6 s) entfällt.

#### Hintergrundgeräusche

Die VAD (Silero) unterscheidet Sprache von Geräuschen wie Lüftern, Tastatur oder Maschinen; die bleiben schon heute draußen. Stimmen im Hintergrund sind für sie aber Sprache. Mit einem Headset ist die eigene Stimme deutlich lauter als alles andere. Eine einstellbare Mindestlautstärke (`MinLevel`, mit Kalibrierung: einmal still sein, einmal sprechen) lässt dann nur noch die eigene Stimme durch.

### 9.2 Von Audio zu Äußerungen

- Die Audioaufnahme läuft dauerhaft, solange das Mikrofon eingeschaltet ist.
- **Die Sprachaktivitätserkennung (VAD)** trennt Sprache von Stille. Eine Äußerung endet nach einer kurzen Pause, die einstellbar ist und bei etwa 0,5–0,8 s liegt.
- Sehr kurze Geräusche wie Klicks oder Husten werden verworfen.
- **Nur Äußerungen** werden erkannt, nicht der Dauerstrom. Das spart Rechenzeit.
- **Eigene Töne:** Während Bestätigungs- und Fehlertöne abgespielt werden, ist die Aufnahme stumm geschaltet, damit sich das System nicht selbst hört.

### 9.3 Nicht jedes Gesprochene ist ein Befehl

Dauerzuhören ist das größte Risiko des Designs. Das System hört auch Telefonate, Selbstgespräche und Kollegen. Damit es dabei weder etwas Falsches ausführt noch ständig Fehlertöne spielt, gilt eine dreistufige Entscheidung:

| Ergebnis | Bedingung (Beispiel) | Reaktion |
|---|---|---|
| **Ausführen** | Hohe Konfidenz und Befehl im Kontext aktiv | Ausführen + Bestätigungston |
| **Fehlerton** | Äußerung wirkt wie ein Befehlsversuch (kurz, enthält Befehls- oder Wortschatznähe), aber kein sicherer Treffer | Nichts ausführen + Fehlerton, Lernmodus kurz bereit |
| **Ignorieren** | Lange Sätze (ab 4 Wörtern) ohne Treffer über 0,7, typische Gesprächssprache | Nichts tun, kein Ton |

Die Schwellenwerte sind einstellbar und werden in der Spike-Phase an echten Aufnahmen kalibriert.

### 9.4 Begleitsprache

Nutzer sprechen mehr als Befehle, etwa: „Zeichne ein Rechteck … und zwar von hier (Klick) nach hier (Klick).“ Die Spracherkennung zerlegt das bei Pausen in Stücke:

| Stück | Behandlung |
|---|---|
| „Zeichne ein Rechteck“ | Befehl → ausführen |
| „und zwar von hier“ | nur Füllwörter → **still ignorieren** |
| „nach hier“ | nur Füllwörter → **still ignorieren** |

- **Füllwörter pro Sprache** (`ttm_core/languages.py`: „und“, „zwar“, „hier“, „da“, „nach“, „jetzt“ …): Ein Satzstück, das nur aus ihnen besteht, löst weder Befehl noch Fehlerton aus.
- **Beim Bewerten echter Befehle bleiben sie erhalten:** „von vorne“ trifft weiterhin die Vorderansicht.
- **Ohne diese Regel** hätte „von hier“ wegen der Ähnlichkeit zu „von hinten“ sogar einen falschen Ansichtswechsel auslösen können.

**Mögliche Erweiterung**, falls Fehlauslösungen ein Problem bleiben: Ein optionales Rufwort (z. B. „FreeCAD, …“) wird **nur im Dauerzuhör-Modus** verlangt. Es lässt sich in den Einstellungen abschalten.

---

## 10. Rückmeldung

- **Bestätigungston:** kurz und hell, wenn ein Plan erfolgreich ausgeführt wurde.
- **Fehlerton:** kurz und tiefer, wenn etwas nicht verstanden wurde oder fehlgeschlagen ist.
- **Erzeugung der Töne:** Der Sprachdienst erzeugt sie synthetisch, z. B. als Sinus mit Hüllkurve, und spielt sie über `sounddevice` ab. Das Addon braucht kein Qt-Multimedia.
- **Optional: Text in der Statusleiste,** z. B. „Erkannt: ‚Rechteck‘ → Sketcher_CreateRectangle“. Das hilft beim Anlernen und bei der Fehlersuche.
- **Bei Unsicherheit** das Rückfrage-Menü neben dem Mauszeiger (8.8).

### 10.1 Sprachausgabe

Töne für das Alltägliche, Sprache für die Momente, in denen ein Ton zu wenig erklärt.

| Stufe | Verhalten |
|---|---|
| Aus | nur Töne |
| Wichtiges (Vorgabe) | abgebrochene Folge mit Grund („Vertiefung geht gerade nicht – zuerst eine Skizze wählen“), Rückfrage („Meinst du Vertiefung oder Nut?“), Anleitung im Training („Bitte noch zweimal“), Dienst bereit („Ich höre zu“) |
| Gesprächig | zusätzlich Bestätigungen („Mache ich“) |

- **Piper** (lokal, schnell auf der CPU). Feste Sätze werden beim Start erzeugt und
  zwischengespeichert, damit sie ohne Verzögerung kommen.
- **Im Sprachdienst**, der auch die Töne spielt: Während er spricht, ist das Mikrofon taub
  (sich nicht selbst hören). Unterbrechen im Satz ist ein späteres Thema.
- **Die Sätze stehen im Sprachpaket** (`lang/<sprache>/speech.json`, 13.1).
- **Stimme wählbar:** Mitgeliefert bzw. vorgeschlagen werden nur frei lizenzierte Stimmen (z. B.
  „Thorsten“, CC0). Andere Piper-Stimmen lädt der Nutzer selbst und wählt die Datei. Stimmen,
  die aus urheberrechtlich geschütztem Material trainiert sind (z. B. GLaDOS aus „Portal“),
  dürfen wir nicht mitliefern; die Lizenz jeder Stimme wird in der Auswahl angezeigt.

---

## 11. Protokoll zwischen Addon und Dienst

Die Verbindung läuft über TCP auf `127.0.0.1` (Port einstellbar), mit einer JSON-Nachricht pro Zeile.

| Richtung | Nachricht | Inhalt |
|---|---|---|
| Addon → Dienst | `hello` | Protokollversion, Sprache, FreeCAD-Version |
| Addon → Dienst | `listen` | `on` / `off` |
| Addon → Dienst | `context` | Kontext-Schnappschuss (Ebenen, Kandidaten mit Texten, Auswahl) |
| Dienst → Addon | `state` | `listening` / `processing` / `idle` / `error` |
| Dienst → Addon | `speech_start` | Eine Äußerung beginnt. Das Addon hält Mausposition und Auswahl fest (6.4) |
| Dienst → Addon | `plan` | Ein Schritt: `id`, `command`, `text` (sein Teil der Äußerung), `utterance`, `more` (weitere Schritte folgen), `via` (`name` / `description`) |
| Dienst → Addon | `not_understood` | Erkannter Text, ggf. Top-3-Kandidaten |
| Addon → Dienst | `result` | `ok` und die `id` des Schritts. Bei `more` schickt das Addon vorher den neuen `context`. Der Dienst entscheidet dann den nächsten Schritt oder spielt den Ton |
| Addon → Dienst | `learn` | Äußerung + Befehls-ID aus dem Lernmodus |

Die Verbindung wird nur lokal angenommen, also nicht an andere Netzwerkschnittstellen gebunden. Zusätzlich gibt es ein beim Start erzeugtes Token, damit keine anderen lokalen Programme Befehle einschleusen können.

---

## 12. Technikwahl

| Baustein | Vorschlag | Alternativen |
|---|---|---|
| Spracherkennung | **faster-whisper**, Modell `small` (int8 auf der CPU, float16 auf der GPU) | whisper.cpp, Vosk (sehr schnell, aber schwächer) |
| VAD | **Silero VAD** | webrtcvad |
| Embeddings | Kleines **mehrsprachiges** Sentence-Embedding-Modell | – |
| LLM | **Ollama** mit kleinem Instruct-Modell (1–4 B Parameter), Ausgabe per JSON-Schema | llama.cpp-Server |
| Audio | **sounddevice** (PortAudio) | – |
| Addon-UI | FreeCADs `PySide`-Kompatibilitätsschicht (Qt5/Qt6) | – |
| Tests | **pytest** für `ttm_core` und den Dienst, Smoke-Tests mit FreeCAD-Stubs für das Addon | – |

Die konkreten Modelle werden in der Spike-Phase nach Latenz und Treffsicherheit auf der Zielhardware ausgewählt.

### 12.1 Mit und ohne Grafikkarte

Das System muss **mit und ohne GPU** funktionieren. Da CAD-Rechner meist eine Grafikkarte haben, ist der GPU-Betrieb der Normalfall, für den optimiert wird. Der CPU-Betrieb ist eine vollwertige Rückfallebene.

| | GPU-Profil (Standard, wenn erkannt) | CPU-Profil |
|---|---|---|
| Spracherkennung | faster-whisper `small` oder größer, float16 | faster-whisper `base`/`small`, int8 |
| Embeddings | auf der GPU | auf der CPU (klein genug) |
| LLM (Stufe 3) | 3–4 B Parameter | 1–2 B Parameter oder abgeschaltet |
| Erwartung | Auch zusammengesetzte Sätze flüssig | Einfache Befehle flüssig, Stufe 3 spürbar langsamer |

- **Automatische Erkennung:** Beim Start prüft der Dienst, ob eine nutzbare GPU vorhanden ist (CUDA, ggf. später ROCm/Metal), und wählt das Profil. Die Wahl lässt sich in den Einstellungen übersteuern.
- **Grafikspeicher wird mit FreeCAD geteilt:** Die GPU rendert gleichzeitig die 3D-Ansicht. Der Dienst bekommt deshalb ein einstellbares VRAM-Budget und wählt die Modellgrößen danach. Reicht der Speicher nicht, laufen einzelne Bausteine (z. B. das LLM) auf der CPU weiter, statt dass FreeCAD ins Stocken gerät.
- **Kein Abbruch bei fehlender GPU:** Fehlen Treiber oder CUDA-Bibliotheken, fällt der Dienst mit Hinweis in der Statusleiste auf das CPU-Profil zurück.

---

## 13. Einstellungen

Die Einstellungsseite liegt in FreeCAD unter *Bearbeiten → Einstellungen → Talk to me*
(`Gui.addPreferencePage`), flach und einfach aufgebaut:

| Reiter | Inhalt |
|---|---|
| Allgemein | Sprache, Mikrofon (Geräteliste mit Pegelanzeige), Lautstärke der Töne |
| Erkennung | Modell mit Hinweis auf Größe und Geschwindigkeit, Gerät (automatisch / CPU / GPU) mit Anzeige des gefundenen |
| Verhalten | Rückfrage-Menü (an/aus, Dauer), Sprachausgabe (Stufe, Stimme), DryRun, Pause bei inaktivem FreeCAD |
| Sprache | Listen des Sprachpakets bearbeiten (13.1), Knöpfe „Training…“ und „Wortschatz bearbeiten…“ |
| Experte | Python des Sprachdienstes, Zusatzargumente, Schwellen für Ausführen / Fehlerton / Ignorieren, Pausendauer |

- Sprache, Modell, Gerät, Mikrofon und Stimme wirken erst nach einem Neustart des Dienstes;
  die Seite startet ihn nach dem Speichern selbst neu.
- Der **Wortschatz-Editor** ist ein eigenes, größeres Fenster: eigene Phrasen und gelernte
  Formen ansehen, verschieben, löschen (auch falsch Gelerntes).

### 13.1 Sprachpakete

Alles Sprachabhängige der Erkennung liegt nicht im Code, sondern in einem Paket pro Sprache:

```
lang/de/  language.json   Füllwörter, Stoppwörter, Zahl- und Einheitswörter, Satzverbinder, Verbpartikel
          patterns.json   Satzmuster mit Lücke („den nennen wir {label}“)
          vocab.json      Synonyme, Ausweichwörter
          speech.json     Sätze der Sprachausgabe
lang/en/  …
```

- **Zwei Schichten:** das mitgelieferte Paket (nur lesbar, Verbesserungen als Beitrag ins Repo)
  und die Änderungen des Nutzers im Benutzerordner, bearbeitbar auf der Einstellungsseite.
- **Nicht jede Sprache braucht jede Liste:** Fehlt eine (Verbpartikel im Chinesischen), entfällt
  die Regel.
- **Code statt Liste**, wo Verfahren sprachabhängig sind: Lautvergleich (Kölner Phonetik für
  Deutsch, z. B. Metaphone für Englisch; ohne Verfahren nur Schreibweise), Wortstämme (z. B.
  Snowball). Sprachen ohne Leerzeichen zwischen Wörtern (Chinesisch, Japanisch) brauchen einen
  Umbau des Abgleichs, der mit Wörtern arbeitet; Arabisch eigene Normalisierung.
- **Englisch als zweites Paket** von Anfang an, um die Trennung zu prüfen.

Davon getrennt ist die **Übersetzung der Oberfläche** (Knöpfe, Statusleiste) über FreeCADs
`translate()` und Übersetzungsdateien.

---

## 14. Teststrategie

- **`ttm_core`** wird testgetrieben mit pytest entwickelt: Matching, Priorisierung, Wortschatz-Zusammenführung, Parameter-Normalisierung, Protokoll.
- **Sprachdienst:** Tests mit aufgezeichneten Audio-Beispielen pro Sprache als Regressionstests für Erkennung und Ablehnung (Abschnitt 9.3), dazu Latenzmessungen.
- **Addon:** Smoke-Tests mit gestubbtem FreeCAD unter PySide2 und PySide6, wie bei WB_Organizer. Kontext-Sammler und Ausführer werden zusätzlich manuell nach einer Checkliste in FreeCAD 1.x geprüft.
- **Korpus:** Sammlung typischer Befehle und typischer Nicht-Befehle pro Sprache, um Fehlauslösungen zu messen.

---

## 15. Fahrplan

| Phase | Inhalt | Ergebnis |
|---|---|---|
| **0 – Spike** | Dienst mit Audio + VAD + faster-whisper, Mikrofon-Button in FreeCAD, erkannten Text in der Statusleiste anzeigen, Töne | Latenz und Treffsicherheit gemessen, **jeweils im GPU- und im CPU-Profil** |
| **1 – Grundbefehle** | Kontext-Sammler, automatischer Wortschatz aus QAction-Texten, Stufe 1, Ausführen mit `runCommand` | „Rechteck“ im Sketcher funktioniert |
| **2 – Robust zuhören** | Ablehnungslogik (9.3), Kalibrierung der Schwellen, Korpus | Dauerzuhören ohne störende Fehlauslösungen |
| **3 – Anlernen** | Embeddings (Stufe 2), Lernmodus, `custom`-Dateien | Synonyme und eigene Begriffe |
| **4 – Parameter & Folgen** | LLM (Stufe 3), Parameterschemata, Undo-Transaktionen, Werkzeug-Ebene mit Folgebefehlen (6.5) | „Schließe den Sketch und polstere 12 mm auf“, „Rechteck … Breite 50, Höhe 30“ |
| **5 – Pakete & Editor** | Teilbare Workbench-Pakete, grafischer Wortschatz-Editor | Community-Erweiterbarkeit |

**Nächste Schritte (Stand 2026-10-19).** Erledigt sind Phase 0 und 1, Hilfstexte (Stufe 1b),
Befehlsfolgen, Umbenennen, Auswahl in Dialogen, Mikrofon per Stimme aus, Anzeige der
System-Stummschaltung. Reihenfolge:

1. Training (8.7) und Rückfrage-Menü (8.8)
2. Sprachpakete de und en (13.1)
3. Sprachausgabe (10.1)
4. Einstellungsseite (13)
5. Wortschatz-Editor
6. Übersetzung der Oberfläche

---

## 16. Risiken und offene Fragen

| Thema | Risiko / Frage | Gegenmaßnahme / nächster Schritt |
|---|---|---|
| Fehlauslösungen beim Dauerzuhören | Gespräche lösen Befehle aus | Dreistufige Entscheidung (9.3), Undo-Transaktion, optional Rufwort |
| Latenz im CPU-Profil | Erkennung + LLM zu langsam | Stufe 1 ohne LLM, kleinere Modelle, Stufe 3 abschaltbar (12.1) |
| GPU-Konkurrenz mit FreeCAD | Modelle belegen VRAM, 3D-Ansicht ruckelt | VRAM-Budget, Auslagern einzelner Bausteine auf die CPU (12.1) |
| Fehlende QActions | Workbenches ohne bisherige Aktivierung haben keine übersetzten Texte | Englische Rückfallebene, Wortschatz beim Aktivieren nachladen |
| Befehle mit interaktiven Dialogen | Manche Befehle öffnen Dialoge, die Eingaben erwarten | Parameter über Objekteigenschaften setzen, Dialog-Ebene (6.2) |
| Installation des Dienstes | venv, Modelle herunterladen, PortAudio | Installationsskript, später Prüfung in der Einstellungsseite |
| FreeCAD in einer Sandbox (Flatpak, Snap) | Der Sprachdienst läuft als Unterprozess mit einer venv, die auf das System-Python verweist. In der Sandbox gibt es dieses Python nicht, und der Mikrofonzugriff ist eingeschränkt | Vorerst AppImage oder Distributionspaket empfehlen (README). Später den Dienst unabhängig von FreeCAD starten (eigener Autostart, FreeCAD verbindet sich nur per Socket) oder als eigenständiges Paket ausliefern |
| Veraltete FreeCAD-Versionen aus Distributionen | `apt install freecad` liefert unter Ubuntu 22.04 / Mint 21 FreeCAD 0.19 (2021). Dort fehlt z. B. `QtWidgets` in FreeCADs PySide-Schicht | Rückfall auf `QtGui` (`talktome/qt.py`), Tests gegen die 0.19-Schicht. Zielversion bleibt 1.x |
| GPU-Hersteller | CUDA (NVIDIA) ist am besten unterstützt, AMD/Intel/Apple weniger | Zunächst CUDA + CPU, andere Backends später prüfen |
| Name des Repo-Ordners | `TalkToMe` (ohne Leerzeichen), Anzeigename „Talk to me“ | Bei Bedarf umbenennen |
