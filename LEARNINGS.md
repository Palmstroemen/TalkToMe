# Talk to me – Learnings

Was uns bei der Entwicklung von „Talk to me“ (Sprachsteuerung für FreeCAD, Oktober 2026)
begegnet ist, und worauf man bei einer ähnlichen Neuentwicklung achten sollte. Gedacht als
Grundlage für eine Sprachsteuerung auf Betriebssystemebene („Verschiebe dieses File in das
Projekt XY“, „Gehe in das Projekt YZ“, „Zeige die neuesten Fotos aus 2026“).

Gruppiert in:

1. **Allgemein:** gilt für jede Sprachsteuerung einer Anwendung
2. **Folgen des kleinen Spracherkennungsmodells:** vieles davon wird mit einem größeren Modell oder einer GPU kleiner
3. **FreeCAD-spezifisch**
4. **Übertrag auf die Betriebssystemebene**
5. **Checkliste**

Rahmen der Erfahrungen: CPU-Laptop (i7-8665U, keine CUDA-GPU), faster-whisper `tiny`/`base`
(int8), Silero-VAD, Piper für die Sprachausgabe, alles lokal; Deutsch als Hauptsprache, Englisch
als zweite; FreeCAD 1.1.4 als AppImage.

---

## 1. Allgemein: Sprachsteuerung für Anwendungen

### 1.1 Architektur

- **Zwei Prozesse lohnen sich.** Die Anwendung (hier das FreeCAD-Addon) bleibt dünn: Kontext
  einsammeln, Befehle ausführen. Ein eigener Sprachdienst hat Mikrofon, VAD, Spracherkennung,
  Entscheidung und Sprachausgabe. So stören Modelle, Abhängigkeiten und Abstürze die Anwendung
  nicht, und der Dienst läuft mit eigenem Python (FreeCADs Python kennt z. B. `sounddevice` nicht).
- **Verbindung:** JSON-Zeilen über TCP auf `127.0.0.1` mit einem Token beim Start. Einfach zu
  debuggen, sprachneutral.
- **Die Entscheidungslogik gehört in einen Kern ohne Abhängigkeiten** (`ttm_core`: nur
  Standardbibliothek). Er wird vom Dienst und vom Addon genutzt und ist ohne Mikrofon, Modell oder
  Anwendung testbar. Das war die Grundlage für über 500 Tests, die in unter einer Minute laufen.
- **Dieselbe Funktion für Dienst und Tests:** Die Logik „ganze Äußerung → Schritte“ (Gerede
  erkennen, exklusive Befehle, Werte für ein laufendes Werkzeug) stand zuerst im Dienst, vermischt
  mit dem Senden. Herausgezogen als reine Funktion prüfen die Tests genau das, was der Dienst tut.
- **Der Dienst bekommt alle Hardware als Parameter** (Quelle, VAD, Erkenner, Lautsprecher,
  Stimme). Tests laufen mit Attrappen; ein Werkzeug (`tools/try_talktome.py`) nutzt den echten
  Dienst ohne die Anwendung.
- **Protokoll in Schritten statt „ein Satz, ein Befehl“:** Der Dienst schickt einen Schritt
  (`plan` mit `id`), die Anwendung führt aus, schickt den **neuen Kontext** und dann `result`.
  Erst dann wird der nächste Schritt entschieden. Ohne das geht keine Befehlsfolge, weil sich die
  verfügbaren Befehle mit jedem Schritt ändern.
- **Umgebung des Dienstes säubern:** Eine Anwendung, die ihr eigenes Python mitbringt
  (AppImage), vererbt `PYTHONHOME` usw. an Kindprozesse. Der Dienst startete dadurch mit dem
  falschen Python und stürzte sofort ab.

### 1.2 Dauerzuhören

- **VAD (Silero) trennt Sprache von Geräusch** zuverlässig; Lüfter, Tastatur, Klicks bleiben
  draußen. Stimmen im Raum sind für sie aber Sprache. Ein Headset hilft; eine Mindestlautstärke
  wäre die nächste Stufe.
- **Segmentierung mit Vorlauf:** Ein Puffer vor dem erkannten Sprachbeginn verhindert
  abgeschnittene Satzanfänge. Satzende nach etwa 0,6 s Stille; das ist der feste Teil der Latenz.
- **Nicht sich selbst hören:** Während Töne oder Sprache laufen, ist das Mikrofon taub. Aber
  **nicht den Segmentierer zurücksetzen**: Frames in dieser Zeit als Stille behandeln, sonst geht
  der Anfang eines Satzes verloren, der während des Tons beginnt („Ansicht von vorne“ → „von“).
- **Stummschaltung des Systems erkennen:** Ein per Taste stummgeschaltetes Mikrofon liefert
  **exakte Nullen**; echtes Rauschen ist nie genau null. Nach 0,5 s Nullen ist der Zustand
  „stumm (System)“ sicher. (Ein vermeintliches Flackern beim Stream-Start war in Wahrheit der
  Nutzer, der die Taste gedrückt hat. Messungen mit dem Nutzer abstimmen.)
