#!/usr/bin/env python3
# Copyright (c) 2026 Stefan Koelle (https://stefankoelle.de)
# Licensed under the MIT License. See LICENSE file in project root for details.
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from html.parser import HTMLParser
from pathlib import Path

URL = "https://www.darts1.de/termine/termine.php"
ET_OVERVIEW_URL = "https://www.darts1.de/european-tour/european-tour.php"
ET_ARCHIVE_URL = "https://www.darts1.de/european-tour/european-tour-{year}.php"
USER_AGENT = "darts-calender/0.1 (+https://www.moonweb.org/darts/; Darts-Turnierkalender, taeglicher Abruf)"
CATEGORY = "pdc"
DEFAULT_BLACKLIST = Path(__file__).resolve().parent / "blacklist.txt"

DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})\s*(.*)$", re.DOTALL)
ET_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
ET_NUMBER_RE = re.compile(r"PDC European Tour\s+(\d+)")
ET_RANGE_RE = re.compile(
    r"(\d{1,2})\.(\d{1,2})\.\s*bis\s*(\d{1,2})\.(\d{1,2})\.(\d{4})"
)
ET_LINK_RE = re.compile(
    r'href="(https://www\.darts1\.de/european-tour/[^"]+\.php)"[^>]*'
    r'title="([^"]*)"'
)
ET_GENERIC_URL_RE = re.compile(r"/european-tour(?:-\d{4})?\.php$")
WS_URL_RE = re.compile(r"/world-series/")


def is_world_series(item):
    if WS_URL_RE.search(item.get("url") or ""):
        return True
    titel = item["titel"]
    return "Darts Masters" in titel or "World Series" in titel

SPORT1 = "SPORT1"
PROSIEBEN = "ProSieben"
PLUTO = "Pluto.TV"
SPORT1_ODER_PLUTO = "SPORT1 oder Pluto.TV"


def _wm_2026(item):
    return "Darts-WM" in item["titel"] and item["end"] <= "2027-01-03"


def _wm_ab_2027(item):
    return "Darts-WM" in item["titel"] and item["start"] >= "2027-12-01"


def _players_finals(item):
    return "Players Championship" in item["titel"] and "Finals" in item["details"]


def _sport1_titel(item):
    text = f"{item['titel']} {item.get('event', '')}"
    return any(
        name in text
        for name in (
            "Premier League",
            "Grand Slam of Darts",
            "UK Open",
            "World Grand Prix",
            "The Masters",
            "German Open",
            "German Darts Open",
            "Super League",
        )
    )


def _sport1_oder_pluto(item):
    return "European Tour" in item["titel"]


SENDER_RULES = [
    ("wm_2026", _wm_2026, SPORT1),
    ("wm_ab_2027", _wm_ab_2027, PROSIEBEN),
    ("world_series_finals", lambda i: "World Series of Darts Finals" in i["titel"], SPORT1),
    ("players_finals", _players_finals, SPORT1),
    ("sport1_titel", _sport1_titel, SPORT1),
    ("world_series", lambda i: i.get("serie") == "world_series", PLUTO),
    ("sport1_oder_pluto", _sport1_oder_pluto, SPORT1_ODER_PLUTO),
    ("fallback", lambda i: True, PLUTO),
]


def classify_sender(item):
    for _name, predicate, sender in SENDER_RULES:
        if predicate(item):
            return sender
    return PLUTO


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def parse_et_deeplinks(html):
    mapping = {}
    ambiguous = set()
    for row in ET_ROW_RE.findall(html):
        if "European Tour" not in row:
            continue
        range_match = ET_RANGE_RE.search(row)
        if not range_match:
            continue
        day1, month1, day2, month2, year = range_match.groups()
        try:
            start = date(int(year), int(month1), int(day1))
            end = date(int(year), int(month2), int(day2))
        except ValueError:
            continue
        if end < start:
            continue
        link = None
        for href, title in ET_LINK_RE.findall(row):
            if ET_GENERIC_URL_RE.search(href):
                continue
            link = {"url": href, "name": normalize(title)}
            break
        if link is None:
            continue
        key = (start.isoformat(), end.isoformat())
        if key in mapping and mapping[key]["url"] != link["url"]:
            ambiguous.add(key)
            continue
        mapping[key] = link

    for key in ambiguous:
        mapping.pop(key, None)
    return mapping


