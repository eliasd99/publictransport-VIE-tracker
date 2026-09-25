# Pilgramgasse Departure Board — project notes

**Status as of 2026-09-20: deployed and running, both 14A directions now
resolved.** The board is live on the HDMI monitor, driven by
`wldeparture.service` on boot. Hardware/access details live in
`RASPBERRY_PI_STATUS.md`; the on-screen design lives in
`DASHBOARD_LAYOUT.md`. This doc covers the software: what it shows, the
APIs behind it, and the deployment gotchas hit along the way.

## Content shown

- U4 both directions, 13A both directions, 14A both directions (all four
  stop IDs confirmed live — see the table below)
- ÖBB connections Wien Meidling → Wulkaprodersdorf, as clock times rather
  than a countdown
- No disruption ticker currently (removed in the stacked-list redesign —
  see `DASHBOARD_LAYOUT.md`)
- Header clock shows `HH:MM:SS`, always in Vienna time (`config.TIMEZONE`),
  whatever the Pi's system timezone is
- The header's "LIVE" dot turns amber / "OFFLINE" when Wiener Linien data
  stops refreshing (`WL_STALE_SECONDS`)
- Delayed ÖBB trains are marked orange ("+N" on the next one); cancelled
  ones are red and struck through

## Refresh rates

Set in `config.py`:

- **Wiener Linien**: every **30s** (`WL_REFRESH_SECONDS`)
- **ÖBB**: every **120s** (`OEBB_REFRESH_SECONDS`) — slower on purpose,
  since it's an unofficial endpoint and trains run roughly hourly anyway

Each worker thread catches every exception around its fetch, so an API
response with an unexpected shape can't kill the thread (which would freeze
a row while the process — and so systemd — thought all was well).

On a failed fetch, the worker loop backs off — each consecutive failure
multiplies the delay (up to 4x), so a struggling API isn't hammered every
30s. Between fetches, the on-screen countdowns still tick down every
second locally, computed from the absolute departure timestamps rather
than waiting on the next API call.

## Data sources / APIs

### Wiener Linien — official open data, no key

`https://www.wienerlinien.at/ogd_realtime/monitor?stopId=...`
Docs: https://www.wienerlinien.at/ogd_realtime/doku/
Licence CC BY 4.0, attribution "Datenquelle: Stadt Wien – data.wien.gv.at".

Stops are identified by **StopID** (RBL number): one number = one station +
one line + one direction. `find_stops.py` resolves these by joining four
published CSVs, which use **English column names** now (`PlatformText`,
`StopID`, `LineText`, ...) — the old German ones (`NAME`, `RBL_NUMMER`,
`BEZEICHNUNG`, ...) no longer exist. Confirmed-live schema (2026-09-20):

| File | Columns |
|---|---|
| `wienerlinien-ogd-haltestellen.csv` | `DIVA;PlatformText;Municipality;MunicipalityID;Longitude;Latitude` |
| `wienerlinien-ogd-haltepunkte.csv` | `StopID;DIVA;StopText;Municipality;MunicipalityID;Longitude;Latitude` |
| `wienerlinien-ogd-fahrwegverlaeufe.csv` | `LineID;PatternID;StopSeqCount;StopID;Direction` |
| `wienerlinien-ogd-linien.csv` | `LineID;LineText;SortingHelp;Realtime;MeansOfTransport` |

If `find_stops.py` ever breaks again with "no station found," check the
live headers first (`curl ... | head -1`) before assuming the join logic
is wrong — this has already happened once.

**Resolved stop IDs for Pilgramgasse** (9 stop points total; these are the
ones this board uses, confirmed live by querying each individually since a
combined query mixes lines together):

| stopId | Line | Direction | Note |
|---|---|---|---|
| 4417 | U4 | → Heiligenstadt | |
| 4420 | U4 | → Hütteldorf | |
| 699 | 13A | → Alser Straße/Skodagasse | shared curb, also serves 14A |
| 699 | 14A | → Neubaugasse | same physical platform as the 13A row above |
| 669 | 13A | → Hauptbahnhof | shared curb, also serves N71 |
| 751 | 14A | → Reumannplatz | platform 1, confirmed live 2026-09-20; serves 14A only |

Filled into `config.py`'s `WL_ROWS`. Because 699 serves two rows (13A and
14A), departure-matching in `main.py` filters by line name as well as
stopId — otherwise both rows would show the same mixed set.

### ÖBB — no official open realtime API exists

`oebb_client.py` talks to the HAFAS `mgate.exe` endpoint the ÖBB app
itself uses (`https://fahrplan.oebb.at/bin/mgate.exe`, access ID
`OWDL4fE4ixNiPBBm`, client `oebbPROD-ADHOC` v6030600, ver 1.45 — public via
the open-source `hafas-client` project). **Unofficial: may break without
notice.** `OEBB_ENABLED = False` in `config.py` disables the row. Still
not verified against the live endpoint end-to-end (only the WL side is
confirmed live so far).