- **Mikrofon aus per Sprache** („kurze Pause“, „Mikro aus“) großzügig erkennen: Ein Fehlalarm
  ist harmlos. Ein solcher Befehl muss **exklusiv** sein: „Ok, kurze Pause“ darf in einem Dialog
  nicht zuerst OK drücken. Zum Einschalten gibt es bewusst keinen Sprachbefehl.

### 1.3 Entscheiden: lieber nichts tun als das Falsche

- **Drei Ausgänge statt zwei:** ausführen / nicht verstanden (Fehlerton oder Rückfrage) /
  **ignorieren** (Gerede, still). Ohne „ignorieren“ ist Dauerzuhören unerträglich.
- **Lange Sätze sind gefährlich:** Je mehr Wörter, desto mehr Zufallstreffer gegen hunderte
  Befehlsnamen („schon“ ≈ „Cone“, „einen“ ≈ „Einfügen“). Regeln, die geholfen haben:
  - Ein ganzer Satz, der als Gerede gilt, wird als Ganzes ignoriert (sonst wirken seine kurzen
    Reste wie Befehlsversuche).
  - Abschnitte nur aus Stoppwörtern treffen keinen Befehl („und“ klang wie „Undo“).
  - Ein Name, der nur einen kleinen Teil des Satzes erklärt, verliert gegen eine Beschreibung,
    die den ganzen Satz erklärt. *Lücke, die erst der Korpus zeigte:* Passte keine Beschreibung,
    wurde der schwache Namenstreffer doch ausgeführt.
- **Gespräch und Befehl unterscheiden sich sprachlich, nicht in der Ähnlichkeit.** Gespräch
  *beschreibt* Bestehendes („**Der** Kreis **ist** zu groß“, „Die Bohrung **sitzt** falsch“, „**Wie**
  spät ist es“, „**glaube** ich“, „I **made** …“), ein Befehl *will* etwas („Ich brauche hier
  **einen** Kreis“, „Mach eine Bohrung“). Eine Liste von **Aussagewörtern** im Sprachpaket
  (Hilfsverben, Zustandsverben, Fragewörter, Meinungsverben) senkte die Fehlauslösungen bei
  Gesprächen mit Fachwörtern von 10 auf 0, ohne einen der langen, natürlichen Befehle zu
  verlieren. Ab 3 Wörtern gilt so ein Satz als Gespräch; steht daneben ein Teilsatz mit
  erkanntem Befehl, gilt nur dieser („Die Skizze ist fertig, Skizze verlassen“). Preis: Befehle
  in Frageform („Wie wäre es mit einer Fase?“) werden ignoriert.
- **Zufällige Sicherheit ist keine.** „Symmetrisch“ klang wie „Isometrisch“, wurde aber nie
  ausgeführt, weil zwei Ansichtsbefehle gleichauf lagen und die Mehrdeutigkeitsprüfung griff.
  Nachdem ein Fehler in der Kandidatenliste behoben war, blieb nur einer übrig, und er wurde
  ausgeführt. Korrekturen an einer Stelle können Schutz an einer ganz anderen entfernen; nur ein
  breiter Korpus zeigt das.
- **Mehrdeutigkeit erkennen:** Zwei Kandidaten auf derselben Ebene, knapp beieinander → nicht
  raten. Ausnahme: Ist eine Phrase in der anderen enthalten („Part“ vs. „Part Design“), gewinnt
  die längere.
- **Kontextebenen** (Dialog > Bearbeitung > Arbeitsbereich > global) mit kleinem Bonus. Was im
  offenen Dialog angeboten wird, ist fast immer gemeint.
- **Nicht verfügbare Befehle** nicht still verwerfen, sondern sagen, *dass* sie gemeint waren
  („Vertiefung geht gerade nicht“). In Tests zählt das als **richtig erkannt**: „Rückgängig“ in
  einem neuen Dokument ist kein Fehler der Erkennung.

### 1.4 Wörter vergleichen

- **Drei Stufen haben sich bewährt:** unscharfer Vergleich mit Phrasen → Lautvergleich →
  Vergleich mit den **Hilfetexten** der Befehle. Die Anwendung hat diese Texte ohnehin
  (Tooltips/Statustexte), übersetzt, für jeden Befehl. „Extrudiere das und ziehe es vom Körper
  ab“ findet so die *Vertiefung*, ohne dass ihr Name fällt.
- **Lautvergleich pro Sprache:** Kölner Phonetik (Deutsch), Metaphone (Englisch). Ohne ihn
  wechselte „Pat“ (gemeint: Pad) in einen falschen Arbeitsbereich.
- **Lautvergleich-Fallen:**
  - Einzelne Wörter klingen wie andere: „Ebene“ = „oben“ (beide 016) machte jede Ebene zur
    XY-Ebene, weil „oben“ ein Synonym war. Synonyme als **Wortgruppe** („von oben“).
  - **Fremdsprachige Bezeichnungen** (FreeCADs englische Befehlsnamen) nie mit den Lautregeln der
    Nutzersprache vergleichen: „Ebene“ klang deutsch wie „Open“.
- **Komposita und Leerzeichen:** „Part Design“ vs. „PartDesign“, „Körper 2“ vs. „Körper2“ →
  auch ohne Leerzeichen vergleichen.
