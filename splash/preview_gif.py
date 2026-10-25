#!/usr/bin/env python3
"""Make a GIF of the splash so you can preview it without the Pi.

  python3 preview_gif.py frames/braille-110.json splash-preview.gif [columns]
  python3 preview_gif.py frames/half-110.json console.gif 240 --console

Draws the frames the way a terminal would, cropped to a screen `columns`
wide (default 200). --console uses the Pi console's own 16-color palette,
which is a lot harsher than a desktop terminal's (bright green, orange-brown
"yellow"), so you see what the Pi will actually show.
"""

import json
import sys

from PIL import Image, ImageDraw, ImageFont

BITS = [(0, 0, 1), (0, 1, 2), (0, 2, 4), (1, 0, 8), (1, 1, 16), (1, 2, 32), (0, 3, 64), (1, 3, 128)]
BG = (22, 24, 30)
COLORS = {
    ".": (225, 228, 235),  # default
    "g": (105, 110, 122),  # gray
    "w": (255, 255, 255),  # bright white
    "y": (176, 140, 40),   # dim yellow
    "Y": (255, 220, 90),   # bright yellow
    "r": (170, 40, 40),    # red
    "R": (255, 70, 60),    # bright red
    "G": (46, 110, 62),    # dark green
}
# The Linux console's fixed VGA palette, for the codes splash.py sends there.
CONSOLE_COLORS = {
    ".": (255, 255, 255), "g": (85, 85, 85), "w": (255, 255, 255),
    "y": (170, 85, 0), "Y": (255, 255, 85), "r": (170, 0, 0),
    "R": (255, 85, 85), "G": (0, 170, 0),
}
CONSOLE_BG = (0, 0, 0)
INVERSE = {"i": ".", "j": "r", "J": "R"}   # reverse video: light cell, dark character
CELL = (10, 20)
FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "/System/Library/Fonts/Menlo.ttc", "/Library/Fonts/Menlo.ttc"]


def load_font():
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, 16)
        except OSError:
            pass
    return ImageFont.load_default()


def draw_row(d, font, r, text, colors, left, cols):
    for i in range(left, min(len(text), left + cols)):
        ch, code = text[i], colors[i]
        x0, y0 = (i - left) * CELL[0], r * CELL[1]
        if code in INVERSE:
            d.rectangle([x0, y0, x0 + CELL[0] - 1, y0 + CELL[1] - 1], fill=COLORS[INVERSE[code]])
            col = BG
        else:
            col = COLORS.get(code, COLORS["."])
        o = ord(ch)
        if 0x2800 <= o <= 0x28FF:
            code = o - 0x2800
            for dx, dy, b in BITS:
                if code & b:
                    cx, cy = x0 + 3 + dx * 4.5, y0 + 3 + dy * 4.5
                    d.ellipse([cx - 1.4, cy - 1.4, cx + 1.4, cy + 1.4], fill=col)
        elif ch in "▀▄█":
            if ch in "▀█":
                d.rectangle([x0, y0, x0 + CELL[0] - 1, y0 + CELL[1] // 2 - 1], fill=col)
            if ch in "▄█":
                d.rectangle([x0, y0 + CELL[1] // 2, x0 + CELL[0] - 1, y0 + CELL[1] - 1], fill=col)
        elif ch.strip():
            d.text((x0 + 1, y0 + 1), ch, fill=col, font=font)


def main():
    global BG
    args = [a for a in sys.argv[1:] if a != "--console"]
    if "--console" in sys.argv:
        COLORS.update(CONSOLE_COLORS)
        BG = CONSOLE_BG
    src, out = args[0], args[1]
    cols = int(args[2]) if len(args) > 2 else 200
    data = json.load(open(src, encoding="utf-8"))
    rows_table = data["rows"]
    left = max(0, data["final_car_left"] - (cols - data["car_width"]) // 2)
    font = load_font()
    frames = []
    seq = data["frames"] + data["frames"][data["loop_from"]:] * 2
    for f in seq:
        img = Image.new("RGB", (cols * CELL[0], len(f) * CELL[1]), BG)
        d = ImageDraw.Draw(img)
        for r, idx in enumerate(f):
            text, colors = rows_table[idx]
            draw_row(d, font, r, text, colors, left, cols)
        frames.append(img.resize((img.width // 2, img.height // 2), Image.LANCZOS))
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=1000 // data["fps"], loop=0)
    print(f"wrote {out} ({len(frames)} frames)")


if __name__ == "__main__":
    main()
