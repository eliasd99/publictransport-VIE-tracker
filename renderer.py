"""
Pixel-art departure board — "stacked list" layout.

The whole board is drawn onto a deliberately tiny canvas (320x180 by
default) and blown up to the monitor with whole-number nearest-neighbour
scaling. That is what makes the pixels chunky and square instead of blurry,
so every measurement in here is in *board pixels*, not screen pixels.

Layout (see DASHBOARD_LAYOUT.md for the design decision this implements):
  * one full-width header bar: "NÄCHSTE ABFAHRTEN" left, HH:MM:SS clock + a
    static (non-blinking) "LIVE" dot on the right. The dot turns amber and
    reads "OFFLINE" when the Wiener Linien data has stopped refreshing.
  * ÖBB times are struck through in red when cancelled; a delayed next
    train gets a small "+N" after its (already delay-adjusted) time.
  * one row per line/direction below it, stacked top to bottom instead of
    side-by-side columns: pictogram -> coloured line badge -> destination
    -> right-aligned countdown (one big next departure + smaller upcoming
    ones + "MIN"). The ÖBB connection is just another row in the same list,
    showing clock times instead of a minute countdown.
  * no disruption ticker in this layout (removed by request) and no
    blinking anywhere — the clock and the status dot are both static.

Design rules that keep it looking hand-made:
  * no anti-aliasing anywhere — bitmap fonts only
  * no rounded corners
  * dithered checkerboards instead of gradients
  * a small fixed palette
"""

from __future__ import annotations

import pygame

import config
import pixelfont as pf

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
# Values from DASHBOARD_LAYOUT.md ("Typography / color" section) — these are
# still mockup placeholders, not the real Wiener Linien/ÖBB brand hex values.

BG = (11, 15, 14)            # #0B0F0E
BG_DITHER = (18, 22, 21)
TEXT = (244, 239, 225)       # #F4EFE1
DIM = (150, 155, 145)
DIMMER = (92, 97, 90)
BORDER = (54, 58, 90)
ACCENT = (255, 199, 68)
HOT = (255, 122, 86)
WARN = (232, 84, 107)
LIVE_DOT = (61, 220, 151)    # #3DDC97 — static presence indicator, never blinks
STALE_DOT = ACCENT           # amber — same dot, data no longer refreshing

LINE_COLORS = {
    "U4":  (46, 139, 87),    # #2E8B57
    "13A": (232, 163, 61),   # #E8A33D
    "14A": (61, 165, 217),   # #3DA5D9 — distinct from 13A so the two buses don't blur together
    "_oebb": (200, 30, 44),  # #C81E2C
    "_bus": (58, 143, 216),
}

# ---------------------------------------------------------------------------
# Sprites — '#' body, '+' highlight, '.' transparent
# ---------------------------------------------------------------------------

# Two square windows, flat roof — front of a U-Bahn carriage.
SPRITE_METRO = (
    ".#####.",
    "#+.+.+#",
    "#+++++#",
    "#.....#",
    "#######",
    ".#...#.",
    ".......",
)

# One wide windscreen — front of a bus.
SPRITE_BUS = (
    ".#####.",
    "#+++++#",
    "#.....#",
    "#+++++#",
    "#######",
    ".#...#.",
    ".......",
)

# Side view with a pantograph on the roof.
SPRITE_TRAIN = (
    "..#.#..",
    "..###..",
    ".#####.",
    "#+.+.+#",
    "#######",
    ".#.#.#.",
    ".......",
)


def draw_sprite(surface, rows, x, y, body, highlight=None):
    highlight = highlight or body
    for row_index, row in enumerate(rows):
        for col_index, cell in enumerate(row):
            if cell == "#":
                surface.set_at((x + col_index, y + row_index), body)
            elif cell == "+":
                surface.set_at((x + col_index, y + row_index), highlight)


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def dither(surface, rect, color, phase=0):
    """Checkerboard fill — the pixel-art way to get a half-tone."""
    for y in range(rect.top, rect.bottom):
        for x in range(rect.left + ((y + phase) % 2), rect.right, 2):
            surface.set_at((x, y), color)


def dotted_line(surface, x1, x2, y, color, step=2):
    for x in range(x1, x2, step):
        surface.set_at((x, y), color)


def badge(surface, text, x, y, color, scale=1, pad_x=2, pad_y=2):
    """A line number in a solid colour block, with a 1px drop shadow."""
    width, height = pf.measure(text, tiny=False, scale=scale)
    rect = pygame.Rect(x, y, width + pad_x * 2, height + pad_y * 2)
    pygame.draw.rect(surface, color, rect)

    # Darken the bottom row so the block has a little depth.
    shade = tuple(max(0, channel - 45) for channel in color)
    pygame.draw.line(surface, shade, (rect.left, rect.bottom - 1),
                     (rect.right - 1, rect.bottom - 1))
    for corner in (
        (rect.left, rect.top), (rect.right - 1, rect.top),
        (rect.left, rect.bottom - 1), (rect.right - 1, rect.bottom - 1),
    ):
        surface.set_at(corner, BG)

    # Shadow first, then the white glyphs on top of it.
    pf.draw(surface, text, rect.x + pad_x, rect.y + pad_y + 1, shade, scale=scale)
    pf.draw(surface, text, rect.x + pad_x, rect.y + pad_y, (255, 255, 255), scale=scale)
    return rect


