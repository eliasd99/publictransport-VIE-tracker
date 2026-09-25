# Raspberry Pi — hardware & access

## Current state

- **Raspberry Pi 3A+**, 512MB RAM
- Fresh Raspberry Pi OS, flashed via Raspberry Pi Imager on 2026-09-20
  after the previous card's SSH password was lost (see `DEPARTURE_BOARD.md`
  → *Lessons learned*).
- Boots to a **console, not the desktop** (`multi-user.target`) — the
  Imager defaults to Desktop, which silently breaks pygame/SDL fullscreen
  output (see `DEPARTURE_BOARD.md`). **For any future from-scratch flash
  of a kiosk Pi, pick the Lite image up front** to skip this switch.
- Hostname, username and IP: set when flashing — not recorded here. Give
  the Pi a static DHCP lease in the router so its address doesn't change.
- **SSH key auth is configured** (`ssh-copy-id` run from your own computer) —
  password login isn't needed for `ssh`, but `sudo` on the Pi still asks
  for the account password interactively (see `DEPARTURE_BOARD.md` for the
  `ssh -t` gotcha this causes).
- Drives an **HDMI monitor only** — the 3.5" SPI touchscreen from the
  earlier flight-tracker project is not attached. Confirmed working via
  KMS/DRM at 1920×1080.
- Current project: `~/wldeparture`, the Wiener Linien/ÖBB pixel-art
  departure board — see `DEPARTURE_BOARD.md` for the software side and
  `DASHBOARD_LAYOUT.md` for the on-screen design. `DEPARTURE_BOARD.md`
  also covers keeping it always-on (no console blanking, systemd
  auto-restart) — worth applying on any fresh flash of this Pi.

## Historical: flight-tracker era SPI screen (not currently attached)

Kept only in case this screen is ever reattached to a project on this or
another Pi — does not describe the Pi's current setup.

- **Display:** RPI-35LCD — 3.5" resistive touchscreen
  - Controller: ILI9486, 480×320, SPI
  - Driven via the **legacy `fbtft` framebuffer** at `/dev/fb1` (no
    `/dev/dri` node — not a DRM/KMS device)
  - Pixel format: **RGB565** (307,200 bytes = 480×320×2)
  - Kernel driver installed via `goodtft/LCD-show`, overlay:
    `dtoverlay=tft35a:rotate=90`
  - **Side effect:** the `LCD-show` installer rewrites the boot config and
    disables normal HDMI output. Reversing it needs `sudo ./LCD-hdmi`
    (same repo) or manually removing the `tft35a`/`piscreen`/`ads7846`
    overlay lines and ensuring `dtoverlay=vc4-kms-v3d` is present.
- **Touch:** ADS7846 controller, a Linux evdev input device
  (`/dev/input/eventN`) — never wired up in the flight-tracker project.
- **SDL/pygame workaround:** this Pi's SDL2 build had no `fbdev`/`fbcon`
  driver, and the panel has no DRM/KMS node, so no standard SDL video
  driver could address `/dev/fb1` directly. Fix: `SDL_VIDEODRIVER=dummy`,
  render to an off-screen pygame surface, convert each frame to raw
  little-endian RGB565 with **numpy** (vectorized — a per-pixel Python
  loop is too slow on a Pi 3A+), and write those bytes directly to
  `/dev/fb1` instead of `pygame.display.flip()`. The same technique is
  reused as a fallback path in `display.py` in case this screen ever
  comes back.
