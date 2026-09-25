# Pilgramgasse Departure Board

A pixel-art departure board for the Raspberry Pi showing, on one screen:

- **U4** in both directions (Heiligenstadt / Hütteldorf)
- **13A** in both directions
- **14A** in both directions (Neubaugasse / Reumannplatz)
- The next **ÖBB** trains Wien Meidling → Wulkaprodersdorf

Stacked as one full-width list, one row per line/direction — not the
older side-by-side column layout. There's currently no disruption ticker
(removed for readability; see `DASHBOARD_LAYOUT.md` in the project notes).

---

## Before you start: the HDMI problem

Your Pi is currently configured for the 3.5" SPI touchscreen from the flight
tracker. The `goodtft/LCD-show` installer that set that up **rewrites the boot
config and disables normal HDMI output**. So if you just plug in an HDMI
monitor now, you will most likely get no picture — that's the config, not a
broken cable.

**Step 0 is therefore to switch the Pi back to HDMI.** See step 1 below.

The old flight tracker itself is harmless: nothing autostarts, no systemd
service is enabled, so you can leave `~/flighttracker` exactly where it is.
It costs nothing but a few MB of disk.

---

## 1. Switch the Pi back to HDMI output

SSH in:

```bash
ssh <user>@<pi-address>
```

(`<user>` is the account you created when flashing the card, `<pi-address>`
its hostname or IP on your network.)

If you still have the LCD-show folder (you probably do, that's how the screen
was installed), it ships a script that reverses itself:

```bash
cd ~/LCD-show
sudo ./LCD-hdmi
```

That reboots the Pi on its own. Plug the HDMI monitor in **before** it comes
back up — the Pi only detects HDMI at boot.

**If you don't have `~/LCD-show` any more**, edit the boot config by hand:

```bash
sudo nano /boot/firmware/config.txt      # on older Raspberry Pi OS: /boot/config.txt
```

- Put a `#` in front of any line mentioning `tft35a`, `piscreen`, `ads7846`,
  or `dtoverlay=...rotate=90`
- Make sure this line is present and **not** commented out:
  `dtoverlay=vc4-kms-v3d`

Then `sudo reboot`.

After the reboot, check that the Pi really sees an HDMI framebuffer:

```bash
ls /dev/fb*          # expect /dev/fb0
ls /dev/dri/         # expect card0 (and card1) — this means KMS is active
cat /sys/class/graphics/fb0/virtual_size    # e.g. 1920,1080
```

If `/dev/dri/` is empty, KMS didn't load — recheck `config.txt`.

---

## 2. Copy the project to the Pi

From your computer, in the folder containing `wldeparture`:

```bash
scp -r wldeparture <user>@<pi-address>:~/
```

---

## 3. Install the dependencies

```bash
ssh <user>@<pi-address>
sudo apt update
sudo apt install -y python3-pygame python3-numpy python3-requests
```

Use **apt, not pip** for these. On a 512MB Pi 3A+, pip would try to compile
numpy and pygame from source and will run out of memory.

`python3-pygame` and `python3-numpy` are already installed from the flight
tracker, so this will be quick.

Give your user access to the graphics devices (needed for fullscreen output
without a desktop):

```bash
sudo usermod -aG video,render,input "$USER"
```

Log out and back in for that to take effect.

---

## 4. Find the stop IDs

Wiener Linien identify stops by **RBL number** (`stopId`). One number =
one station + one line + one direction, so Pilgramgasse has several.

```bash
cd ~/wldeparture
python3 find_stops.py Pilgramgasse
```

This downloads a few open-data CSV files (cached afterwards) and prints a
table like:

```
   4212   U4                     Pilgramgasse  H1
   4213   U4                     Pilgramgasse  H2
   1856   13A, 14A, 59A          Pilgramgasse  ...
```

To see **which direction** each number serves, query one live:

```bash
python3 wl_client.py 4212
```

It prints the line, countdown and destination — that tells you whether 4212
is the Heiligenstadt or the Hütteldorf platform.