- **Wortstämme** für Beschreibungen („extrudiere“ = „extrudiert“), **trennbare Verben** im
  Deutschen („zieht … ab“ = „abziehen“; der Unterschied zwischen Vertiefung und Aufpolsterung).
- **Beschriftungen haben gemeinsame Enden, die nichts unterscheiden:** Im Sketcher heißen zehn
  Befehle „… festlegen“ („Parallel festlegen“), im Englischen „… Constraint“, dazu „… um
  Mittelpunkt“. Man sagt einfach „Parallel“, und das erklärte nur die Hälfte der Beschriftung.
  Allgemeine Lösung: Ein Ende, das mindestens 3 Beschriftungen eines Kontexts teilen, ergibt eine
  **Kurzform** ohne dieses Ende; bei gleichen Kurzformen bekommt sie der erste Befehl (bei Gruppen
  die Voreinstellung). **Aber:** Im Englischen ist das gemeinsame Ende oft das *Objekt* („Edit
  **Sketch**“, „Fit **Selection**“), übrig bleibt ein nacktes Verb („Fit“ ≈ „first“). Darum zählen
  Kurzformen nur als ganze Äußerung oder exakt geschrieben im Satz.
- **Seltene Wörter gewichten, aber nicht allein entscheiden lassen:** „machen“ kam nur im
  Hilfetext von „Rückgängig“ vor; „mach eine Skizze“ wurde zu Rückgängig. Mindestens zwei
  erklärte Wörter verlangen; generische Verben als Stoppwörter.

### 1.5 Mehr als ein Befehl: Folgen, Parameter, Bezüge

- **Teilsätze statt Sätze:** An Satzzeichen und „und/dann/danach“ trennen, dann Schritt für
  Schritt im jeweils neuen Kontext entscheiden. Ein Befehl kann sich über Teilsätze ziehen; ein
  weiterer Teilsatz gehört nur dazu, wenn er **für denselben Befehl** etwas beiträgt.
- **Kontextwechsel sind eigene Schritte** (Wechsel des Arbeitsbereichs): Was danach kommt, ist
  erst im neuen Kontext verfügbar.
- **Nachfragen aus demselben Teilsatz beantworten:** „Mach eine Skizze in der XY-Ebene“ – der
  Befehl öffnet einen Auswahldialog, der Rest des Teilsatzes ist die Antwort. Ebenso Werte:
  „Zeichne ein Rechteck 50 mal 30“, „Aufpolsterung 12 mm“.
- **Werte, die vor ihrem Feld kommen, festhalten** (das Feld erscheint erst nach dem ersten
  Klick) und dann eintragen.
- **Wartet ein Werkzeug auf Werte, sind reine Wertangaben immer Werte.** „Breite 50, Höhe 30“
  wechselte den Arbeitsbereich, weil „Breite“ wie „Part“ klingt. Ein Teilsatz nur aus Zahlen,
  Wertnamen, Einheiten und Füllwörtern ist dann eine Eingabe, egal wie sehr er nach einem Befehl
  klingt; mehrere davon hintereinander sind ein Schritt. Kontextwechsel (Arbeitsbereich) werden
  währenddessen gar nicht angeboten.
- **Freier Text als Parameter** („Den nennen wir Bodenplatte“) lässt sich nicht unscharf
  vergleichen → **Satzmuster mit Lücke**, pro Sprache.
- **Zahlen:** Artikel sind auch Zahlwörter („**ein** Rechteck“ ≠ 1) → nur mit Einheit danach oder
  Namen davor. Einheiten, Winkel („30 Grad“) und benannte Werte („Höhe 30 Breite 50“) aus dem
  Sprachpaket. Werte nach Art verteilen (Längen ↔ Winkel), nicht nach einer Liste pro Werkzeug.
- **Bezüge („das“, „den“, „dieses File“) brauchen eine Rangfolge**, z. B.: offener Dialog → in
  derselben Äußerung erzeugt → Auswahl → in Bearbeitung → zuletzt erzeugt → aktives Objekt.
- **Benannte Objekte so suchen, wie man sie vorliest:** „Körper zwei“ = „Körper 2“ = „Körper002“
  (Zahlwörter → Ziffern, führende Nullen weg); unscharf ja, aber **Zahlen müssen exakt stimmen**.

### 1.6 Lernen statt Sonderregeln

- **Sonderregeln für einzelne Verhörer sind eine Falle.** Eine Regel für das gesprochene
  „Ypsilon“ funktionierte für einen Nutzer, wäre aber für andere Stimmen, Modelle und Sprachen
  falsch. Besser: **pro Nutzer lernen, wie die Erkennung ihn hört.**
- **Gespeichert wird der tatsächlich erkannte Text** („X-Upsilom-Ebene“ bedeutet XY-Ebene), als
  „gehörte Form“, mit Lautvergleich, damit auch ähnliche Verhörer passen.
- **Gelernte Formen nicht als Hinweiswörter an die Erkennung geben**, sonst erzieht man sie zu
  den Fehlern.
