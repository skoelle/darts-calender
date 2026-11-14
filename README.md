# 🎯 Darts Kalender

Ein schlanker Turnierkalender für die PDC-Saison — als Webseite, als JSON und als
abonnierbarer ICS-Kalender. Die Termine werden automatisch eingesammelt und täglich
neu aufgebaut.

## ✨ Funktionen

- 📅 **Karten- und Tabellenansicht** mit Umschalter
- 🔴 **Matchday-Status**: Turniertage, Countdown und "Als nächstes"-Liste
- 🏷️ **Filter** nach Sender und Serie (Majors, European Tour, World Series …)
- 🏆 **Order of Merit** direkt verlinkt — aus der Saison-Karte und im Hero bei
  Majors und European-Tour-Events
- 📆 **ICS-Abo** (`webcal://`) inklusive Kopier- und Download-Button
- 📱 **Responsive** Layout mit Burger-Menü auf kleinen Bildschirmen
- 🚀 **Automatischer Build** per GitHub Action inklusive Deploy

## 🖼️ Screenshots

Kartenansicht:

![Kartenansicht](docs/screenshot-karten.png)

Tabellenansicht:

![Tabellenansicht](docs/screenshot-tabelle.png)

## 📦 Ausgaben

| Datei        | Zweck                                   |
| ------------ | --------------------------------------- |
| `index.html` | Webseite mit eingebetteten Termindaten  |
| `darts.json` | Rohdaten als JSON                       |
| `darts.ics`  | Kalender zum Abonnieren oder Importieren |

## 🛠️ Nutzung

```bash
python3 -m venv .venv      # optional, nur Standardbibliothek nötig
./run.sh
```

Alternativ direkt:

```bash
python3 fetch_termine.py --out-dir dist --html-out dist/index.html
```

Optionen wie `--source`, `--et-source` oder `--layout` erlaubt die Arbeit mit
lokalen Kopien; ein Blick in `--help` lohnt sich.

## 🗂️ Aufbau

- `fetch_termine.py` — Abruf, Aufbereitung, JSON- und ICS-Erzeugung
- `layout.html` — Template der Webseite, wird mit den Termindaten befüllt
- `blacklist.txt` — Einträge, die nicht übernommen werden
- `run.sh` — Build-Skript für den täglichen Lauf
- `.github/` — Workflow für Build und Deploy

## ⚠️ Hinweis

Die Daten werden automatisch übernommen und ohne Gewähr bereitgestellt.
Terminverschiebungen der Veranstalter sind jederzeit möglich.