---

## 5. Fill in `config.py`

```bash
nano config.py
```

Put the numbers you found into `WL_ROWS`. The board draws one row per entry,
top to bottom — this is the "stacked list" layout, not side-by-side columns:

```python
WL_ROWS = [
    {"title": "U4",  "subtitle": "Heiligenstadt", "stop_ids": [4212]},
    {"title": "U4",  "subtitle": "Hütteldorf",    "stop_ids": [4213]},
    {"title": "13A", "subtitle": "Skodagasse",    "stop_ids": [1856]},
    {"title": "13A", "subtitle": "Hauptbahnhof",  "stop_ids": [1857]},
]
```

The `subtitle` is just the label drawn on screen — call it whatever is
most useful to you. If one physical stop serves more than one line (a
shared curb often does), give each line its own row with the same
`stop_ids` — the board tells them apart by line name, not just stopId.
This is exactly the situation at Pilgramgasse: stop `699` carries both
`13A` (→ Alser Straße/Skodagasse) and `14A` (→ Neubaugasse), and the board's
`main.py` filters by line name so the two rows never mix departures.

Ctrl+O to save, Ctrl+X to exit.

---

## 6. Test each piece separately

Test them in this order; it makes any failure obvious.

```bash
# a) Can we reach Wiener Linien and parse the answer?
python3 wl_client.py 4212 4213

# b) Does the ÖBB lookup work?
python3 oebb_client.py "Wien Meidling" "Wulkaprodersdorf"

# c) Does the screen work at all? (colour bars for 5 seconds)
python3 display.py

# d) The whole board
python3 main.py
```

Press **Esc** or **q** to quit, or Ctrl+C.

When `main.py` starts it prints which output backend it picked, e.g.
`Display: SDL (kmsdrm) 1920x1080`. If it says `framebuffer /dev/fb0`, SDL
couldn't open the screen and it fell back to writing pixels directly —
that still works, just less efficiently.

---

## 7. Stop the screen from blanking / going to sleep

The Pi itself has no suspend state enabled in this setup — "it went into
standby" is almost always the **console blanking** the HDMI output after a
few minutes of inactivity, which looks identical to the Pi sleeping. Fix it
once, before installing the service:

```bash
sudo nano /boot/firmware/cmdline.txt      # on older Raspberry Pi OS: /boot/cmdline.txt
```

This file is **one single line** — add `consoleblank=0` to the end of it,
separated by a space from whatever's already there (don't add a newline).
Save, then:

```bash
sudo reboot
```

If the screen still blanks after that, it's most likely the **monitor's
own** auto-power-save kicking in after a period it decides looks idle —
check the monitor's own on-screen menu for an "eco"/"power save"/"auto off"
timer and disable it there; that's outside what the Pi can control.

---

## 8. Start it automatically on boot

The unit file ships with a `YOUR_USER` placeholder. Replace it with your
Pi username first:

```bash
sed -i "s/YOUR_USER/$USER/g" ~/wldeparture/wldeparture.service
sudo cp ~/wldeparture/wldeparture.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wldeparture
sudo systemctl start wldeparture
```

The unit is already set up to do the two things that matter for "just leave
it plugged in":

- **`WantedBy=multi-user.target`** (via `enable`) — starts on every boot,
  including after a hard power cut, with no login or manual step needed.
- **`Restart=always` + `StartLimitIntervalSec=0`** — if the process ever
  crashes, hangs, or gets OOM-killed, systemd restarts it after 3 seconds,
  and never permanently gives up, however many times that happens.

Everyday commands:

```bash
sudo systemctl status wldeparture     # is it running?
sudo systemctl restart wldeparture    # after editing config.py
sudo systemctl stop wldeparture       # stop it
journalctl -u wldeparture -f          # live log
```

To stop the login prompt from drawing over the board on tty1:

```bash
sudo systemctl disable --now getty@tty1
```