- **Konflikte prüfen:** Eine Aufnahme, die einen *anderen* Befehl trifft, wird nicht gelernt.
- **Lernen nebenbei:** Ein Rückfrage-Menü neben dem Mauszeiger („meintest du 1 … 2 …“), per Maus
  oder Stimme („die zweite“) wählbar. **Die Wahl ist das Training.** Es darf weder Maus noch
  Tastatur fangen (laufende Werkzeuge nicht unterbrechen).
- **Gezieltes Training mit Führung:** Liste der nicht verstandenen Sätze mit Spalte „gemeint“,
  oben „noch einmal sagen“, unten Befehl wählen, sofort speichern, „vergessen“ möglich. Der erste
  Entwurf ohne Hilfetexte und Zuordnungsspalte war für den Nutzer unverständlich.
- **Befehle mit Parameter lernen Satzmuster:** „Nenndas Bodenplatte“ + „welcher Teil ist der
  Name?“ → `nenndas {label}`.
- **Ein Editor zum Aufräumen** (löschen, falsch Gelerntes zum richtigen Befehl verschieben) gehört
  dazu.
- **Ein Knopf genügt.** Ein zweiter Symbolleisten-Knopf für das Training (Mikrofon mit Haken)
  verwirrte neben dem Mikrofon. Das Training kommt von selbst (Rückfrage-Menü), per Sprache
  („Lass uns das mal trainieren“) oder aus den Einstellungen.

### 1.7 Rückmeldung

- **Töne für das Alltägliche, Sprache für die wichtigen Momente** (nicht verstanden, Rückfrage,
  Training, abgebrochene Folge). Drei Stufen (aus / wichtig / gesprächig).
- **Piper** ist lokal und schnell genug: 50–120 ms für einen kurzen Satz auf der CPU; feste
  Sätze vorab erzeugen und zwischenspeichern; Stimme im Hintergrund laden, bis dahin Töne.
- **Lizenzen von Stimmen beachten:** Frei sind z. B. Thorsten (de, CC0) und LJSpeech (en,
  gemeinfrei). Stimmen aus Spielen oder Filmen (GLaDOS) nicht mitliefern; der Nutzer kann sie
  selbst wählen.
- **Statusleiste:** gehörter Text → Befehl. Unverzichtbar beim Testen und Anlernen.

### 1.8 Sprachen

- **Sprachpakete statt Listen im Code:** Füllwörter, Stoppwörter, Zahl- und Einheitswörter,
  Satzverbinder, Verbpartikel, Satzmuster, Synonyme, Sätze der Sprachausgabe; dazu der *Name* des
  Laut- und Stammverfahrens (die bleiben Code). Benutzeränderungen getrennt davon.
- **Die Trennung früh mit einer zweiten Sprache prüfen.** Englisch war mit 30 Tests gegen echte
  englische Anwendungsdaten der Nachweis.
- **Sprachen ohne Leerzeichen** (Chinesisch, Japanisch) brauchen einen Umbau, nicht nur Listen:
  Alles arbeitet mit Wörtern und Wortgruppen.
- **UI-Übersetzung ist ein anderes Thema** als die gesprochene Sprache und folgt der
  Anwendungssprache.
- **Varianten und Dialekte erben** von einem Basispaket und enthalten nur Abweichungen
  (`de` → `de-AT` → Benutzer), mit klaren Mischregeln (Liste ersetzen oder mit `+` ergänzen,
  Tabellen mischen, Phrasen der Variante zuerst). Die Erkennung bekommt die Basissprache
  (Whisper kennt `de`, nicht `de-AT`).
- **Manches hängt am Modell, nicht an der Sprache:** gehörte Formen, was das Modell weglässt
  oder erfindet, Schreibweisen von Zahlen. Das ist eine zweite Achse neben der Sprache
  (Modellprofile); gelernte Formen sollten das Modell mitspeichern.

### 1.9 Entwicklung und Tests

- **Testgetrieben mit reinem Kern** zahlte sich aus: viele Umbauten (Sprachpakete, Folgen,
  Vorrangregeln) liefen ohne Rückschritte, weil die bestehenden Tests unverändert grün bleiben
  mussten.
- **Echte Daten als Testdaten:**
  - **Kontexte der echten Anwendung aufzeichnen** (alle Befehle mit Texten, Hilfetexten, aktiv/
    inaktiv). Fast alle Fehler bei langen Sätzen zeigten sich *nur* mit den ~80 echten
    Kandidaten, nie mit kleinen handgeschriebenen Listen.
  - **Transkripte der echten Stimme des Nutzers** als Testfälle („X-Upsilom-Ebene“).
- **Synthetische Stimme (Piper) für Durchläufe von Ende zu Ende**, aber **kein Ersatz** für die
  echte Stimme: Sie spricht manche Wörter schlecht aus, die Ergebnisse weichen deutlich ab.
- **Mit der Kunststimme gefundene Probleme mit dem Nutzer gegenprüfen**, bevor man Regeln baut.
- **Latenz messen, nicht schätzen.** Eine Befehlsfolge entschied dieselben Wortgruppen bis zu
  zehnmal; Zwischenspeichern der Vergleiche brachte 0,8 s → 0,2 s, ohne Ergebnisänderung.
- **Den Nutzer schützen:** Testläufe mit einer Kopie seiner Konfiguration; seine Daten und sein
  Mikrofonzustand werden danach wiederhergestellt; nichts ungefragt herunterladen, was er schon
  hat.

