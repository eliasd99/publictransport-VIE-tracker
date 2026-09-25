"""
Hand-drawn bitmap fonts.

Two sizes, both designed on a pixel grid rather than scaled down from a
smooth outline font — that's what keeps the board looking like pixel art
instead of like small text.

    BIG    5x7 glyphs, 6px advance   – headlines, countdowns, clock
    TINY   3x5 glyphs, 4px advance   – direction labels, details

Both are stored with one extra row on top for umlaut dots, so "Ä" lines up
with "A". Glyphs are rendered once per (character, scale, colour) and
cached, so drawing a frame is just blitting.

Everything is drawn in upper case: it's a departure board.
"""

from __future__ import annotations

import pygame

# ---------------------------------------------------------------------------
# 5x7 face
# ---------------------------------------------------------------------------

_BIG = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#...#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("#####", "...#.", "..##.", "....#", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": ("..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ":": (".....", "..#..", "..#..", ".....", "..#..", "..#..", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", "..#..", "....."),
    ",": (".....", ".....", ".....", ".....", "..#..", "..#..", ".#..."),
    "-": (".....", ".....", ".....", ".###.", ".....", ".....", "....."),
    "+": (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "?": (".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."),
    "(": ("...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."),
    ")": (".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."),
    # Square brackets — used for placeholder text like "[stop unresolved]".
    "[": (".###.", ".#...", ".#...", ".#...", ".#...", ".#...", ".###."),
    "]": (".###.", "...#.", "...#.", "...#.", "...#.", "...#.", ".###."),
    "%": ("##..#", "##..#", "...#.", "..#..", ".#...", "#..##", "#..##"),
    "'": ("..#..", "..#..", ".....", ".....", ".....", ".....", "....."),
    "=": (".....", ".....", "#####", ".....", "#####", ".....", "....."),
    "*": (".....", "#.#.#", ".###.", "#####", ".###.", "#.#.#", "....."),
    # Arrow, multiplication sign and middle dot — used in the train row.
    "→": (".....", "..#..", "...#.", "#####", "...#.", "..#..", "....."),
    "×": (".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "....."),
    "·": (".....", ".....", ".....", "..#..", ".....", ".....", "....."),
}

# ---------------------------------------------------------------------------
# 3x5 face
# ---------------------------------------------------------------------------

_TINY = {
    "A": (".#.", "#.#", "###", "#.#", "#.#"),
    "B": ("##.", "#.#", "##.", "#.#", "##."),
    "C": (".##", "#..", "#..", "#..", ".##"),
    "D": ("##.", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "##.", "#..", "###"),
    "F": ("###", "#..", "##.", "#..", "#.."),
    "G": (".##", "#..", "#.#", "#.#", ".##"),
    "H": ("#.#", "#.#", "###", "#.#", "#.#"),
    "I": ("###", ".#.", ".#.", ".#.", "###"),
    "J": ("..#", "..#", "..#", "#.#", ".#."),
    "K": ("#.#", "#.#", "##.", "#.#", "#.#"),
    "L": ("#..", "#..", "#..", "#..", "###"),
    # M and W are five columns wide, not three. At three they came out as
    # solid blobs indistinguishable from N and H — "WIEN" read as "NIEN".
    # The font is variable-width, so the extra pixels cost nothing elsewhere.
    "M": ("#...#", "##.##", "#.#.#", "#...#", "#...#"),
    "W": ("#...#", "#...#", "#.#.#", "#.#.#", ".#.#."),
    "N": ("#.#", "###", "###", "#.#", "#.#"),
    "O": (".#.", "#.#", "#.#", "#.#", ".#."),
    "P": ("##.", "#.#", "##.", "#..", "#.."),
    "Q": (".#.", "#.#", "#.#", "###", ".##"),
    "R": ("##.", "#.#", "##.", "#.#", "#.#"),
    "S": (".##", "#..", ".#.", "..#", "##."),
    "T": ("###", ".#.", ".#.", ".#.", ".#."),
    # U must be flat-bottomed or it reads as V — "UND" was showing as "VND".
    "U": ("#.#", "#.#", "#.#", "#.#", "###"),
    "V": ("#.#", "#.#", "#.#", ".#.", ".#."),
    "X": ("#.#", "#.#", ".#.", "#.#", "#.#"),
    "Y": ("#.#", "#.#", ".#.", ".#.", ".#."),
    "Z": ("###", "..#", ".#.", "#..", "###"),
    "0": (".#.", "#.#", "#.#", "#.#", ".#."),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("##.", "..#", ".#.", "#..", "###"),
    "3": ("##.", "..#", ".#.", "..#", "##."),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "##.", "..#", "##."),
    "6": (".##", "#..", "##.", "#.#", ".#."),
    "7": ("###", "..#", ".#.", "#..", "#.."),
    "8": (".#.", "#.#", ".#.", "#.#", ".#."),
    "9": (".#.", "#.#", ".##", "..#", "##."),
    " ": ("...", "...", "...", "...", "..."),
    ":": ("...", ".#.", "...", ".#.", "..."),
    ".": ("...", "...", "...", "...", ".#."),
    ",": ("...", "...", "...", ".#.", "#.."),
    "-": ("...", "...", "###", "...", "..."),
    "+": ("...", ".#.", "###", ".#.", "..."),
    "/": ("..#", "..#", ".#.", "#..", "#.."),
    "!": (".#.", ".#.", ".#.", "...", ".#."),
    "?": ("##.", "..#", ".#.", "...", ".#."),
    "(": ("..#", ".#.", ".#.", ".#.", "..#"),
    ")": ("#..", ".#.", ".#.", ".#.", "#.."),
    "[": (".##", ".#.", ".#.", ".#.", ".##"),
    "]": ("##.", ".#.", ".#.", ".#.", "##."),
    "'": (".#.", ".#.", "...", "...", "..."),
    "→": ("...", "..#", "###", "..#", "..."),
    "×": ("...", "#.#", ".#.", "#.#", "..."),
    "·": ("...", "...", ".#.", "...", "..."),
}