## Design & rendering notes

- Both API clients never raise — failures surface as an `.error` field and
  the board keeps showing the last good data.
- `display.py` auto-detects output: SDL/KMS first (HDMI), falling back to
  raw framebuffer writes. Confirmed picking KMS/DRM directly once
  `getty@tty1` was disabled (see **Lessons learned**) — no offscreen
  fallback.
- Pixel-art rendering (canvas size, bitmap fonts, upscaling), the row
  layout, and the colour palette are all covered in `DASHBOARD_LAYOUT.md`
  rather than duplicated here.

## Keeping it running: no sleep, always-on autostart

Two separate things were involved in the board apparently "going into
standby":

1. **Console/HDMI blanking.** With no desktop session and nothing
   otherwise touching the console, the kernel's own idle-blank timer can
   still blank the display. Fixed by adding `consoleblank=0` to
   `/boot/firmware/cmdline.txt` (see `README.md` step 7). If the screen
   still blanks after that, it's the monitor's own auto-power-save timer
   (check its on-screen menu) — that's hardware, not something the Pi
   controls.
2. **The service not restarting itself.** The original unit had no
   `Restart=` directive, so a crash (or the process getting OOM-killed on
   a 512MB Pi) would just leave the board off until someone noticed and
   ran `systemctl start` by hand. `wldeparture.service` now sets
   `Restart=always`, `RestartSec=3`, and `StartLimitIntervalSec=0` (so
   systemd never permanently gives up after repeated failures — note this
   one must sit in `[Unit]`; an earlier version had it under `[Service]`,
   where systemd silently ignores it). Combined
   with `enable` (already done — `WantedBy=multi-user.target`), pulling
   power and plugging it back in boots straight back to the board with no
   manual step.

## Lessons learned (worth reading before repeating any of this)

1. **The Pi's SSH password was lost.** A first-boot recovery script
   (`systemd.run=` kernel-command-line hook) failed twice — once because
   the script was never actually copied to the boot partition (silent
   no-op), once causing a genuine reboot loop. **Reflashing the card with
   Raspberry Pi Imager** (credentials via the gear icon) was faster and
   safer than debugging a headless boot-time hook blind with no keyboard
   attached. Prefer that path again if this happens.
2. **The reflash defaulted to Raspberry Pi OS with Desktop, not Lite.**
   Not obvious until pygame's SDL fell back to an invisible "offscreen"
   driver — the desktop compositor was holding the display. Fix:
   `sudo systemctl set-default multi-user.target` to boot to a plain
   console. Flash Lite from the start next time to skip this.
3. **Editing files in `nano` over SSH can be unreliable** — arrow-key
   navigation once corrupted `config.py` with garbage characters. For
   config with known-good values, generate the file locally and `scp` it
   over instead of live-editing in nano.
4. `ssh-copy-id` must be run **from your own computer**, not from inside a shell
   already on the Pi.
5. **`ssh host 'sudo ...'` fails** with "a terminal is required to read
   the password" unless a pseudo-terminal is forced with `ssh -t` — a
   plain non-interactive SSH command has no TTY for sudo to prompt on.
6. **`wldeparture.service` originally had `User=pi` and
   `WorkingDirectory=/home/pi/wldeparture`**, left over from a template —
   the real user was different. The unit now ships with a `YOUR_USER`
   placeholder that's filled in with `sed` before installing (README step 8); worth checking any future unit file against the real
   username before `cp`-ing it into `/etc/systemd/system/`.
7. **`ExecStartPre=/bin/sleep 5` hung for the full 90s systemd default
   timeout** on first install (unit stuck in `activating (start-pre)`).
   Cause: the unit claims `/dev/tty1` directly (`TTYPath=/dev/tty1`,
   `StandardInput=tty`), and `getty@tty1` was still enabled and holding
   that console, so opening it blocked indefinitely. Fixed with
   `sudo systemctl disable --now getty@tty1` (this is step 8 in
   `README.md`, easy to miss on a first install). Once disabled, the unit
   started clean and SDL picked KMS/DRM immediately. The current unit
   drops the `ExecStartPre=/bin/sleep 5` entirely rather than relying on
   the sleep to dodge this.
8. An `XDG_RUNTIME_DIR is invalid or not set` line from SDL on startup is
   harmless in this setup (no desktop session, running from a systemd unit
   on tty1) — it's immediately followed by a successful
   `Display: SDL (KMSDRM) ...` line, so it doesn't need chasing.
9. **The service had no `Restart=` directive**, so a crash just left the
   board dark until someone manually restarted it — see "Keeping it
   running" above.

## Open items

- ÖBB client still untested against the live endpoint.
- `consoleblank=0` needs to actually be applied on the Pi's
  `/boot/firmware/cmdline.txt` (README step 7) — it's documented here and
  in the README but is a manual edit, not something this repo can push by
  itself.