### 1.10 Der Wahrheitskorpus

Der wichtigste Baustein der zweiten Hälfte: Sätze mit dem Ergebnis, das sie liefern müssen,
gespielt in aufgezeichneten Zuständen der Anwendung. Er hat in kurzer Zeit mehr gefunden als
alle Einzeltests zuvor.

- **Kontexte als Rohdaten aufzeichnen,** ohne Wortschatz. Unsere ersten aufgezeichneten
  Kontexte enthielten die Synonyme schon; eine Änderung am Wortschatz wäre im Test unsichtbar
  geblieben. Jeder Lauf baut die Kandidaten aus Rohdaten plus aktuellem Paket.
- **Ergebnisse nach Schaden ordnen:** richtig < nachgefragt < verpasst < auf Gespräch reagiert <
  Falsches ausgeführt. Ein „bestanden/durchgefallen“ verdeckt, *wie* schlimm etwas ist.
- **Bekannte Schwächen markieren** (mit Notiz) statt Tests abzuschalten: Sie stehen in jedem
  Bericht, brechen die Tests aber nicht. **Und Alarm schlagen, wenn eine bekannte Schwäche
  plötzlich richtig ist**, damit die Markierung nicht veraltet.
- **Gesprächssätze sind der wertvollste Teil.** Sätze beim Arbeiten mit Fachwörtern darin („die
  Kante ist zu scharf“) fanden die meisten Fehlauslösungen. Ebenso wichtig: lange, natürliche
  Befehle als Gegenprobe, damit eine Verschärfung nichts Nützliches abschneidet.
- **Der Korpus findet nur, was er an Sätzen hat.** Ein absichtlich schädlicher Vorschlag fiel
  nicht auf, weil der einzige betroffene Satz schon falsch war.
- **Vorher/nachher-Vergleich** mit den Korrekturen eines Nutzers prüft, ob ein geteilter
  Vorschlag etwas verschlechtert, bevor er in ein Paket kommt.
- **Abdeckung pro Befehl** als Sicht auf den Korpus: Wie viele *verschiedene* Formulierungen
  (nach bedeutungstragenden Wörtern, „Mach eine Fase“ = „Fase“) werden erkannt, **ohne sich selbst
  im Wortschatz** (sonst misst man Auswendiglernen), mit welchem Abstand zum nächsten Befehl und
  **womit verwechselbar**. Daraus eine Ampel; der Name der Anwendung zählt als Grundausstattung.
- **Neue Kontexte decken Fehler im Einsammeln auf:** Erst die neu aufgezeichneten Kontexte
  zeigten, dass Gruppen-Buttons nie zerlegt wurden (3.2).

### 1.11 Community

- **Beitragen ohne Code ermöglichen:** Sprachpakete sind Daten, Kontexte nimmt ein Makro auf,
  der Korpus ist eine Textdatei. Ein Prüfwerkzeug (`check_pack`) sagt Schritt für Schritt, was
  fehlt, statt eine lange Anleitung vorauszusetzen.
- **Anleitung mit einem durchgespielten Beispiel** (Französisch von null bis zum Pull Request)
  und echten Ausgaben, nicht abstrakt.
- **Issue-Vorlagen fragen nach dem Gehörten**, nicht nur dem Gesagten, plus Sprache, Modell,
  Version und Zustand der Anwendung. Daraus wird fast unverändert ein Korpus-Fall.
- **Korrekturen der Nutzer sind der Rohstoff,** aber nie automatisch übernehmen: anzeigen,
  auswählen lassen, mit dem Korpus prüfen. Datenschutz: Objektnamen im Kontext sind sichtbar
  und editierbar.
- **Ideen für Trainingsspiele** (noch nicht gebaut): Karten mit den schlecht abgedeckten Befehlen
  zuerst, Beispiele anderer erst *nach* dem eigenen Versuch (sonst wird nachgesprochen); und
  „bedienen und dazu sprechen“: Der Klick auf ein Werkzeug ist die Grundwahrheit für den Satz
  davor, das System beobachtet nur und führt nichts aus.

---

## 2. Folgen des kleinen Spracherkennungsmodells

Wir haben bewusst das kleinste schnelle Modell genommen (`tiny`/`base` auf der CPU, ~0,5–1 s
Erkennung; `small` brauchte 2,7 s und war zu langsam). Was davon ein Modellproblem ist:

| Beobachtung | Mit größerem Modell / GPU | Unsere Lösung |
|---|---|---|
| Fachbegriffe verhört: „Rechteck“ → „Richtig“, „Fase“ → „Phase“, „Skizze“ → „Gizze“ | deutlich seltener, Homophone bleiben („Fase“/„Phase“) | Hinweiswörter aus dem Kontext, Lautvergleich, Training |
| Buchstaben diktieren („XY-Ebene“): „Exerzielern eben“, „Upsilom“, „Öpsilon“ | besser, bleibt schwierig | Ausweichwörter („von oben“), Training, Rückfrage-Menü |
| Hinweiswörter erzeugen Befehle, die nicht gesagt wurden („Rückgängig“ → „Rechteck öffnen“), oder die falsche Ebene („XZ“ statt „XY“) | seltener | Mehrdeutigkeitsprüfung, Abstand zum Zweitbesten, nie bei Unsicherheit ausführen |
| Wiederholungsschleifen („Halluzinationen“): einmal 6,9 s statt 1 s | seltener | Ausgabe auf 40 Tokens begrenzt |
| `avg_logprob` trennt richtige von falschen Treffern nicht | – | Sicherheit über die Entscheidungslogik, nicht über die Modellkonfidenz |
| Komposita/Schreibweisen schwanken („Part Design“, „PartDesigner“, „Partie sein“) | weniger | Vergleich ohne Leerzeichen, Lautvergleich |
| Satzenden ohne Punkt, Teilsätze ohne Komma | besser | Trennung zusätzlich an „und/dann“ |

