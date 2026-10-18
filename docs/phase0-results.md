# Phase 0 – Messergebnisse

Stand: 18.10.2026 · Rechner: Dell-Laptop, Intel Core i7-8665U (4 Kerne/8 Threads), Intel UHD 620, keine CUDA-GPU → **CPU-Profil**

## Testaufbau

- 20 deutsche Befehle aus `tools/phrases_de.txt`
- **Synthetische Stimme** (Piper, Stimme „thorsten“), keine echte Aufnahme. Die Ergebnisse mit echter Stimme können deutlich abweichen. Messungen mit eigener Stimme: `tools/measure_stt.py record`.
- faster-whisper 1.2.1, int8, beam 1, Sprache fest `de`
- „Befehlstreffer“: Der erkannte Text führt über `ttm_core.matching` (Schwelle 0,75) zum richtigen Testbefehl aus `tools/test_commands_de.json`. Bei zwei Sätzen ohne Testbefehl ist „kein Treffer“ richtig.

## Ergebnisse

| Modell | Hotwords | Befehlstreffer | Erkennung Ø | Erkennung max | Wortfehlerrate |
|---|---|---|---|---|---|
| tiny  | nein | 12/20 | 0,53 s | 1,3 s | 0,75 |
| tiny  | ja   | 17/20 | 0,55 s | 1,4 s | – |
| base  | nein | 16/20 | 0,93 s | 2,4 s | 0,58 |
| base  | ja   | 18/20 | 1,34 s | **6,9 s** | – |
| small | nein | 17/20 | 2,71 s | 3,1 s | 0,37 |
| small | ja   | 18/20 | 2,86 s | 3,7 s | – |

Die gefühlte Antwortzeit ist etwa **0,64 s Pausenerkennung + Erkennungszeit**.

## Erkenntnisse

1. **`small` ist auf dieser CPU zu langsam** (≈ 3,3 s gefühlt). Realistisch sind `tiny` und `base`.
2. **Hotwords bringen viel:** Mit dem Kontext-Wortschatz als Hinweis steigt `tiny` von 12 auf 17 Treffer. Das bestätigt Abschnitt 6.5 des Designs.
3. **Hotwords können aber falsche Befehle erzeugen:** „Rückgängig“ wurde zu „Kreis, gängig“ (→ Kreis) bzw. „Rückansicht“ (→ Rückansicht). Ein falsch ausgeführter Befehl ist schlimmer als keiner (Grundprinzip 4), also braucht es eine Konfidenzprüfung, z. B. über `avg_logprob`, bevor ausgeführt wird.
4. **Ausreißer:** `base` mit Hotwords brauchte einmal 6,9 s (Whisper „halluziniert“ in einer Schleife). Nötig ist eine Obergrenze für die Länge der Ausgabe bzw. ein Zeitlimit.
5. **Homophone:** „Fase“ wird als „Phase“ erkannt, mit jedem Modell. Das ist ein Fall für die Übersetzungstabelle bzw. den Lernmodus (Abschnitt 8.4).
6. **Stummschaltung nach dem Ton** hat Satzanfänge abgeschnitten, wenn direkt nach einem Befehl weitergesprochen wurde. Behoben: Frames während des Tons bleiben im Vorlaufpuffer (Test `test_speech_starting_during_tone_keeps_its_beginning`).
7. **Audioausgabe unter Linux:** Die ALSA→PulseAudio-Brücke meldet sporadisch Pufferunterläufe („underrun occurred“). Gemildert durch einen dauerhaft offenen Ausgabestream mit 0,1 s Latenz, aber nicht ganz beseitigt.

## Nächste Schritte

- **Messung mit echter Stimme:** `tools/measure_stt.py record` und `bench`.
- **Standardmodell im CPU-Profil:** vorerst `base`, `tiny` mit Hotwords als schnelle Alternative prüfen.
- **Zeitlimit und Konfidenzschwelle** vor Phase 1 einbauen.

## Nachtrag: Klangähnlicher Abgleich + Hotwords + Längenbegrenzung

Gleiche 20 synthetische Sätze, Abgleich jetzt mit Kölner Phonetik (`language="de"`), Zahlen und Einheiten werden beim Abgleich ignoriert, Whisper-Ausgabe auf 40 Tokens begrenzt.

| Modell | Hotwords | Befehlstreffer vorher → jetzt | **Falsche** Befehle | Erkennung Ø / max |
|---|---|---|---|---|
| tiny | nein | 12 → **14** | 0 | 0,52 s / 1,4 s |
| tiny | ja   | 17 → **17** | 0 | 0,52 s / 1,2 s |
| base | nein | 16 → **17** | 0 | 0,99 s / 2,5 s |
| base | ja   | 18 → **17** | **2** | 1,00 s / 1,9 s (vorher max 6,9 s) |

- **Kölner Phonetik:** reiner Gewinn. „Zeichen ein Richtig“ → Rechteck, „Phase 2 mm“ / „Faset 2 mm“ → Fase. In diesen Messungen keine Fehlauslösung.
- **Längenbegrenzung:** Der Ausreißer ist weg (max. 1,9 s statt 6,9 s).
- **Hotwords sind zweischneidig:** Bei `tiny` bringen sie +3 Treffer ohne Fehlauslösung. Bei `base` hat Whisper zweimal Wörter aus der Hinweisliste „gehört“, die nicht gesagt wurden: „Rückgängig“ → „Rechteck öffnen“, „Isometrische Ansicht“ → „Ansicht“. Das sind zwei **falsch ausgeführte** Befehle.
- **`avg_logprob` trennt die Fehlauslösungen nicht sauber** von richtigen Treffern (−0,37 und −0,77 gegenüber richtigen Treffern bis −0,92). Für die Sicherheit vor dem Ausführen (Phase 1) braucht es also mehr als eine einfache Schwelle, z. B. eine Kombination aus Abgleich-Score, Konfidenz und Zweitbestem Kandidaten.
- **Vorbehalt:** „Rückgängig“ wird von der synthetischen Stimme offenbar schlecht ausgesprochen (scheitert mit jedem Modell). Belastbar wird das erst mit echter Stimme.
