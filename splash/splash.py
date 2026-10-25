#!/usr/bin/env python3
"""Mr. Bean boot splash.

Plays the pre-rendered animation from frames/ (made by build_frames.py),
types the tagline, then loops the idle part until systemd stops it when the
head unit UI takes over.

No Pillow and no image work at boot: it loads one JSON file and prints text.

Things it does to look clean on the Pi's console:
  * Waits until the screen is actually up (framebuffer exists and the
    console size has stopped changing) before drawing anything, then holds
    the empty night scene for a moment so the monitor has time to sync.
  * Only redraws the characters that changed since the last frame, and
    never clears a line first, so there are no flickering lines.
  * Notices if the console size changes mid-animation and redraws.

Settings (environment variables, also set in the service file):
  SPLASH_STYLE=half|braille  force a style (default: half on the console,
                             braille in other terminals)
  SPLASH_PREROLL=2.0         seconds to hold the empty scene before he drives in
  SPLASH_WAIT_MAX=10         longest to wait for the screen to be ready
  SPLASH_ONCE=1              exit after the intro instead of looping
"""

import glob
import json
import math
import os
import random
import signal
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FRAME_DIR = os.path.join(HERE, "frames")
TAGLINE = "2001 Mazda Miata SE  /  British Racing Green"
STAR_DENSITY = 0.02     # share of sky cells above the animation that get a star

# Color codes in the frames -> ANSI.
ANSI = {
    ".": "0",       # default
    "g": "0;90",    # gray
    "w": "1;97",    # bright white
    "y": "0;33",    # dim yellow
    "Y": "1;93",    # bright yellow
    "r": "0;31",    # red
    "R": "1;91",    # bright red
    "G": "0;32",    # dark green
}
# The Linux console only knows the 8 basic colors; bold makes the bright ones.
# Default text there is a dim gray, so the car (the only thing drawn in the
# default color) is made bright white.
ANSI_CONSOLE = dict(ANSI, **{".": "1;37"}, g="1;30", w="1;37", Y="1;33", R="1;31")

out = sys.stdout


def write(s):
    out.write(s)
    out.flush()


def move(row, col):
    return f"\033[{row + 1};{col + 1}H"


def term_size():
    try:
        size = os.get_terminal_size(out.fileno())
        return size.columns, size.lines
    except OSError:
        return 80, 24


def on_console():
    return os.environ.get("TERM", "linux") in ("linux", "dumb")


def wait_for_screen():
    """Wait until the framebuffer exists and the console size is stable."""
    deadline = time.monotonic() + float(os.environ.get("SPLASH_WAIT_MAX", "10"))
    if on_console():
        while not os.path.exists("/sys/class/graphics/fb0") and time.monotonic() < deadline:
            time.sleep(0.1)
    last, stable = None, 0
    while time.monotonic() < deadline and stable < 4:
        size = term_size()
        stable = stable + 1 if size == last and size[0] >= 80 else 0
        last = size
        time.sleep(0.1)


def pick_style():
    forced = os.environ.get("SPLASH_STYLE")
    if forced in ("half", "braille"):
        return forced
    return "half" if on_console() else "braille"


def pick_file(style, cols):
    """Largest pre-rendered car that fits the screen width."""
    sizes = sorted(int(os.path.basename(p).split("-")[1].split(".")[0])
                   for p in glob.glob(os.path.join(FRAME_DIR, f"{style}-*.json")))
    if not sizes:
        sys.exit(f"no frames for style '{style}' in {FRAME_DIR}; run build_frames.py")
    fits = [s for s in sizes if s + 10 <= cols]
    return os.path.join(FRAME_DIR, f"{style}-{max(fits) if fits else min(sizes)}.json")


