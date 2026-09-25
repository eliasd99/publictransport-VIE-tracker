"""
ÖBB connections via the HAFAS "mgate" endpoint.

IMPORTANT CAVEAT
----------------
ÖBB does not publish an official open API for live connections. This module
talks to the same endpoint the ÖBB Scotty app uses. The access ID below is
public knowledge (it ships inside the app and is documented in the widely
used open-source `hafas-client` project), but this is still an *unofficial*
interface:

  * it can change or stop working without notice,
  * there are no uptime guarantees,
  * so be gentle with it — one request every couple of minutes, which is
    what config.OEBB_REFRESH_SECONDS does.

If it ever breaks, the board keeps working; the train row just shows an
error line, and you can set OEBB_ENABLED = False in config.py.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import requests

import config

LOCAL_TZ = ZoneInfo(config.TIMEZONE)

ENDPOINT = "https://fahrplan.oebb.at/bin/mgate.exe"

CLIENT = {"type": "IPH", "id": "OEBB", "v": "6030600", "name": "oebbPROD-ADHOC"}
AUTH = {"type": "AID", "aid": "OWDL4fE4ixNiPBBm"}
VERSION = "1.45"

TIMEOUT = (5, 15)

_location_cache: dict[str, str] = {}


@dataclass
class Connection:
    departure: dt.datetime | None
    arrival: dt.datetime | None
    dep_delay: int = 0          # minutes
    arr_delay: int = 0          # minutes
    platform: str = ""
    changes: int = 0
    product: str = ""           # e.g. "REX 7622"
    cancelled: bool = False

    @property
    def duration_minutes(self) -> int | None:
        if not self.departure or not self.arrival:
            return None
        return int((self.arrival - self.departure).total_seconds() // 60)

    def minutes_from(self, now: dt.datetime) -> int | None:
        if self.departure is None:
            return None
        return int((self.departure - now).total_seconds() // 60)


@dataclass
class TrainResult:
    connections: list[Connection] = field(default_factory=list)
    error: str | None = None
    fetched_at: dt.datetime | None = None


def _request(method: str, req: dict) -> dict:
    """Send one mgate service request and return svcResL[0]['res']."""
    body = {
        "lang": "de",
        "svcReqL": [{"cfg": {"polyEnc": "GPA"}, "meth": method, "req": req}],
        "client": CLIENT,
        "ext": "OEBB.1",
        "ver": VERSION,
        "auth": AUTH,
    }
    response = requests.post(
        ENDPOINT,
        json=body,
        timeout=TIMEOUT,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()

    if payload.get("err") not in (None, "OK"):
        raise RuntimeError(f"HAFAS error {payload.get('err')}")

    services = payload.get("svcResL") or []
    if not services:
        raise RuntimeError("empty HAFAS response")
    service = services[0]
    if service.get("err") not in (None, "OK"):
        raise RuntimeError(f"HAFAS {method} error {service.get('err')}")
    return service.get("res") or {}


def resolve_station(name: str) -> str:
    """Turn a station name into the location ID (lid) HAFAS wants."""
    if name in _location_cache:
        return _location_cache[name]

    res = _request(
        "LocMatch",
        {"input": {"field": "S", "loc": {"name": name + "?", "type": "S"}, "maxLoc": 5}},
    )
    matches = ((res.get("match") or {}).get("locL")) or []
    stations = [m for m in matches if m.get("extId") or m.get("lid")]
    if not stations:
        raise RuntimeError(f"station not found: {name}")

    best = stations[0]
    lid = best.get("lid") or f"A=1@L={best['extId']}@"
    _location_cache[name] = lid
    return lid


def _parse_hafas_time(date_str: str, time_str: str | None) -> dt.datetime | None:
    """
    HAFAS times look like "133000" (HHMMSS), sometimes prefixed with a day
    offset like "01133000" meaning "next day". Dates look like "20260919".
    """
    if not time_str or not date_str:
        return None

    day_offset = 0
    if len(time_str) == 8:
        day_offset = int(time_str[:2])
        time_str = time_str[2:]
    if len(time_str) != 6:
        return None

    try:
        base = dt.datetime.strptime(date_str, "%Y%m%d")
        moment = base + dt.timedelta(
            hours=int(time_str[0:2]),
            minutes=int(time_str[2:4]),
            seconds=int(time_str[4:6]),
            days=day_offset,
        )
    except ValueError:
        return None

    # HAFAS returns local Vienna time without an offset. Attach Vienna
    # explicitly rather than the Pi's system timezone, which may be UTC.
    return moment.replace(tzinfo=LOCAL_TZ)


def fetch(origin: str, destination: str, results: int = 3) -> TrainResult:
    """
    Look up the next connections. Never raises — errors land in `.error`.
    """
    try:
        from_lid = resolve_station(origin)
        to_lid = resolve_station(destination)

        now = dt.datetime.now(LOCAL_TZ)
        res = _request(
            "TripSearch",
            {
                "depLocL": [{"lid": from_lid}],
                "arrLocL": [{"lid": to_lid}],
                "outDate": now.strftime("%Y%m%d"),
                "outTime": now.strftime("%H%M%S"),
                "getPasslist": False,
                "getPolyline": False,
                "numF": max(1, results),
            },
        )
    except requests.RequestException as exc:
        return TrainResult(error=f"network: {exc.__class__.__name__}")
    except (RuntimeError, ValueError, KeyError) as exc:
        return TrainResult(error=str(exc)[:60])

    # Product names live in a shared lookup table referenced by index.
    products = res.get("common", {}).get("prodL") or []

    outcome = TrainResult(fetched_at=dt.datetime.now(LOCAL_TZ))

    for connection in (res.get("outConL") or [])[:results]:
        date = connection.get("date") or ""
        dep = connection.get("dep") or {}
        arr = connection.get("arr") or {}

        planned_dep = _parse_hafas_time(date, dep.get("dTimeS"))
        real_dep = _parse_hafas_time(date, dep.get("dTimeR"))
        planned_arr = _parse_hafas_time(date, arr.get("aTimeS"))
        real_arr = _parse_hafas_time(date, arr.get("aTimeR"))

        dep_delay = 0
        if planned_dep and real_dep:
            dep_delay = round((real_dep - planned_dep).total_seconds() / 60)
        arr_delay = 0
        if planned_arr and real_arr:
            arr_delay = round((real_arr - planned_arr).total_seconds() / 60)

        # Name the first train of the journey.
        product = ""
        for section in connection.get("secL") or []:
            journey = section.get("jny")
            if not journey:
                continue
            index = journey.get("prodX")
            if index is not None and index < len(products):
                entry = products[index]
                product = (entry.get("addName") or entry.get("name") or "").strip()
            break

        outcome.connections.append(
            Connection(
                departure=real_dep or planned_dep,
                arrival=real_arr or planned_arr,
                dep_delay=dep_delay,
                arr_delay=arr_delay,
                platform=str(dep.get("dPlatfR") or dep.get("dPlatfS") or ""),
                changes=int(connection.get("chg") or 0),
                product=product,
                cancelled=bool(dep.get("dCncl") or connection.get("cncl")),
            )
        )

    if not outcome.connections and not outcome.error:
        outcome.error = "no connections returned"
    return outcome


if __name__ == "__main__":
    # Quick manual check:
    #   python3 oebb_client.py "Wien Meidling" "Wulkaprodersdorf"
    import sys

    start = sys.argv[1] if len(sys.argv) > 1 else "Wien Meidling"
    end = sys.argv[2] if len(sys.argv) > 2 else "Wulkaprodersdorf"

    data = fetch(start, end)
    if data.error:
        print("ERROR:", data.error)
    for item in data.connections:
        when = item.departure.strftime("%H:%M") if item.departure else "??:??"
        till = item.arrival.strftime("%H:%M") if item.arrival else "??:??"
        delay = f" +{item.dep_delay}" if item.dep_delay else ""
        change = "direct" if item.changes == 0 else f"{item.changes} change(s)"
        print(f"{when}{delay} -> {till}  {item.product:<12} {change}  Bstg {item.platform}")