def _with_accent_row(table: dict, width: int) -> dict:
    """
    Give every glyph a blank row on top, then add the umlauts.

    Glyphs may be wider than the nominal width (M and W in the tiny face
    are), so the blank row is sized per glyph rather than globally.
    """
    built = {
        char: ("." * len(rows[0]),) + rows
        for char, rows in table.items()
    }

    dots = ("#.#" if width == 3 else ".#.#.")
    for accented, plain in (("Ä", "A"), ("Ö", "O"), ("Ü", "U")):
        built[accented] = (dots,) + table[plain]
    return built


BIG = _with_accent_row(_BIG, 5)
TINY = _with_accent_row(_TINY, 3)

BIG_HEIGHT = 8
TINY_HEIGHT = 6
GAP = 1            # blank columns between glyphs, before scaling

_cache: dict = {}


def normalise(text: str) -> str:
    """
    Upper-case the text and fold anything the fonts can't draw.

    ß becomes SS (correct German upper case anyway), and any remaining
    unknown character becomes a space rather than a row of '?'.
    """
    text = (text or "").replace("ß", "SS").upper()
    # Long dashes and non-breaking spaces turn up in the API's disruption text.
    text = text.replace("–", "-").replace("—", "-").replace(" ", " ")
    return text


def _rows_for(char: str, tiny: bool):
    table = TINY if tiny else BIG
    return table.get(char) or table[" "]


def _glyph(char: str, tiny: bool, scale: int, color) -> pygame.Surface:
    key = (char, tiny, scale, color)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    rows = _rows_for(char, tiny)
    width = len(rows[0])
    height = TINY_HEIGHT if tiny else BIG_HEIGHT

    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell == "#":
                surface.set_at((x, y), color)

    if scale != 1:
        surface = pygame.transform.scale(surface, (width * scale, height * scale))

    _cache[key] = surface
    return surface


def measure(text: str, tiny: bool = False, scale: int = 1) -> tuple[int, int]:
    text = normalise(text)
    height = (TINY_HEIGHT if tiny else BIG_HEIGHT) * scale
    if not text:
        return (0, height)

    width = sum(len(_rows_for(char, tiny)[0]) + GAP for char in text) - GAP
    return (width * scale, height)


def draw(surface, text, x, y, color, tiny=False, scale=1, align="left"):
    """
    Draw text and return the rectangle it occupied.

    align: "left" | "right" | "center" — all relative to (x, y) as the top
    edge, which keeps the call sites simple on a grid layout.
    """
    text = normalise(text)
    if not text:
        return pygame.Rect(x, y, 0, 0)

    width, height = measure(text, tiny, scale)
    if align == "right":
        x -= width
    elif align == "center":
        x -= width // 2

    cursor = x
    for char in text:
        surface.blit(_glyph(char, tiny, scale, color), (cursor, y))
        cursor += (len(_rows_for(char, tiny)[0]) + GAP) * scale

    return pygame.Rect(x, y, width, height)


def fit(text: str, max_width: int, tiny=False, scale=1) -> str:
    """Trim text (with a trailing dot) so it fits inside max_width pixels."""
    text = normalise(text)
    if measure(text, tiny, scale)[0] <= max_width:
        return text
    while text and measure(text + ".", tiny, scale)[0] > max_width:
        text = text[:-1]
    return text + "." if text else ""