def line_color(name: str):
    name = (name or "").upper()
    if name in LINE_COLORS:
        return LINE_COLORS[name]
    if name.startswith("U"):
        return LINE_COLORS["U4"]
    return LINE_COLORS["_bus"]


def line_sprite(name: str):
    return SPRITE_METRO if (name or "").upper().startswith("U") else SPRITE_BUS


def _even_heights(total: int, count: int) -> list[int]:
    """Split `total` px into `count` row heights as evenly as possible."""
    if count <= 0:
        return []
    base, remainder = divmod(total, count)
    # Give the extra pixels to the first rows rather than the last, so the
    # ÖBB row (usually last) doesn't look randomly taller or shorter.
    return [base + 1 if i < remainder else base for i in range(count)]


# ---------------------------------------------------------------------------


class Board:
    MARGIN = 4
    HEADER_H = 15

    def __init__(self, size=None):
        self.size = size or config.INTERNAL_SIZE
        self.surface = pygame.Surface(self.size)

    # -- main ---------------------------------------------------------------

    def render(self, state) -> pygame.Surface:
        surface = self.surface
        surface.fill(BG)

        width, height = self.size
        dither(surface, pygame.Rect(0, 0, width, self.HEADER_H - 1), BG_DITHER)

        self._header(state)
        top = self.HEADER_H
        self._rows(state, top, height - top - self.MARGIN)

        return surface

    # -- header ---------------------------------------------------------------
    # Static: no blinking colon, no blinking status dot — just a presence
    # indicator whose colour reflects whether the data is fresh
    # (DASHBOARD_LAYOUT.md).

    def _header(self, state) -> None:
        surface = self.surface
        width = self.size[0]

        label_max_w = width - 2 * self.MARGIN - 110
        pf.draw(surface, pf.fit("NÄCHSTE ABFAHRTEN", label_max_w, tiny=True), self.MARGIN, 5, DIM,
                tiny=True)

        stale = state.wl_is_stale()
        dot_colour = STALE_DOT if stale else LIVE_DOT
        live_rect = pf.draw(surface, "OFFLINE" if stale else "LIVE", width - self.MARGIN, 5,
                            dot_colour, tiny=True, align="right")
        dot_x = live_rect.left - 6
        pygame.draw.rect(surface, dot_colour, pygame.Rect(dot_x, live_rect.y + 1, 3, 3))
        pf.draw(surface, state.now.strftime("%H:%M:%S"), dot_x - 5, 4, TEXT,
                scale=1, align="right")

        dotted_line(surface, self.MARGIN, width - self.MARGIN, self.HEADER_H - 1, BORDER)

    # -- the stacked row list -------------------------------------------------

    def _rows(self, state, top: int, height: int) -> None:
        surface = self.surface
        width = self.size[0]

        entries = [("wl", row) for row in config.WL_ROWS]
        if config.OEBB_ENABLED:
            entries.append(("oebb", None))

        if not entries or height < 10:
            return

        heights = _even_heights(height, len(entries))

        y = top
        for index, ((kind, row), row_h) in enumerate(zip(entries, heights)):
            rect = pygame.Rect(self.MARGIN, y, width - 2 * self.MARGIN, row_h)
            if kind == "wl":
                self._wl_row(state, row, rect)
            else:
                self._oebb_row(state, rect)

            if index < len(entries) - 1:
                dotted_line(surface, self.MARGIN, width - self.MARGIN, rect.bottom - 1, BORDER)

            y += row_h

    # -- one Wiener Linien row -------------------------------------------------

    def _wl_row(self, state, row, rect: pygame.Rect) -> None:
        surface = self.surface
        title = row.get("title", "?")
        colour = line_color(title)

        icon_y = rect.y + (rect.height - 7) // 2
        draw_sprite(surface, line_sprite(title), rect.x, icon_y, colour, (255, 255, 255))

        badge_x = rect.x + 9
        badge_h = pf.BIG_HEIGHT + 4
        badge_y = rect.y + (rect.height - badge_h) // 2
        chip = badge(surface, title, badge_x, badge_y, colour)

        dest_x = chip.right + 5
        dest_y = rect.y + (rect.height - pf.TINY_HEIGHT) // 2
        dest_max_w = max(20, rect.right - dest_x - 76)
        destination = f"→ {row.get('subtitle', '')}"
        pf.draw(surface, pf.fit(destination, dest_max_w, tiny=True), dest_x, dest_y, TEXT,
                tiny=True)

        entries = state.departures_for(row)[: config.WL_DEPARTURES_PER_ROW]
        self._countdown_group(state, entries, rect)

    def _countdown_group(self, state, entries, rect: pygame.Rect) -> None:
        """
        Right-aligned: one emphasised "next" number, then smaller upcoming
        ones, then "MIN". The emphasis is carried by colour (and the BIG vs
        TINY face), not by blowing the first number up to double size —
        keeps the whole row legible without needing anything oversized.
        """
        surface = self.surface
        mid_y = rect.y + (rect.height - pf.TINY_HEIGHT) // 2

        if not entries:
            message = pf.fit(state.wl_error or "KEINE ABFAHRTEN", 110, tiny=True)
            pf.draw(surface, message, rect.right - 2, mid_y, DIMMER,
                    tiny=True, align="right")
            return

        now = state.now
        minutes = [max(0, d.minutes_from(now) or 0) for d in entries]

        x = rect.right - 2
        min_rect = pf.draw(surface, "MIN", x, mid_y, DIMMER, tiny=True, align="right")
        x = min_rect.left - 4

        # Smaller upcoming numbers, closest-to-MIN first (i.e. the furthest
        # departure, reading big -> small -> small -> MIN left to right).
        for value in reversed(minutes[1:]):
            small_rect = pf.draw(surface, str(value), x, mid_y, DIM, tiny=True, align="right")
            x = small_rect.left - 5

        # The next departure, or a blinking-free "JETZT" — same size as the
        # row's other text, picked out by colour instead of by size.
        first = minutes[0]
        big_y = rect.y + (rect.height - pf.BIG_HEIGHT) // 2
        if first == 0:
            pf.draw(surface, "JETZT", x, big_y, ACCENT, scale=1, align="right")
        else:
            colour = HOT if first <= 1 else ACCENT
            pf.draw(surface, str(first), x, big_y, colour, scale=1, align="right")

    # -- the ÖBB row -------------------------------------------------------

    def _oebb_row(self, state, rect: pygame.Rect) -> None:
        surface = self.surface
        colour = LINE_COLORS["_oebb"]

        icon_y = rect.y + (rect.height - 7) // 2
        draw_sprite(surface, SPRITE_TRAIN, rect.x, icon_y, colour, (255, 235, 235))

        badge_x = rect.x + 9
        badge_h = pf.BIG_HEIGHT + 4
        badge_y = rect.y + (rect.height - badge_h) // 2
        chip = badge(surface, "ÖBB", badge_x, badge_y, colour)

        dest_x = chip.right + 5
        dest_y = rect.y + (rect.height - pf.TINY_HEIGHT) // 2
        dest_max_w = max(20, rect.right - dest_x - 116)
        # Drop a "Wien "-style city prefix from the origin — there's rarely
        # room for the full station name next to three departure times.
        origin = config.OEBB_FROM.split()[-1]
        route = f"{origin} → {config.OEBB_TO}"
        pf.draw(surface, pf.fit(route, dest_max_w, tiny=True), dest_x, dest_y, TEXT, tiny=True)

        self._time_group(state, rect)

    def _time_group(self, state, rect: pygame.Rect) -> None:
        """Same big-then-small-then-small pattern as _countdown_group, but
        with clock times instead of a minute countdown (no "MIN" suffix)."""
        surface = self.surface
        trains = state.trains[: config.OEBB_RESULTS]
        mid_y = rect.y + (rect.height - pf.TINY_HEIGHT) // 2

        if not trains:
            message = pf.fit(state.train_error or "KEINE VERBINDUNG", 140, tiny=True)
            pf.draw(surface, message, rect.right - 2, mid_y, DIMMER, tiny=True, align="right")
            return

        def label(train):
            return train.departure.strftime("%H:%M") if train.departure else "--:--"

        x = rect.right - 2
        for train in reversed(trains[1:]):
            colour = WARN if train.cancelled else (HOT if train.dep_delay > 0 else DIM)
            small_rect = pf.draw(surface, label(train), x, mid_y, colour, tiny=True,
                                 align="right")
            if train.cancelled:
                self._strike(small_rect, colour)
            x = small_rect.left - 6

        first = trains[0]
        big_y = rect.y + (rect.height - pf.BIG_HEIGHT) // 2
        if first.dep_delay > 0 and not first.cancelled:
            # The time shown is already the real (delayed) one; "+N" says by how much.
            delay_rect = pf.draw(surface, f"+{first.dep_delay}", x, mid_y, HOT,
                                 tiny=True, align="right")
            x = delay_rect.left - 2
        colour = WARN if first.cancelled else TEXT
        big_rect = pf.draw(surface, label(first), x, big_y, colour, scale=1, align="right")
        if first.cancelled:
            self._strike(big_rect, colour)

    def _strike(self, rect: pygame.Rect, colour) -> None:
        """Strike a cancelled departure through the middle of its glyphs."""
        # Glyphs carry one blank accent row on top, so shift the line down a pixel.
        y = rect.y + 1 + (rect.height - 1) // 2
        pygame.draw.line(self.surface, colour, (rect.left - 1, y), (rect.right, y))