**Allgemein gilt aber auch mit großem Modell:** Hinweiswörter wirken nur für den Kontext zur Zeit
des Sprechens. In einer Befehlsfolge fehlen die Wörter späterer Kontexte (die Ebenen gibt es
erst, wenn der Dialog offen ist). Eigennamen (Projekt- und Dateinamen!) bleiben schwierig.

**Empfehlung:** Mit dem kleinen Modell entwickeln, weil es die Robustheit erzwingt, aber das
Profil wählbar machen (CPU: `base`, GPU: `small`/`medium`) und mit dem Ziel-Modell messen.

---

## 3. FreeCAD-spezifisch

### 3.1 Installation und Laden

- **apt liefert alte Versionen** (Ubuntu 22.04 / Mint 21: FreeCAD 0.19). AppImage nehmen.
  Flatpak/Snap: Sandbox, der Dienst mit eigenem Python und das Mikrofon sind dort ein Problem.
- **Benutzerverzeichnis je Version:** 1.1 nutzt `~/.local/share/FreeCAD/v1-1/Mod`, nicht
  `~/.FreeCAD/Mod`.
- **`package.xml` muss den Inhalt als `<workbench>` deklarieren**, sonst führt FreeCAD 1.x die
  `InitGui.py` nicht aus (auch für ein Addon, das gar keine Workbench ist).
- **`InitGui.py` läuft per `exec` in einer Funktion:** Namen auf Modulebene verschwinden danach.
  Objekte wie Timer brauchen einen Qt-Eltern (Hauptfenster).
- **Qt5/Qt6:** FreeCADs `PySide`-Modul; `QAction` liegt in Qt6 in `QtGui`; FreeCAD 0.19 hat kein
  `QtWidgets` im Shim.

### 3.2 Befehle, Texte, Hilfetexte

- Befehle: `Gui.Command.get(id)`, `.getAction()` (übersetzte Texte), `.getInfo()` (englisch),
  `.isActive()`. **Hilfetexte** stehen übersetzt im `statusTip()` der Aktion.
- **Gruppenbefehle** (Buttons mit Menü: „Kreis / Ellipse …“) enthalten Unteraktionen. Ältere
  Versionen trugen den Befehl in der Eigenschaft `CommandName`, **FreeCAD 1.1 in `data()` und
  `objectName()`** der Aktion. Unser Code suchte nur `CommandName`; die Gruppen wurden nie
  zerlegt, alle Einträge waren Phrasen des Gruppenbefehls, und der führte seine Voreinstellung
  aus: „Ellipse“ hätte einen Kreis gezeichnet. Mehrere Quellen probieren und nur Namen
  akzeptieren, die FreeCAD als Befehl kennt. Im Sketcher sind es danach 153 statt 94 Befehle.
- `Std_Workbench` trägt die Namen *aller* Arbeitsbereiche → aus den Kandidaten nehmen.
- **„Umbenennen“ ist kein Befehl**, nur eine Aktion der Baumansicht. Selbst umsetzen (Label in
  einer Transaktion, damit Rückgängig geht).
- **Objektnamen im Baum:** der zweite Körper heißt „Körper001“, der dritte „Körper002“.
- **Mikrofon-Button als echter Befehl** (checkbarer Python-Befehl in einer globalen Toolbar), dann
  lässt sich ein Tastenkürzel zuweisen. Allein das Vorhandensein von `"Checkable"` macht ihn
  umschaltbar.

### 3.3 Dialoge und Qt

- **Aufgabendialoge werden mit ~300 ms Verzögerung eingeblendet:** `isVisible()` ist direkt nach
  dem Befehl falsch → `isVisibleTo(TaskView)`.
- **PySide6 gibt Wrapper zu früh frei:** Feld eines modalen Dialogs nur benutzen, solange man eine
  Referenz auf den Dialog hält.
- **Qt-Elementdaten speichern Kopien** von Python-Dicts → nur IDs ablegen.
- **Der Einstellungsdialog ist modal:** Fenster, die man von dort öffnet, müssen seine Kinder
  sein, sonst sind sie gesperrt.
- **Icon einer Einstellungsgruppe:** `preferences-<gruppe_kleingeschrieben>.svg` im Icon-Pfad.
  FreeCAD-Icons folgen dem Tango-Stil (Verlauf, Kontur, Glanzlicht).

### 3.4 Sketcher und PartDesign

