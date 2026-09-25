# Departure board — chosen layout (design decision)

**Status as of 2026-09-20: implemented, deployed, and confirmed live** on
the HDMI monitor at 1920×1080 via `wldeparture.service` — deployment
gotchas are in `DEPARTURE_BOARD.md`, not here.

## Design exploration

Three layout variants were mocked up; "B — Stacked List" is the one
picked.

## Why a redesign

The original 4-column pixel-art layout worked but was flagged as hard to
read, and the blinking clock colon was unwanted ("informative but not
attention-seeking, no blinking").

## Chosen layout: single full-width list

- One vertical list, one row per line/direction, instead of 4 side-by-side
  columns — less eye movement, no column-gutter guessing.
- Each row: small pixel pictogram (train vs. bus) → colored line badge →
  destination → (right-aligned) one "next departure" number + two smaller
  upcoming ones, all in **one row** (no separate "then ..." row — that's
  what let 7 groups fit in 540px height).
- Top header bar (full width): "NÄCHSTE ABFAHRTEN" label on the left,
  **current time (`HH:MM:SS`)** + a static "LIVE" status dot on the
  right — the dot does **not** blink. It turns amber and reads "OFFLINE"
  once the Wiener Linien data is older than `WL_STALE_SECONDS` (90s), so
  countdowns running on old data are never labelled live. Seconds were
  added after the first pass at user request.
- No disruption ticker in this variant (removed per request) — if
  disruptions need to come back, they'd need their own row or a
  re-introduced side panel.
- Row divider lines run the full board width.

## Content shown (rows, top to bottom)

1. U4 → Heiligenstadt
2. U4 → Hütteldorf
3. 13A → Alser Straße/Skodagasse
4. 13A → Hauptbahnhof
5. 14A → Neubaugasse (shares stop 699 with 13A)
6. 14A → Reumannplatz (stop 751, its own platform — confirmed live
   2026-09-20)
7. ÖBB Meidling → Wulkaprodersdorf

- U4/13A/14A rows: countdown in **minutes** — one emphasised "next" number
  + two smaller upcoming ones + "MIN" suffix.
- ÖBB row: three **clock times** (e.g. 13:45 → 14:45 → 15:45) instead of a
  countdown — the regional train runs roughly hourly, so actual departure
  times are more useful than a countdown. Times are the real (delay-adjusted)
  ones; a delayed next train gets a small orange "+N", later delayed trains
  are drawn orange, and a cancelled train is red and struck through.

## Typography / sizing / color (implemented values)

- Fonts: hand-drawn bitmap faces in `pixelfont.py` (5×7 "BIG", 3×5
  "TINY"), the same ones the original 4-column board used. Added `[`/`]`
  glyphs to both faces (originally for a "[stop unresolved]" placeholder
  that no longer appears now both 14A rows are resolved, but kept since
  other short bracketed labels may want them later).
- **Sizing pass (post-deployment):** the first version of this layout used
  2x-scaled digits for the "next" departure and the header clock, which
  read as oversized on the actual monitor. Every number and the clock are
  now drawn at the same base scale as the rest of the board; the "next"
  departure and header clock are still picked out, but by **colour**
  (amber/red accent vs. dimmed grey) rather than by being blown up to
  double size. Net effect: a smaller, more consistent, less
  glasses-required board.
- Background: near-black `#0B0F0E`. Primary text: warm off-white `#F4EFE1`.
- Line badge colors (still placeholders — not the real Wiener
  Linien/ÖBB brand hex values):
  - U4: green `#2E8B57`
  - 13A: amber `#E8A33D`
  - 14A: light blue `#3DA5D9` (distinct from 13A so the two buses don't
    blur together)
  - ÖBB: red `#C81E2C`
- Status dot: static teal-green `#3DDC97` while live, amber `#FFC744` when
  the data is stale — never blinking.

## Implementation notes

- `renderer.py`'s `Board._rows()` walks `config.WL_ROWS` plus one synthetic
  ÖBB row, splitting the available height evenly (extra pixels go to the
  earliest rows). This replaced the old 4-column `_columns()`/`_column()`
  panel-based drawing entirely — rows are flat with a dotted full-width
  divider, no bordered panel per item.
- `config.WL_COLUMNS` was renamed to `WL_ROWS` (same shape: title,
  subtitle, stop_ids) — `find_stops.py`'s hint text and `README.md` were
  updated to match.
- **Bug fixed while wiring this up**: stop 699 serves both 13A and 14A.
  The old `departures_for()` only matched by stopId, so both rows would
  have shown the same mixed departures. It now also filters by line name
  whenever `stop_ids` is given (see `DEPARTURE_BOARD.md`).
- The disruption ticker code (`_ticker()`, the alert sprite, the blinking
  clock colon) was deleted rather than disabled. `SHOW_DISRUPTIONS` still
  exists in `config.py` (defaulting to `False`) purely to control whether
  the API is asked for disruption text; nothing currently renders it.
- Verified pre-deployment by rendering a frame with mocked departure data
  (no network calls) and inspecting the upscaled PNG; verified
  post-deployment on the real monitor.

## Open items

- Decide whether disruptions get reintroduced somewhere in this layout.