(Required — the unit claims `/dev/tty1` directly. If you skip this, the
service hangs at start for up to 90 seconds waiting for a console that
`getty@tty1` is still holding open.)

---

## Tweaking the pixel-art look

The board is drawn onto a deliberately tiny canvas and then blown up to the
monitor by a **whole number** — x4 for 1280x720, x6 for 1920x1080 — with no
smoothing. That's what makes the pixels square and crisp rather than blurry.
Anything left over is letterboxed in black.

In `config.py`:

| Setting | Effect |
|---|---|
| `INTERNAL_SIZE` | The canvas. `(320, 180)` is the default. `(240, 135)` gives noticeably chunkier pixels but less room for text. |
| `TICKER_SPEED` | How fast the disruption message scrolls, in board pixels per second. |
| `SCANLINES` | Fake CRT scanlines over the whole image. Off by default — try it and see. |
| `FPS` | 12 by default, because the ticker scrolls and the clock colon blinks. |

The colour palette and the little vehicle sprites are at the top of
`renderer.py`, written as text — `#` is a pixel, `+` is a highlight, `.` is
transparent — so you can redraw them by typing:

```python
SPRITE_BUS = (
    ".#####.",
    "#+++++#",
    ...
)
```

The fonts in `pixelfont.py` are drawn the same way, one glyph at a time.
They're variable-width: `M` and `W` are five pixels wide where most letters
are three, because at three they turned into unreadable blobs.

---

## Troubleshooting

**Black screen, but `systemctl status` says running**
Check the log: `journalctl -u wldeparture -n 50`. The most common cause is
SDL having no video device — confirm `/dev/dri/card0` exists (step 1).
As a fallback, set `DISPLAY_MODE = "fb"` in `config.py`.

**A row is empty / says "keine Abfahrten"**
That stopId probably isn't serving anything right now (night hours) or the
number is wrong. Verify with `python3 wl_client.py <id>`.

**The train row shows an error**
ÖBB has no official public API. This uses the endpoint the ÖBB app itself
talks to, which can change without warning. The rest of the board keeps
working. Set `OEBB_ENABLED = False` in `config.py` to hide the row.

**Screen blanks / "goes into standby" after a while**
See step 7 above (`consoleblank=0`). If that's already set and it still
happens, it's very likely the monitor's own power-saving timer, not the Pi.

**Want to go back to the 3.5" SPI screen**
`cd ~/LCD-show && sudo ./LCD35-show`, then in `config.py` set
`FB_DEVICE = "/dev/fb1"`, `DISPLAY_MODE = "fb"` and
`INTERNAL_SIZE = (240, 160)` — that's exactly half of 480×320, so it still
scales by a whole number. At that size drop to
`WL_DEPARTURES_PER_ROW = 2` and trim `WL_ROWS` down to what still fits.

---

## Files

| File | What it does |
|---|---|
| `config.py` | All settings — stop IDs, colours, refresh rates |
| `find_stops.py` | Resolves station names to stopIds from the open-data CSVs |
| `wl_client.py` | Wiener Linien realtime API |
| `oebb_client.py` | ÖBB connection lookup |
| `display.py` | Output backends (SDL/HDMI, raw framebuffer) + integer upscaling |
| `pixelfont.py` | The hand-drawn bitmap fonts |
| `renderer.py` | Draws the board — palette and sprites live at the top |
| `main.py` | Ties it together, background refresh threads |
| `wldeparture.service` | systemd unit for autostart (auto-restart, boots straight to the board) |

## A note on the APIs

**Wiener Linien** is a proper open-government data service: free, no key, no
registration, documented at
<https://www.wienerlinien.at/ogd_realtime/doku/>. Data is licensed
CC BY 4.0 — "Datenquelle: Stadt Wien – data.wien.gv.at".

**ÖBB** publishes no equivalent open realtime API. `oebb_client.py` uses the
HAFAS endpoint their own app uses. It works well, but it's unofficial: treat
it as a nice-to-have, poll it gently (the default is every 2 minutes), and
don't be surprised if it needs adjusting some day.