- **Läuft ein Sketcher-Werkzeug?** Dann ist `SketcherGui::TaskSketcherTool` sichtbar. *Welches*,
  verrät es nicht.
- **Werte gehen in 1.1.4 in Felder in der 3D-Ansicht** (On-View-Parameter), die mit der Vorgabe
  erst **nach dem ersten Klick** erscheinen. Eingabe: Feld mit Fokus, Enter, Fokus wandert.
  Felder tragen ihre Einheit (`mm`/`°`). **Escape zweimal an die Ansicht** beendet das Werkzeug.
- **Der Kreis fragt nach dem Durchmesser**, nicht nach dem Radius.
- **PartDesign-Dialoge:** Text ins Feld schreiben genügt bei der Aufpolsterung nicht → Wert über
  `rawValue` setzen; der Dialog bleibt offen, OK beim Nutzer.
- **Bemaßungen haben Namen** (für Ausdrücke) → ohne Leerzeichen; der Bemaßungsdialog ist modal,
  hat aber ein Namensfeld.

### 3.5 Testen ohne Bildschirm

- Das AppImage läuft mit `QT_QPA_PLATFORM=offscreen` und einer **Kopie** der Konfiguration
  (`--user-cfg`); ein Skript als Argument wird nach dem Start ausgeführt. So ließen sich Dialoge,
  Werkzeuge, Mausklicks (simulierte Ereignisse), Bildschirmfotos und sogar die echte
  Spracherkennung mit Piper-WAV-Dateien prüfen, ohne den Nutzer zu stören.

---

## 4. Übertrag auf die Betriebssystemebene

### 4.1 Was sich übernehmen lässt

Fast alles aus Abschnitt 1: Dienst mit VAD/Erkennung/Sprachausgabe, die Entscheidung mit
„ignorieren“, Lautvergleich, Teilsätze und Schritte mit Kontext-Rundlauf, Satzmuster für
Parameter, Bezugs-Rangfolge, Lernen pro Nutzer, Rückfrage-Menü, Sprachpakete, Tests mit
aufgezeichneten Kontexten.

### 4.2 Was neu ist

- **Woher kommen die Kandidaten?** In FreeCAD aus dessen API. Auf Betriebssystemebene aus den
  **Barrierefreiheits-Schnittstellen**: AT-SPI (Linux), UI Automation (Windows), Accessibility API
  (macOS). Sie liefern für das aktive Fenster Schaltflächen, Menüs, Beschriftungen und oft
  Beschreibungen, also genau das, was wir aus `QAction`-Texten und Statustexten gelesen haben.
  Qualität schwankt je Anwendung.
- **Die Beispiele sind keine Befehle, sondern Aufträge mit Dingen darin:**
  - „Verschiebe **dieses File** in das **Projekt XY**“: Bezug („dieses“ = Auswahl im
    Dateimanager / Fokus / zuletzt erwähnt) und ein **benanntes Ziel**, das es zu finden gilt.
  - „Gehe in das **Projekt YZ**“: Navigation zu einem Ort, dessen Name gesprochen wird.
  - „Navigiere zu den **neuesten Fotos aus 2026**“: eine **Abfrage** (Typ = Foto, Datum = 2026,
    Sortierung = neueste), keine Auswahl aus einer Liste.
- **Entitäten statt Befehlsnamen:** Projekte, Ordner, Dateien, Kontakte. Die Hinweiswörter für
  die Erkennung kommen aus diesem Bestand (Ordnernamen der Projekte, zuletzt benutzte Dateien),
  der Abgleich wie bei „Körper2“: normalisiert, unscharf, Zahlen exakt. Ein Index hilft
  (Tracker/Baloo unter Linux, Windows Search, Spotlight).
- **Abfragen brauchen mehr als Satzmuster:** Zeit („aus 2026“, „von letzter Woche“), Art
  („Fotos“, „PDFs“), Sortierung („neueste“). Für wenige feste Formen gehen Satzmuster mit
  mehreren Lücken; für freie Formulierungen ist das die Stelle für ein kleines lokales
  Sprachmodell, das einen **strukturierten Plan** erzeugt (wie Stufe 3 im Design), der dann
  geprüft und ausgeführt wird.
- **Sicherheit wiegt schwerer:** Verschieben, Löschen, Umbenennen von Dateien sind folgenreich.
  - Vor destruktiven Aktionen ansagen und bestätigen lassen („Verschiebe 3 Dateien nach XY?“),
    oder nur dann, wenn der Treffer nicht eindeutig ist.
  - Rückgängig ermöglichen (Papierkorb statt Löschen, Protokoll der Verschiebungen).
  - Nie bei Unsicherheit ausführen; „lieber nichts tun“ gilt doppelt.
  - Ein Sprachmodell darf nur Pläne aus einem festen Befehlssatz liefern, nie direkt ausführen
    (Dateinamen und Inhalte können Anweisungen enthalten).
- **Eingaben simulieren** ist unter Wayland eingeschränkt (bewusst). Besser über die
  Anwendungen selbst: D-Bus (Dateimanager wie Nautilus/Dolphin haben Schnittstellen),
  Barrierefreiheits-Aktionen, Kommandozeile. Globale Tastenkürzel fürs Mikrofon ebenso.
