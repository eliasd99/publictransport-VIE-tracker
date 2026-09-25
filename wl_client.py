"""
Wiener Linien OGD realtime client.

Docs: https://www.wienerlinien.at/ogd_realtime/doku/
No API key is needed. The endpoint is:

    https://www.wienerlinien.at/ogd_realtime/monitor?stopId=123&stopId=124

Each stopId ("RBL number") identifies one station + one line + one direction,
so a single station like Pilgramgasse has many of them.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import requests

import config

LOCAL_TZ = ZoneInfo(config.TIMEZONE)

MONITOR_URL = "https://www.wienerlinien.at/ogd_realtime/monitor"

# Timeout as (connect, read). A Pi on wifi occasionally stalls; we'd rather
# skip a refresh than freeze the whole board.
TIMEOUT = (5, 10)


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------
# Wiener Linien returns e.g. "2026-09-19T13:45:00.000+0200".
# Python 3.11 parses that fine, but Python 3.9 (Raspberry Pi OS Bullseye)
# rejects the "+0200" form, so we normalise it first.
_TZ_FIX = re.compile(r"([+-]\d{2})(\d{2})$")


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    text = _TZ_FIX.sub(r"\1:\2", text)
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # No offset in the string: it's Vienna local time, whatever the Pi's
        # own timezone happens to be set to.
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed


@dataclass
class Departure:
    line: str
    towards: str
    planned: dt.datetime | None
    real: dt.datetime | None
    stop_id: str = ""            # which RBL this came from — used to pick a column
    platform: str = ""
    barrier_free: bool = False
    traffic_jam: bool = False

    @property
    def when(self) -> dt.datetime | None:
        """Best available time: realtime if we have it, otherwise timetable."""
        return self.real or self.planned

    @property
    def delay_minutes(self) -> int | None:
        """Positive = late, negative = early. None if there's no realtime."""
        if not self.real or not self.planned:
            return None
        return round((self.real - self.planned).total_seconds() / 60)

    def minutes_from(self, now: dt.datetime) -> int | None:
        """
        Countdown in whole minutes.

        We compute this locally from the absolute departure time instead of
        using the API's own `countdown` field. That way the numbers on screen
        keep ticking down correctly between refreshes.
        """
        target = self.when
        if target is None:
            return None
        return int((target - now).total_seconds() // 60)


@dataclass
class MonitorResult:
    departures: list[Departure] = field(default_factory=list)
    disruptions: list[str] = field(default_factory=list)
    error: str | None = None
    fetched_at: dt.datetime | None = None


def _collect_disruptions(payload: dict) -> list[str]:
    """
    Pull human-readable disruption text out of the response.

    Depending on the request, these show up either at the top level under
    `trafficInfos` or attached to individual monitors, so we check both.
    """
    messages: list[str] = []

    def add(entry: dict) -> None:
        if not isinstance(entry, dict):
            return
        title = (entry.get("title") or "").strip()
        description = (entry.get("description") or "").strip()
        text = description or title
        if text and text not in messages:
            messages.append(text)

    data = payload.get("data") or {}
    for entry in data.get("trafficInfos") or []:
        add(entry)
    for monitor in data.get("monitors") or []:
        attributes = monitor.get("attributes") or {}
        for entry in attributes.get("trafficInfos") or []:
            add(entry)
    return messages


def fetch(stop_ids, traffic_info: bool = True) -> MonitorResult:
    """
    Fetch departures for the given stopIds.

    Never raises: on any failure it returns a MonitorResult with `.error` set,
    so the display loop can keep showing the previous data instead of dying.
    """
    stop_ids = [str(s) for s in stop_ids if s]
    if not stop_ids:
        return MonitorResult(error="no stop IDs configured")

    params: list[tuple[str, str]] = [("stopId", s) for s in stop_ids]
    if traffic_info:
        # 'stoerunglang' = the long-form disruption text from the control centre.
        params.append(("activateTrafficInfo", "stoerunglang"))

    try:
        response = requests.get(
            MONITOR_URL,
            params=params,
            timeout=TIMEOUT,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return MonitorResult(error=f"network: {exc.__class__.__name__}")
    except ValueError:
        return MonitorResult(error="bad JSON from API")

    # The API reports its own status in message.messageCode (1 = OK).
    message = payload.get("message") or {}
    if message.get("messageCode") not in (1, None):
        return MonitorResult(error=f"API: {message.get('value', 'error')}")

    result = MonitorResult(fetched_at=dt.datetime.now(LOCAL_TZ))

    for monitor in (payload.get("data") or {}).get("monitors") or []:
        properties = (monitor.get("locationStop") or {}).get("properties") or {}
        rbl = str((properties.get("attributes") or {}).get("rbl") or "")

        for line in monitor.get("lines") or []:
            line_name = (line.get("name") or "?").strip()
            towards = " ".join((line.get("towards") or "").split())
            platform = str(line.get("platform") or "")
            barrier_free = bool(line.get("barrierFree"))
            traffic_jam = bool(line.get("trafficjam"))

            departures = (line.get("departures") or {}).get("departure") or []
            for departure in departures:
                times = departure.get("departureTime") or {}
                planned = parse_time(times.get("timePlanned"))
                real = parse_time(times.get("timeReal"))
                if planned is None and real is None:
                    continue
                result.departures.append(
                    Departure(
                        line=line_name,
                        towards=towards,
                        planned=planned,
                        real=real,
                        stop_id=rbl,
                        platform=platform,
                        barrier_free=barrier_free,
                        traffic_jam=traffic_jam,
                    )
                )

    result.departures.sort(key=lambda d: d.when or dt.datetime.max.replace(tzinfo=dt.timezone.utc))
    result.disruptions = _collect_disruptions(payload)
    return result


if __name__ == "__main__":
    # Quick manual check:  python3 wl_client.py 4111 4112
    import sys

    outcome = fetch(sys.argv[1:])
    if outcome.error:
        print("ERROR:", outcome.error)
    now = dt.datetime.now(LOCAL_TZ)
    for dep in outcome.departures:
        delay = dep.delay_minutes
        suffix = f"  ({delay:+d} min)" if delay else ""
        print(f"{dep.line:>5}  {dep.minutes_from(now):>3} min  {dep.towards}{suffix}")
    for text in outcome.disruptions:
        print("!", text)
