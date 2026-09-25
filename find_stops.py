"""
Find Wiener Linien stopIds (RBL numbers) for a station.

Run this ON THE PI (it needs internet), then paste the numbers it prints
into config.py:

    python3 find_stops.py Pilgramgasse

It downloads three small CSV files published by Wiener Linien as open data
and joins them, because no single file maps "station name + line + direction"
to a stopId on its own:

    haltestellen.csv  – stations          (name       -> DIVA)
    haltepunkte.csv   – platforms/stops   (DIVA       -> StopID, i.e. RBL)
    fahrwegverlaeufe  – route patterns    (StopID     -> which line stops there)
    linien.csv        – line names        (LineID     -> "U4", "13A", ...)

The files are cached next to this script so repeat runs are instant.
Re-run it (delete the ogd_cache/ folder first) if Wiener Linien ever
rename their columns again — they did exactly that at some point after
this script was first written: the CSVs used to have German column names
(NAME, RBL_NUMMER, BEZEICHNUNG, ...) and now use English ones (PlatformText,
StopID, LineText, ...). This version matches the current, English schema.
"""

from __future__ import annotations

import csv
import io
import os
import sys
from collections import defaultdict

import requests

BASE = "https://www.wienerlinien.at/ogd_realtime/doku/ogd/"
FILES = {
    "haltestellen": "wienerlinien-ogd-haltestellen.csv",
    "haltepunkte": "wienerlinien-ogd-haltepunkte.csv",
    "fahrwege": "wienerlinien-ogd-fahrwegverlaeufe.csv",
    "linien": "wienerlinien-ogd-linien.csv",
}

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ogd_cache")


def load(name: str) -> list[dict]:
    """Download (or read from cache) one OGD CSV and return it as dicts."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, FILES[name])

    if not os.path.exists(path):
        url = BASE + FILES[name]
        print(f"  downloading {FILES[name]} ...", flush=True)
        response = requests.get(url, timeout=(5, 60))
        response.raise_for_status()
        with open(path, "wb") as handle:
            handle.write(response.content)

    with open(path, "rb") as handle:
        raw = handle.read()

    # These files are usually UTF-8 now, but fall back to Latin-1 for safety
    # (station names contain German umlauts and ß).
    text = raw.decode("utf-8-sig", errors="replace")
    if "�" in text[:4000] or "Ã" in text[:4000]:
        text = raw.decode("latin-1", errors="replace")

    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def get(row: dict, *candidates: str) -> str:
    """Read a column by any of several possible header spellings."""
    for key in candidates:
        for actual in row:
            if actual and actual.strip().upper() == key.upper():
                return (row[actual] or "").strip()
    return ""


def main(query: str) -> int:
    query_lower = query.lower()

    print(f"Looking for stations matching {query!r} ...")
    stations = load("haltestellen")
    matches = [
        row for row in stations
        if query_lower in get(row, "PlatformText", "NAME").lower()
    ]
    if not matches:
        print(f"No station found matching {query!r}.")
        return 1

    divas = {}
    for row in matches:
        diva = get(row, "DIVA")
        name = get(row, "PlatformText", "NAME")
        if diva:
            divas[diva] = name
    print(f"  found {len(matches)} station row(s), {len(divas)} DIVA group(s)")

    # DIVA -> the platforms (stopIds) that belong to it
    print("Resolving platforms ...")
    stops = load("haltepunkte")
    stop_ids: dict[str, dict] = {}
    for row in stops:
        diva = get(row, "DIVA")
        if diva not in divas:
            continue
        stop_id = get(row, "StopID", "RBL_NUMMER", "RBL")
        if not stop_id or stop_id == "0":
            continue
        stop_ids[stop_id] = {
            "station": divas[diva],
            "label": get(row, "StopText", "NAME"),
        }

    if not stop_ids:
        print("  no platforms with a StopID — nothing to query.")
        return 1

    # LineID -> human-readable line name ("U4", "13A", ...) and mode
    print("Matching lines ...")
    line_info = {}
    for row in load("linien"):
        line_id = get(row, "LineID", "LINIEN_ID")
        name = get(row, "LineText", "BEZEICHNUNG", "NAME")
        mode = get(row, "MeansOfTransport")
        if line_id and name:
            line_info[line_id] = (name, mode)

    serves: dict[str, set] = defaultdict(set)
    for row in load("fahrwege"):
        stop_id = get(row, "StopID", "RBL_NUMMER", "RBL")
        if stop_id in stop_ids:
            line_id = get(row, "LineID", "LINIEN_ID")
            name, _mode = line_info.get(line_id, (line_id, ""))
            serves[stop_id].add(name)

    print()
    print("=" * 70)
    print(f"  stopIds for {query}")
    print("=" * 70)
    for stop_id in sorted(stop_ids, key=int):
        info = stop_ids[stop_id]
        lines = ", ".join(sorted(x for x in serves.get(stop_id, set()) if x)) or "?"
        print(f"  {stop_id:>6}   {lines:<22} {info['station']}  ({info['label']})")
    print("=" * 70)
    print()
    print("To see which DIRECTION each stopId serves, query it live —")
    print("this prints the destination ('towards') for each one:")
    first = sorted(stop_ids, key=int)[0]
    print(f"  python3 wl_client.py {first}")
    print()
    print("Then put the numbers into WL_ROWS in config.py.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("usage: python3 find_stops.py <station name>")
        sys.exit(2)
    sys.exit(main(" ".join(sys.argv[1:])))