- **Kontext ist das aktive Fenster:** Welche Anwendung, welche Auswahl, welcher Ordner. Ebenen wie
  bei uns: Dialog > Anwendung > System.
- **Die Beschriftungen aus den Barrierefreiheits-Schnittstellen** werden dieselben Eigenheiten
  haben wie FreeCADs Befehle: gemeinsame Enden („… öffnen“, „… Settings“), verschachtelte Menüs,
  die man zerlegen muss, Einträge ohne Text. Kurzformen und das Zerlegen von Gruppen übertragen
  sich direkt.
- **Gespräch ist auf Systemebene noch häufiger** (Telefon, Kollegen, Videokonferenz). Die
  Aussagewörter und ein Korpus mit vielen Gesprächssätzen gehören von Anfang an dazu.
- **„Bedienen und dazu sprechen“ passt hier besonders gut:** Die Barrierefreiheits-Schnittstellen
  melden Klicks und Fokuswechsel systemweit; so entstehen beschriftete Sätze aus echter Arbeit,
  in echten Kontexten, die zugleich als aufgezeichnete Kontexte für den Korpus dienen.

### 4.3 Vorschlag für den Start

1. **Ein klar abgegrenzter Bereich:** Dateien und Ordner (ein Dateimanager + Navigation). Die
   drei Beispiele decken ihn ab.
2. **Bestand als Kandidaten:** Projektordner (eine konfigurierbare Liste von Wurzeln), zuletzt
   benutzte Dateien, Lesezeichen; daraus Hinweiswörter und Abgleich.
3. **Befehle mit Lücken:** „gehe zu {Ort}“, „öffne {Datei}“, „verschiebe {Bezug} nach {Ort}“,
   „zeige {Art} aus {Zeit}“; Satzmuster pro Sprache, gelernte Muster wie hier.
4. **Bezug „dieses“** aus der Auswahl des Dateimanagers (D-Bus/AT-SPI), Rangfolge wie beim
   Umbenennen.
5. **Bestätigung bei Dateioperationen** per Sprache („Ja“ / „Nein“) und Menü neben der Maus.
6. **Danach** die Barrierefreiheits-Schnittstelle als allgemeine Quelle für Schaltflächen und Menüs
   beliebiger Anwendungen.

---

## 5. Checkliste für eine Neuentwicklung

- [ ] Kern ohne Abhängigkeiten, Dienst mit austauschbarer Hardware, Protokoll mit Schritten und
      Kontext-Rundlauf
- [ ] Drei Ausgänge: ausführen / nachfragen / ignorieren; ganze Gerede-Sätze ignorieren
- [ ] Kandidaten aus der echten Anwendung, mit Hilfetexten und Aktiv-Zustand; aufzeichnen für Tests
- [ ] Unscharf + Lautvergleich (pro Sprache) + Beschreibungen; Stoppwort-Abschnitte ausschließen;
      fremdsprachige Namen ohne Lautregeln; Synonyme als Wortgruppen
- [ ] Teilsätze, Kontextwechsel als eigener Schritt, Nachfragen aus demselben Teilsatz beantworten
- [ ] Parameter über Satzmuster, Zahlen mit Einheiten, Artikel ≠ Zahl, Bezüge mit Rangfolge
- [ ] Lernen pro Nutzer (gehörte Formen, Muster), Rückfrage-Menü als Training, Editor zum Aufräumen;
      keine Sonderregeln für einzelne Verhörer
- [ ] Sprachpakete von Anfang an, zweite Sprache früh
- [ ] Töne + Sprache in wichtigen Momenten; Mikrofon taub beim Sprechen; Stummschaltung des Systems
      erkennen
- [ ] Mit kleinem Modell entwickeln, mit Zielmodell messen; Ausgabelänge begrenzen
- [ ] Echte Nutzerstimme früh einbeziehen; Kunststimme nur für Abläufe
- [ ] Bei destruktiven Aktionen bestätigen und Rückgängig ermöglichen
- [ ] Wahrheitskorpus von Anfang an: Kontexte als Rohdaten, Ergebnisse nach Schaden geordnet,
      viele Gesprächssätze mit Fachwörtern, lange natürliche Befehle als Gegenprobe, bekannte
      Schwächen markiert (mit Alarm, wenn behoben)
- [ ] Aussagewörter (Aussage, Frage, Meinung) gegen Gespräch; nicht auf zufällige
      Mehrdeutigkeit als Schutz verlassen
- [ ] Gruppen und Menüs in ihre Einträge zerlegen und das prüfen; Kurzformen aus gemeinsamen
      Beschriftungsenden, aber nur als ganze Äußerung oder exakt
- [ ] Wartet ein Werkzeug auf Eingaben, haben reine Wertangaben Vorrang, Kontextwechsel sind
      gesperrt
- [ ] Abdeckung pro Befehl messen (verschiedene Formulierungen, ohne sich selbst, Verwechslungen)
- [ ] Varianten erben vom Basispaket; Modellabhängiges getrennt von Sprachlichem halten
- [ ] Mitmachen ohne Code: Daten statt Code, Prüfwerkzeug, Anleitung mit echtem Beispiel,
      Issue-Vorlagen mit dem Gehörten
