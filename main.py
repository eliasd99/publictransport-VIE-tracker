"""
Pilgramgasse departure board.

    python3 main.py             # auto-detect the screen
    python3 main.py --window    # windowed, for testing on a laptop
    python3 main.py --once out.png   # render one frame to a PNG and exit

Data is fetched in background threads so a slow or failing network never
freezes the display. Countdowns are recomputed locally every frame from the
absolute departure times, so the numbers keep ticking between refreshes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import signal
import sys
import threading
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

import config
import oebb_client
import wl_client
from display import open_display
from renderer import Board

_stop = threading.Event()


class State:
    """Everything the renderer needs, guarded by a lock."""

    def __init__(self):
        self._lock = threading.Lock()
        self.now = dt.datetime.now(wl_client.LOCAL_TZ)
        self.departures: list = []
        self.disruptions: list[str] = []
        self.wl_error: str | None = "starting…"
        self.wl_updated: dt.datetime | None = None
        self.trains: list = []
        self.train_error: str | None = None
        self.train_updated: dt.datetime | None = None

    def update_wl(self, result) -> None:
        with self._lock:
            if result.error:
                self.wl_error = result.error
                # Keep showing the previous departures; they're still roughly
                # right and a blank screen is worse than slightly stale data.
                return
            self.wl_error = None
            self.departures = result.departures
            self.disruptions = result.disruptions
            self.wl_updated = result.fetched_at

    def update_trains(self, result) -> None:
        with self._lock:
            if result.error and not result.connections:
                self.train_error = result.error
                return
            self.train_error = None
            self.trains = result.connections
            self.train_updated = result.fetched_at

    def seconds_since_wl_update(self) -> float | None:
        with self._lock:
            updated = self.wl_updated
        if updated is None:
            return None
        return (self.now - updated).total_seconds()

    def wl_is_stale(self) -> bool:
        """True before the first good update, or once updates have stopped."""
        age = self.seconds_since_wl_update()
        return age is None or age > config.WL_STALE_SECONDS

    def departures_for(self, row) -> list:
        """
        Pick the departures belonging to one row.

        Normally that's an exact stopId match, but a single stopId can serve
        more than one line at the same platform — stop 699 (Alser
        Straße/Skodagasse) carries both 13A and 14A — so the line name has to
        be checked too, or the two rows would double up on each other's
        departures. If a row has no stopIds configured yet, fall back to
        matching the line name (and, loosely, the destination) so the board
        still shows something useful before find_stops.py has been run.
        """
        wanted = {str(s) for s in row.get("stop_ids") or []}
        title = row.get("title", "").upper()
        now = self.now
        with self._lock:
            source = list(self.departures)

        if wanted:
            picked = [d for d in source if d.stop_id in wanted and d.line.upper() == title]
        else:
            subtitle = row.get("subtitle", "").lower()
            picked = [
                d for d in source
                if d.line.upper() == title
                and (not subtitle or subtitle.split()[0] in d.towards.lower())
            ]

        # Drop anything already gone, keep chronological order.
        return [d for d in picked if (d.minutes_from(now) or 0) >= 0]


def collect_stop_ids() -> list[str]:
    ids: list[str] = []
    for row in config.WL_ROWS:
        for stop_id in row.get("stop_ids") or []:
            if str(stop_id) not in ids:
                ids.append(str(stop_id))
    return ids


def wl_worker(state: State) -> None:
    stop_ids = collect_stop_ids()
    if not stop_ids:
        state.wl_error = "no stopIds in config.py — run find_stops.py"
        return

    failures = 0
    while not _stop.is_set():
        # fetch() handles network errors itself, but an API response with an
        # unexpected shape could still raise while it's being parsed. Catch
        # everything here: if this thread died, the board would keep running
        # (so systemd would never restart it) while the rows silently froze.
        try:
            result = wl_client.fetch(stop_ids, traffic_info=config.SHOW_DISRUPTIONS)
        except Exception as exc:                   # noqa: BLE001
            result = wl_client.MonitorResult(error=f"internal: {exc.__class__.__name__}")
        state.update_wl(result)

        # Back off a little when things are failing, so a network outage
        # doesn't turn into a request every 30 seconds forever.
        failures = failures + 1 if result.error else 0
        delay = config.WL_REFRESH_SECONDS * min(4, 1 + failures)
        _stop.wait(delay)


def train_worker(state: State) -> None:
    if not config.OEBB_ENABLED:
        return
    failures = 0
    while not _stop.is_set():
        # Same reasoning as wl_worker: never let a parsing surprise kill the thread.
        try:
            result = oebb_client.fetch(config.OEBB_FROM, config.OEBB_TO, config.OEBB_RESULTS)
        except Exception as exc:                   # noqa: BLE001
            result = oebb_client.TrainResult(error=f"internal: {exc.__class__.__name__}")
        state.update_trains(result)
        failures = failures + 1 if result.error else 0
        delay = config.OEBB_REFRESH_SECONDS * min(4, 1 + failures)
        _stop.wait(delay)


def handle_signal(signum, frame):     # noqa: ARG001
    _stop.set()


def render_once(path: str) -> int:
    """Render a single frame with live data and save it as a PNG."""
    pygame.init()
    pygame.font.init()

    state = State()
    stop_ids = collect_stop_ids()
    if stop_ids:
        state.update_wl(wl_client.fetch(stop_ids, traffic_info=config.SHOW_DISRUPTIONS))
    else:
        state.wl_error = "no stopIds — run find_stops.py"
    if config.OEBB_ENABLED:
        state.update_trains(oebb_client.fetch(config.OEBB_FROM, config.OEBB_TO,
                                              config.OEBB_RESULTS))
    state.now = dt.datetime.now(wl_client.LOCAL_TZ)

    board = Board(config.INTERNAL_SIZE)
    frame = board.render(state)

    # Save the upscaled version — a 320x180 PNG is hard to judge.
    factor = max(1, min(config.FALLBACK_SIZE[0] // frame.get_width(),
                        config.FALLBACK_SIZE[1] // frame.get_height()))
    pygame.image.save(
        pygame.transform.scale(
            frame, (frame.get_width() * factor, frame.get_height() * factor)
        ),
        path,
    )
    print("wrote", path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pilgramgasse departure board")
    parser.add_argument("--window", action="store_true", help="run in a window")
    parser.add_argument("--once", metavar="PNG", help="render one frame to a PNG and exit")
    args = parser.parse_args()

    if args.once:
        return render_once(args.once)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    pygame.init()
    pygame.font.init()

    mode = "window" if args.window else config.DISPLAY_MODE
    try:
        display = open_display(mode, config.FB_DEVICE, config.FALLBACK_SIZE,
                               config.SCANLINES)
    except RuntimeError as exc:
        print("Display error:", exc, file=sys.stderr)
        print("\nTry:  python3 display.py    to test the output backends.",
              file=sys.stderr)
        return 1

    print("Display:", display, flush=True)

    state = State()
    board = Board(config.INTERNAL_SIZE)

    threads = [
        threading.Thread(target=wl_worker, args=(state,), daemon=True),
        threading.Thread(target=train_worker, args=(state,), daemon=True),
    ]
    for thread in threads:
        thread.start()

    clock = pygame.time.Clock()
    try:
        while not _stop.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    _stop.set()
                elif event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_ESCAPE, pygame.K_q
                ):
                    _stop.set()

            state.now = dt.datetime.now(wl_client.LOCAL_TZ)
            display.show(board.render(state))
            clock.tick(config.FPS)
    finally:
        _stop.set()
        display.close()
        pygame.quit()

    return 0


if __name__ == "__main__":
    sys.exit(main())