def resolve_et_url(item, mapping):
    if "European Tour" not in item["titel"]:
        return None
    if not ET_GENERIC_URL_RE.search(item["url"]):
        return None
    return mapping.get((item["start"], item["end"])) or mapping.get(item["start"])


def load_et_mapping(overview_html, archive_htmls=None):
    sources = []
    if overview_html is not None:
        sources.append(overview_html)
    if archive_htmls:
        for html in archive_htmls:
            if html is not None:
                sources.append(html)

    combined = {}
    for html in sources:
        for key, link in parse_et_deeplinks(html).items():
            combined.setdefault(key, link)
    return combined


def enrich_with_et_deeplinks(ranges, overview_html, archive_htmls):
    mapping = load_et_mapping(overview_html, archive_htmls)
    resolved = 0
    unresolved = []
    for item in ranges:
        if "European Tour" not in item["titel"]:
            continue
        if not ET_GENERIC_URL_RE.search(item["url"]):
            continue
        hit = resolve_et_url(item, mapping)
        if hit:
            item["uebersicht_url"] = item["url"]
            item["url"] = hit["url"]
            item["event"] = hit["name"]
            resolved += 1
        else:
            unresolved.append(item)

    for item in ranges:
        item["sender"] = classify_sender(item)

    return resolved, unresolved


def load_blacklist(path):
    if not path.exists():
        print(f"Warnung: Blacklist nicht gefunden: {path}")
        return []
    patterns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        patterns.append(entry.casefold())
    return patterns


def apply_blacklist(ranges, patterns):
    if not patterns:
        return list(ranges), []
    kept = []
    removed = []
    for item in ranges:
        titel = item["titel"].casefold()
        if any(pattern in titel for pattern in patterns):
            removed.append(item)
        else:
            kept.append(item)
    return kept, removed


class TerminParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.spans = []
        self._cur = None
        self._in_anchor = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "span":
            match = re.search(r"\b([a-z]+)\s+box\b", attrs.get("class", ""))
            if match:
                self._cur = {
                    "kategorie": match.group(1),
                    "titel": "",
                    "rest": "",
                    "url": "",
                }
        elif tag == "a" and self._cur is not None:
            self._in_anchor = True
            self._cur["url"] = attrs.get("href", "")

    def handle_endtag(self, tag):
        if tag == "span" and self._cur is not None:
            self.spans.append(self._cur)
            self._cur = None
            self._in_anchor = False
        elif tag == "a":
            self._in_anchor = False

    def handle_data(self, data):
        if self._cur is None:
            return
        if self._in_anchor:
            self._cur["titel"] += data
        else:
            self._cur["rest"] += data


def parse_span(span):
    text_rest = normalize(span["rest"])
    match = DATE_RE.match(text_rest)
    if match:
        day, month, year, rest = match.groups()
        try:
            start = date(int(year), int(month), int(day))
        except ValueError:
            return None
        return {
            "datum": start,
            "titel": normalize(span["titel"]),
            "details": normalize(rest).lstrip(",").strip(),
            "url": span["url"],
        }
    if not span["titel"] and text_rest == "bis":
        return {"bis": True}
    return None


def extract_ranges(spans, category):
    entries = []
    for span in spans:
        if span["kategorie"] != category:
            continue
        parsed = parse_span(span)
        if parsed is not None:
            entries.append(parsed)

    ranges = []
    used = set()
    index = 0
    while index + 2 < len(entries):
        first, marker, last = entries[index], entries[index + 1], entries[index + 2]
        if (
            "datum" in first
            and marker.get("bis")
            and "datum" in last
            and last["datum"] >= first["datum"]
        ):
            ranges.append(
                {
                    "start": first["datum"].isoformat(),
                    "end": last["datum"].isoformat(),
                    "titel": first["titel"] or last["titel"],
                    "details": first["details"] or last["details"],
                    "url": first["url"] or last["url"],
                    "kategorie": category,
                }
            )
            used.update((index, index + 1, index + 2))
            index += 3
        else:
            index += 1

    for index, first in enumerate(entries):
        if index in used or "datum" not in first:
            continue
        if index + 1 >= len(entries) or index + 1 in used:
            continue
        last = entries[index + 1]
        if "datum" not in last:
            continue
        if first["titel"] != last["titel"] or first["details"] != last["details"]:
            continue
        if (last["datum"] - first["datum"]).days != 1:
            continue
        ranges.append(
            {
                "start": first["datum"].isoformat(),
                "end": last["datum"].isoformat(),
                "titel": first["titel"],
                "details": first["details"],
                "url": first["url"] or last["url"],
                "kategorie": category,
            }
        )
        used.update((index, index + 1))

    for item in ranges:
        if is_world_series(item):
            item["serie"] = "world_series"
        item["sender"] = classify_sender(item)

    ranges.sort(key=lambda item: (item["start"], item["end"], item["titel"]))
    return ranges


