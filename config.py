"""
Configuration for the Pilgramgasse departure board.

Everything you'd normally want to tweak lives in this one file.
After changing it:  sudo systemctl restart wldeparture
"""

# ---------------------------------------------------------------------------
# Wiener Linien stop IDs (RBL numbers)
# ---------------------------------------------------------------------------
# Each stopId = one station + one line + one direction.
# Run  python3 find_stops.py Pilgramgasse  on the Pi to discover these,
# then paste the numbers here.
#
# The board draws one row per entry in this list, top to bottom, in this
# order — this is the "stacked list" layout (see DASHBOARD_LAYOUT.md in the
# project). A physical stop can serve more than one line (699 below serves
# both 13A and 14A), so main.py filters by stop_id *and* line name to keep
# their departures from mixing into each other's row.

WL_ROWS = [
    # label shown on screen   stopIds (one or more)
    {"title": "U4",  "subtitle": "Heiligenstadt",           "stop_ids": [4417]},
    {"title": "U4",  "subtitle": "Hütteldorf",              "stop_ids": [4420]},
    {"title": "13A", "subtitle": "Alser Str./Skodagasse",   "stop_ids": [699]},
    {"title": "13A", "subtitle": "Hauptbahnhof",            "stop_ids": [669]},
    # Stop 699 is the same physical platform as the 13A row above (a shared
    # curb) — it also serves 14A towards Neubaugasse. main.py's
    # departures_for() filters by line name as well as stop_id, so this row
    # only ever picks up 14A departures, not the 13A ones sharing the stop.
    {"title": "14A", "subtitle": "Neubaugasse",             "stop_ids": [699]},
    # The return direction is a separate platform at Pilgramgasse (stop 751,
    # platform 1) — confirmed live on 2026-09-20 to serve 14A only, towards
    # Reumannplatz. Earlier notes flagged 751 as unverified; it's now been
    # queried directly against the Wiener Linien monitor endpoint and checks
    # out, so both 14A directions are wired up the same way as U4 and 13A.
    {"title": "14A", "subtitle": "Reumannplatz",            "stop_ids": [751]},
]

# Show at most this many upcoming departures per row (one big "next" number
# plus this-minus-one smaller upcoming ones).
WL_DEPARTURES_PER_ROW = 3

# How often to ask Wiener Linien for fresh data, in seconds.
# Be polite: the API is free and unauthenticated. 30s is plenty —
# the countdowns on screen tick down every second on their own.
WL_REFRESH_SECONDS = 30

# If the last successful Wiener Linien update is older than this, the header's
# "LIVE" dot turns amber and reads "OFFLINE" — the countdowns keep ticking from
# the last data, but you can see it's no longer being refreshed. 90s = two
# missed refreshes in a row.
WL_STALE_SECONDS = 90

# Ask the API for disruption/Störung text alongside departures. The current
# "stacked list" layout has no ticker to display it (removed — see
# DASHBOARD_LAYOUT.md), so this currently only affects how much the API
# calls fetch, not anything drawn on screen.
SHOW_DISRUPTIONS = False

# ---------------------------------------------------------------------------
# ÖBB train connection
# ---------------------------------------------------------------------------
# Set OEBB_ENABLED = False to drop the train row entirely.
OEBB_ENABLED = True

OEBB_FROM = "Wien Meidling"
OEBB_TO = "Wulkaprodersdorf"

# How many connections to show.
OEBB_RESULTS = 3

# Trains run roughly hourly, so there is no point hammering this endpoint.
OEBB_REFRESH_SECONDS = 120

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
# All times on the board (header clock, ÖBB departures) are shown in this
# timezone, regardless of what the Pi's system clock is set to.
TIMEZONE = "Europe/Vienna"

# "auto"   – try HDMI via SDL/KMS, then fall back to writing the framebuffer
# "sdl"    – force a normal SDL window/fullscreen (HDMI)
# "fb"     – force raw framebuffer writes (set FB_DEVICE below)
# "window" – windowed, for testing on a laptop
DISPLAY_MODE = "auto"

FB_DEVICE = "/dev/fb0"   # /dev/fb0 = HDMI, /dev/fb1 = the old 3.5" SPI LCD

# Only used when the resolution can't be detected automatically.
FALLBACK_SIZE = (1280, 720)

# ---------------------------------------------------------------------------
# Pixel-art canvas
# ---------------------------------------------------------------------------
# The board is drawn at this small size and then blown up to the monitor by
# a WHOLE number (x4, x5, x6 ...) with no smoothing — that is what makes the
# pixels square and crisp. Any leftover space is letterboxed in black.
#
#   320x180  ->  x4 = 1280x720, x6 = 1920x1080   (both exact — the default)
#   240x135  ->  x8 = 1920x1080                  (chunkier, less text fits)
#   240x160  ->  x2 = 480x320                    (the old 3.5" SPI screen)
#
# Smaller canvas = bigger, chunkier pixels but less room for text.
INTERNAL_SIZE = (320, 180)

# Kept for a possible future disruption ticker (currently unused — the
# stacked-list layout has no ticker; see DASHBOARD_LAYOUT.md "Not yet done").
TICKER_SPEED = 14

# Fake CRT scanlines drawn over the upscaled image.
SCANLINES = False

# Frames per second. Nothing on the board animates any more — the fastest
# change is the header clock's seconds — so 2 is plenty and keeps the Pi cool.
FPS = 2

# The colour palette lives at the top of renderer.py, next to the sprites.
