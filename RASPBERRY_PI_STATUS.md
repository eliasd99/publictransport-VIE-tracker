# Raspberry Pi — hardware & access

## Current state

- **Raspberry Pi 3A+**, 512MB RAM
- Fresh Raspberry Pi OS, flashed via Raspberry Pi Imager on 2026-09-20
  after the previous card's SSH password was lost.
- Boots to a **console, not the desktop** (`multi-user.target`) — the
  Imager defaults to Desktop, which silently breaks pygame/SDL fullscreen
  output (see README step 1). **For any future from-scratch flash
  of a kiosk Pi, pick the Lite image up front** to skip this switch.
- Hostname, username and IP: set when flashing — not recorded here. Give
  the Pi a static DHCP lease in the router so its address doesn't change.
- **SSH key auth is configured** (`ssh-copy-id` run from your own computer) —
  password login isn't needed for `ssh`, but `sudo` on the Pi still asks
  for the account password interactively, so a one-off remote command
  needs a terminal forced: `ssh -t <user>@<pi-address> 'sudo ...'`.
- Drives an **HDMI monitor**, confirmed working via KMS/DRM at 1920×1080.
- Current project: `~/wldeparture`, the Wiener Linien/ÖBB pixel-art
  departure board — see `DEPARTURE_BOARD.md` for the software side and
  `DASHBOARD_LAYOUT.md` for the on-screen design. `DEPARTURE_BOARD.md`
  also covers keeping it always-on (no console blanking, systemd
  auto-restart) — worth applying on any fresh flash of this Pi.