class Screen:
    """Draws frames, sending only the characters that changed."""

    def __init__(self, data, style):
        self.data = data
        self.blank = " " if style == "half" else "⠀"
        self.palette = ANSI_CONSOLE if on_console() else ANSI
        self.sync = not on_console()   # terminals that support synchronized output
        self.layout()

    def layout(self):
        self.cols, self.rows = term_size()
        self.anim_h = len(self.data["frames"][0])
        # Sit the scene a bit below center so there's more sky above it.
        self.top = max(0, min(self.rows - self.anim_h - 3, (self.rows - self.anim_h) * 2 // 3))
        self.make_sky()
        # Park the car in the middle; the rest of the canvas is clipped.
        self.start = (self.cols - self.data["car_width"]) // 2 - self.data["final_car_left"]
        self.shown = [None] * self.anim_h
        write("\033[0m\033[?25l\033[2J")

    def make_sky(self):
        """Stars for the rows above the animation, so the sky fills the screen.

        They twinkle on the same clock as the stars baked into the frames, so
        the idle loop stays seamless.
        """
        rng = random.Random(11)
        n = int(self.cols * self.top * STAR_DENSITY)
        self.stars = [(rng.randrange(self.cols), rng.randrange(self.top), rng.random() * 6.28,
                       rng.random() < 0.25, rng.choice((1, 2))) for _ in range(n)]
        self.sky_shown = {}

    def sky(self, t):
        if not self.stars:
            return []
        loop_s = self.data.get("loop_s") or 1.6
        fade = min(1.0, max(0.0, t / 0.6))
        fade = fade * fade * (3 - 2 * fade)
        buf = []
        for i, (c, r, ph, bright, cyc) in enumerate(self.stars):
            v = (0.5 + 0.5 * math.sin(ph + 2 * math.pi * cyc * t / loop_s)) * fade
            if v < 0.25:
                cell = (" ", ".")
            else:
                ch = "*" if (bright and v > 0.75) else ("+" if v > 0.7 else ".")
                cell = (ch, "w" if bright and v > 0.6 else "g")
            if self.sky_shown.get(i) != cell:
                self.sky_shown[i] = cell
                buf.append(move(r, c) + f"\033[{self.palette.get(cell[1], '0')}m" + cell[0])
        return buf

    def visible(self, idx):
        """The on-screen slice of a canvas row (text, colors), padded to width."""
        text, colors = self.data["rows"][idx]
        lo = max(0, -self.start)
        hi = min(len(text), self.cols - self.start)
        pad = max(0, self.start)
        t = " " * pad + text[lo:hi]
        c = "." * pad + colors[lo:hi]
        t = t[:self.cols].ljust(self.cols)
        c = c[:self.cols].ljust(self.cols, ".")
        return t, c

    def span(self, t, c, a, b):
        parts, current = [], None
        for i in range(a, b):
            code = self.palette.get(c[i], "0")
            if code != current:
                parts.append(f"\033[{code}m")
                current = code
            parts.append(t[i])
        return "".join(parts)

    def show(self, frame, t=0.0):
        if term_size() != (self.cols, self.rows):
            self.layout()
        buf = self.sky(t)
        for r, idx in enumerate(frame):
            old = self.shown[r]
            if old == idx:
                continue
            t, c = self.visible(idx)
            if old is None:
                buf.append(move(self.top + r, 0) + self.span(t, c, 0, self.cols))
            else:
                ot, oc = self.visible(old)
                i = 0
                while i < self.cols:
                    if t[i] == ot[i] and c[i] == oc[i]:
                        i += 1
                        continue
                    j = i
                    gap = 0
                    while j < self.cols and gap < 4:   # merge nearby changes
                        if t[j] != ot[j] or c[j] != oc[j]:
                            gap = 0
                        else:
                            gap += 1
                        j += 1
                    end = j - gap
                    buf.append(move(self.top + r, i) + self.span(t, c, i, end))
                    i = j
            self.shown[r] = idx
        if buf:
            body = "".join(buf) + "\033[0m"
            if self.sync:
                body = "\033[?2026h" + body + "\033[?2026l"
            write(body)

    def tagline(self):
        row = self.top + self.anim_h + 1
        left = max(0, (self.cols - len(TAGLINE)) // 2)
        for n in range(1, len(TAGLINE) + 1):
            write(move(row, left) + f"\033[{self.palette['g']}m" + TAGLINE[:n] + "\033[0m")
            time.sleep(0.018)


def play(screen, frames, fps, first_index):
    frame_time = 1 / fps
    next_t = time.monotonic()
    for n, frame in enumerate(frames):
        screen.show(frame, (first_index + n) / fps)
        next_t += frame_time
        delay = next_t - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        elif delay < -0.25:      # fell far behind (busy boot): don't rush to catch up
            next_t = time.monotonic()


def on_sigterm(signum, frame):
    raise SystemExit(0)


def main():
    signal.signal(signal.SIGTERM, on_sigterm)
    wait_for_screen()

    style = pick_style()
    with open(pick_file(style, term_size()[0]), encoding="utf-8") as f:
        data = json.load(f)
    screen = Screen(data, style)
    frames, fps = data["frames"], data["fps"]
    loop_from = data.get("loop_from", len(frames))

    # Hold the opening (empty night scene) so the monitor can catch up.
    screen.show(frames[0])
    time.sleep(float(os.environ.get("SPLASH_PREROLL", "2.0")))

    play(screen, frames[:loop_from], fps, 0)
    screen.tagline()
    if os.environ.get("SPLASH_ONCE"):
        return
    loop = frames[loop_from:] or frames[-1:]
    first = loop_from if frames[loop_from:] else len(frames) - 1
    while True:
        play(screen, loop, fps, first)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        write("\033[0m\033[?25h" + move(term_size()[1] - 1, 0))
