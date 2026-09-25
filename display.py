"""
Output backends.

The board is always drawn onto an off-screen pygame surface. How that
surface reaches the glass depends on the hardware:

  SdlDisplay          – normal SDL fullscreen. This is what an HDMI monitor
                        should use (SDL talks to the KMS/DRM driver).
  FramebufferDisplay  – writes raw pixels straight into /dev/fbN. Needed on
                        this Pi's old 3.5" SPI LCD, which has no DRM node,
                        and a useful fallback if SDL can't open a video
                        device for HDMI either.

Keeping both behind the same tiny interface (`.size`, `.show(surface)`,
`.close()`) means main.py doesn't care which one is in use.
"""

from __future__ import annotations

import os

import numpy as np
import pygame


def _read_sys(path: str) -> str | None:
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Pixel-perfect upscaling
# ---------------------------------------------------------------------------


class Scaler:
    """
    Blow the small board canvas up to the screen.

    The whole point of the pixel-art look is that one board pixel becomes an
    exact square block of screen pixels, so we scale by a WHOLE number with
    pygame.transform.scale (nearest neighbour — no blending) and letterbox
    whatever is left over. Using smoothscale here, or a fractional factor,
    would give soft edges and uneven pixel sizes and ruin the effect.
    """

    def __init__(self, target_size, scanlines: bool = False):
        self.target = target_size
        self.scanlines = scanlines
        self._canvas = pygame.Surface(target_size)
        self._overlay = None
        self._factor = None

    def _build_overlay(self):
        width, height = self.target
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        for y in range(0, height, 3):
            pygame.draw.line(overlay, (0, 0, 0, 60), (0, y), (width, y))
        return overlay

    def fit(self, surface: pygame.Surface) -> pygame.Surface:
        source_w, source_h = surface.get_size()
        target_w, target_h = self.target

        if (source_w, source_h) == self.target and not self.scanlines:
            return surface

        factor = min(target_w // source_w, target_h // source_h)

        if factor >= 1:
            scaled = pygame.transform.scale(
                surface, (source_w * factor, source_h * factor)
            )
        else:
            # Screen is smaller than the canvas — rare, but don't crash.
            scaled = pygame.transform.smoothscale(surface, self.target)

        if scaled.get_size() == self.target:
            output = scaled
        else:
            self._canvas.fill((0, 0, 0))
            self._canvas.blit(
                scaled,
                ((target_w - scaled.get_width()) // 2,
                 (target_h - scaled.get_height()) // 2),
            )
            output = self._canvas

        if self.scanlines:
            if self._overlay is None:
                self._overlay = self._build_overlay()
            if output is scaled:
                self._canvas.blit(scaled, (0, 0))
                output = self._canvas
            output.blit(self._overlay, (0, 0))

        self._factor = factor
        return output

    @property
    def factor(self):
        return self._factor


# ---------------------------------------------------------------------------


class SdlDisplay:
    """Standard SDL output — fullscreen on HDMI, or a window for testing."""

    def __init__(self, size=None, windowed=False, scanlines=False):
        pygame.display.init()
        if windowed:
            self.screen = pygame.display.set_mode(size or (1280, 720))
        else:
            # (0, 0) asks SDL for the current desktop/display resolution.
            self.screen = pygame.display.set_mode(size or (0, 0), pygame.FULLSCREEN)
            pygame.mouse.set_visible(False)
        self.size = self.screen.get_size()
        self.driver = pygame.display.get_driver()
        self.scaler = Scaler(self.size, scanlines)

    def show(self, surface: pygame.Surface) -> None:
        self.screen.blit(self.scaler.fit(surface), (0, 0))
        pygame.display.flip()

    def close(self) -> None:
        pygame.display.quit()

    def __str__(self) -> str:
        return f"SDL ({self.driver}) {self.size[0]}x{self.size[1]}"


# ---------------------------------------------------------------------------


class FramebufferDisplay:
    """
    Write pixels directly to a Linux framebuffer device.

    Geometry and pixel format are read from /sys/class/graphics/fbN/ rather
    than hardcoded, so the same code handles the 16-bit SPI panel and a
    32-bit HDMI framebuffer.
    """

    def __init__(self, device: str = "/dev/fb0", scanlines: bool = False):
        self.device = device
        node = os.path.basename(device)
        sysfs = f"/sys/class/graphics/{node}"

        virtual = _read_sys(f"{sysfs}/virtual_size")
        if not virtual:
            raise RuntimeError(f"cannot read geometry for {device}")
        width, height = (int(v) for v in virtual.split(","))

        bpp = int(_read_sys(f"{sysfs}/bits_per_pixel") or 16)
        if bpp not in (16, 32):
            raise RuntimeError(f"unsupported colour depth {bpp} on {device}")

        stride = int(_read_sys(f"{sysfs}/stride") or 0) or width * (bpp // 8)

        self.size = (width, height)
        self.bpp = bpp
        self.stride = stride
        self._padding = stride - width * (bpp // 8)

        try:
            self._fb = open(device, "wb", buffering=0)
        except OSError as exc:
            raise RuntimeError(f"cannot open {device}: {exc}") from exc

        self.scaler = Scaler(self.size, scanlines)
        self._hide_cursor()

    @staticmethod
    def _hide_cursor() -> None:
        """Stop the console cursor blinking on top of the board."""
        try:
            with open("/sys/class/graphics/fbcon/cursor_blink", "w") as handle:
                handle.write("0")
        except OSError:
            pass

    def show(self, surface: pygame.Surface) -> None:
        surface = self.scaler.fit(surface)

        # pixels3d gives (width, height, 3); the framebuffer wants row-major,
        # so transpose to (height, width, 3).
        rgb = pygame.surfarray.pixels3d(surface).transpose(1, 0, 2)

        if self.bpp == 16:
            r = rgb[:, :, 0].astype(np.uint16)
            g = rgb[:, :, 1].astype(np.uint16)
            b = rgb[:, :, 2].astype(np.uint16)
            packed = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            data = packed.astype("<u2")
        else:
            # Linux 32-bit framebuffers are almost always BGRX.
            height, width, _ = rgb.shape
            data = np.zeros((height, width, 4), dtype=np.uint8)
            data[:, :, 0] = rgb[:, :, 2]   # blue
            data[:, :, 1] = rgb[:, :, 1]   # green
            data[:, :, 2] = rgb[:, :, 0]   # red
            data[:, :, 3] = 255            # unused/alpha

        del rgb  # release pixels3d's lock on the surface

        raw = data.tobytes()
        if self._padding:
            # Pad each row out to the hardware stride.
            row_bytes = self.size[0] * (self.bpp // 8)
            pad = b"\x00" * self._padding
            raw = b"".join(
                raw[i * row_bytes:(i + 1) * row_bytes] + pad
                for i in range(self.size[1])
            )

        self._fb.seek(0)
        self._fb.write(raw)

    def close(self) -> None:
        try:
            self._fb.close()
        except OSError:
            pass

    def __str__(self) -> str:
        return f"framebuffer {self.device} {self.size[0]}x{self.size[1]} @{self.bpp}bpp"


# ---------------------------------------------------------------------------


def open_display(mode: str = "auto", fb_device: str = "/dev/fb0",
                 fallback_size=(1280, 720), scanlines: bool = False):
    """
    Pick an output backend.

    "auto" tries the good option first (SDL, which gives HDMI proper
    hardware-accelerated output) and quietly falls back to raw framebuffer
    writes if SDL has no usable video driver — which is exactly the
    situation this Pi was in with the SPI screen.
    """
    if mode == "window":
        return SdlDisplay(size=fallback_size, windowed=True, scanlines=scanlines)

    if mode == "sdl":
        return SdlDisplay(scanlines=scanlines)

    if mode == "fb":
        return FramebufferDisplay(fb_device, scanlines=scanlines)

    # auto
    errors = []
    try:
        display = SdlDisplay(scanlines=scanlines)
        # A 0x0 or absurdly small mode means SDL "succeeded" uselessly.
        if display.size[0] >= 320 and display.size[1] >= 240:
            return display
        display.close()
        errors.append(f"SDL returned {display.size}")
    except Exception as exc:                       # noqa: BLE001 - report and move on
        errors.append(f"SDL: {exc}")

    for candidate in (fb_device, "/dev/fb0", "/dev/fb1"):
        try:
            return FramebufferDisplay(candidate, scanlines=scanlines)
        except Exception as exc:                   # noqa: BLE001
            errors.append(f"{candidate}: {exc}")

    raise RuntimeError("no usable display found -> " + " | ".join(errors))


if __name__ == "__main__":
    # Smoke test: fill the screen with three colour bars for 5 seconds.
    import time

    pygame.init()
    out = open_display(os.environ.get("DISPLAY_MODE", "auto"))
    print("using:", out)

    w, h = out.size
    canvas = pygame.Surface((w, h))
    for index, colour in enumerate([(200, 40, 40), (40, 200, 80), (50, 90, 220)]):
        canvas.fill(colour, pygame.Rect(0, h * index // 3, w, h // 3))
    out.show(canvas)
    time.sleep(5)
    out.close()