def ics_escape(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def ics_fold(line):
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]
    parts = []
    current = b""
    limit = 75
    for char in line:
        chunk = char.encode("utf-8")
        if len(current) + len(chunk) > limit:
            parts.append(current.decode("utf-8"))
            current = b" "
            limit = 75
        current += chunk
    if current:
        parts.append(current.decode("utf-8"))
    return parts


def build_ics(ranges, calendar_name):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//darts-calender//Darts Kalender//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calendar_name)}",
        "X-WR-TIMEZONE:Europe/Berlin",
    ]
    for item in ranges:
        start = date.fromisoformat(item["start"])
        end = date.fromisoformat(item["end"]) + timedelta(days=1)
        sender = item.get("sender", "")
        summary = item["titel"]
        if item["details"]:
            summary = f"{summary}, {item['details']}"
        event = item.get("event", "")
        if event and event not in summary:
            summary = f"{summary} \u2013 {event}"
        if sender:
            summary = f"{summary} [{sender}]"
        digest = hashlib.sha1(
            f"{item['start']}|{item['end']}|{item['titel']}".encode("utf-8")
        ).hexdigest()
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{digest}@darts-calender",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
                f"SUMMARY:{ics_escape(summary)}",
            ]
        )
        description = summary
        if item["url"]:
            description = f"{description}\nDetails und Quelle: {item['url']}"
        lines.append(f"DESCRIPTION:{ics_escape(description)}")
        if sender:
            categories = ",".join(
                ics_escape(part.strip()) for part in sender.split(" oder ")
            )
            lines.append(f"CATEGORIES:{categories}")
        if item["url"]:
            lines.append(f"URL:{item['url']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    folded = []
    for line in lines:
        folded.extend(ics_fold(line))
    return "\r\n".join(folded) + "\r\n"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def js_payload(ranges):
    payload = json.dumps(ranges, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return payload


def inject_data(html, payload):
    lines = html.split("\n")
    for index, line in enumerate(lines):
        if not line.startswith("const DATA="):
            continue
        end = index
        while end < len(lines) and not lines[end].rstrip().endswith("];"):
            end += 1
        if end >= len(lines):
            raise ValueError("Datenzeile in Layout nicht abgeschlossen")
        lines[index : end + 1] = [f"const DATA={payload};"]
        return "\n".join(lines)
    raise ValueError("Kein 'const DATA=' im Layout gefunden")


def build_html(ranges, layout_path):
    html = layout_path.read_text(encoding="utf-8")
    html = inject_build_time(html, build_stamp())
    return inject_data(html, js_payload(ranges))


def build_stamp():
    return datetime.now(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y %H:%M")


def inject_build_time(html, stamp):
    if "__BUILD__" not in html:
        print("Warnung: Kein '__BUILD__'-Platzhalter im Layout gefunden")
        return html
    return html.replace("__BUILD__", stamp)


def main():
    parser = argparse.ArgumentParser(
        description="Liest PDC-Zeitraeume (Start/bis/Ende) von darts1.de aus."
    )
    parser.add_argument("--url", default=URL)
    parser.add_argument("--source", type=Path, help="Lokale HTML-Datei statt Download")
    parser.add_argument(
        "--et-source", type=Path, help="Lokale HTML-Datei der European-Tour-Uebersicht"
    )
    parser.add_argument(
        "--et-archive-source",
        type=Path,
        action="append",
        default=[],
        help="Lokale HTML-Datei einer European-Tour-Archivseite (mehrfach moeglich)",
    )
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument(
        "--layout",
        type=Path,
        default=Path(__file__).resolve().parent / "layout.html",
        help="HTML-Vorlage mit 'const DATA='",
    )
    parser.add_argument(
        "--html-out", type=Path, help="Zieldatei fuer die HTML-Ausgabe"
    )
    parser.add_argument(
        "--blacklist",
        type=Path,
        default=DEFAULT_BLACKLIST,
        help="Datei mit auszuschliessenden Termin-Titeln (Substring je Zeile)",
    )
    parser.add_argument(
        "--no-blacklist",
        action="store_true",
        help="Blacklist-Filterung deaktivieren",
    )
    parser.add_argument("--category", default=CATEGORY)
    args = parser.parse_args()

    if args.source:
        html = args.source.read_text(encoding="utf-8")
    else:
        html = fetch(args.url)

    html_parser = TerminParser()
    html_parser.feed(html)
    ranges = extract_ranges(html_parser.spans, args.category)

    blacklist_patterns = []
    if not args.no_blacklist:
        blacklist_patterns = load_blacklist(args.blacklist)
    ranges, removed = apply_blacklist(ranges, blacklist_patterns)

    et_has_entries = any(
        "European Tour" in item["titel"]
        and ET_GENERIC_URL_RE.search(item["url"] or "")
        for item in ranges
    )

    resolved = 0
    unresolved = []
    if et_has_entries:
        if args.et_source:
            et_html = args.et_source.read_text(encoding="utf-8")
        else:
            try:
                et_html = fetch(ET_OVERVIEW_URL)
            except OSError as error:
                print(f"Warnung: European-Tour-Uebersicht nicht ladbar: {error}")
                et_html = None

        archive_htmls = []
        for path in args.et_archive_source:
            archive_htmls.append(path.read_text(encoding="utf-8"))
        if not args.et_source and not archive_htmls:
            years = sorted({item["start"][:4] for item in ranges})
            for year in years:
                try:
                    archive_htmls.append(fetch(ET_ARCHIVE_URL.format(year=year)))
                except OSError:
                    continue

        resolved, unresolved = enrich_with_et_deeplinks(ranges, et_html, archive_htmls)
    else:
        for item in ranges:
            item["sender"] = classify_sender(item)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "darts.json"
    ics_path = out_dir / "darts.ics"

    json_path.write_text(
        json.dumps(ranges, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    ics_path.write_text(
        build_ics(ranges, "Darts Kalender"),
        encoding="utf-8",
        newline="",
    )

    html_path = args.html_out
    html_written = False
    if html_path is not None:
        try:
            html = build_html(ranges, args.layout)
        except (OSError, ValueError) as error:
            print(f"Warnung: HTML nicht erzeugt: {error}")
        else:
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(html, encoding="utf-8", newline="")
            html_written = True

    print(f"Kategorie: {args.category}")
    print(f"Zeitraeume: {len(ranges)}")
    if removed:
        print(f"Blacklist: {len(removed)} Termine entfernt")
        for item in removed:
            print(f"  {item['start']} -> {item['end']}  {item['titel']} {item['details']}")
    if et_has_entries:
        print(f"European-Tour-Deep-Links: {resolved} aufgeloest, {len(unresolved)} offen")
    counts = {}
    for item in ranges:
        counts[item["sender"]] = counts.get(item["sender"], 0) + 1
        event = f" | {item['event']}" if item.get("event") else ""
        print(
            f"  {item['start']} -> {item['end']}  [{item['sender']}]  "
            f"{item['titel']} {item['details']}{event}"
        )
    if unresolved:
        print("Nicht aufgeloeste European-Tour-Termine:")
        for item in unresolved:
            print(f"  {item['start']} -> {item['end']}  {item['titel']} {item['details']}")
    print("Sender:")
    for sender in sorted(counts):
        print(f"  {sender}: {counts[sender]}")
    print(f"JSON: {json_path}")
    print(f"ICS:  {ics_path}")
    if html_written:
        print(f"HTML: {html_path}")


if __name__ == "__main__":
    sys.exit(main())
