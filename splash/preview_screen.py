#!/usr/bin/env python3
"""Preview the whole screen exactly as the Pi's console will show it.

  pip3 install pyte pillow
  python3 preview_screen.py screen.gif                  full screen, 30 fps
  python3 preview_screen.py screen.gif --size 160x45    a smaller screen
  python3 preview_screen.py splash-preview-screen.gif --fps 15   the README GIF

Runs the real splash.py against an emulated Linux console (default 240x67,
what a 1080p screen gives you), so the sky, layout, tagline and colors are
the same as on the Pi. Also saves a still of the idle scene next to the GIF
(screen.png). --fps 15 halves the file size, which is what the README uses.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.update(TERM="linux", SPLASH_WAIT_MAX="0", SPLASH_PREROLL="0", SPLASH_ONCE="")
import pyte
from PIL import Image, ImageDraw, ImageFont
import splash

ap = argparse.ArgumentParser(description="Preview the splash as the Pi's console shows it.")
ap.add_argument("out", help="GIF to write (.gif is added if missing)")
ap.add_argument("--size", default="240x67", help="console size in characters, COLSxROWS")
ap.add_argument("--fps", type=int, default=30, choices=(30, 15, 10), help="GIF frame rate")
args = ap.parse_args()
OUT = args.out if args.out.lower().endswith(".gif") else args.out + ".gif"
COLS, ROWS = (int(v) for v in args.size.lower().split("x"))
STEP = 30 // args.fps
CW, CH = 6, 12   # pixels per character in the GIF
scr = pyte.Screen(COLS, ROWS); stream = pyte.Stream(scr)
class Out:
    def write(self, s): stream.feed(s)
    def flush(self): pass
    def fileno(self): return 1
splash.out = Out()
splash.term_size = lambda: (COLS, ROWS)
splash.time.sleep = lambda s: None
BASE = {"black": (0,0,0), "red": (170,0,0), "green": (0,170,0), "brown": (170,85,0),
        "blue": (0,0,170), "magenta": (170,0,170), "cyan": (0,170,170), "white": (170,170,170), "default": (170,170,170)}
BRIGHT = {"black": (85,85,85), "red": (255,85,85), "green": (85,255,85), "brown": (255,255,85),
          "blue": (85,85,255), "magenta": (255,85,255), "cyan": (85,255,255), "white": (255,255,255), "default": (255,255,255)}
FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",   # Linux / Pi
              "/System/Library/Fonts/Menlo.ttc",                       # macOS
              "/System/Library/Fonts/Monaco.ttf",
              "C:/Windows/Fonts/consola.ttf"]                          # Windows


def load_font(size):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


font = load_font(int(CH * 0.85))
imgs = []
def snap():
    im = Image.new("RGB", (COLS * CW, ROWS * CH)); d = ImageDraw.Draw(im)
    for y in range(ROWS):
        line = scr.buffer[y]
        for x in range(COLS):
            c = line[x]
            if c.data in (" ", ""): continue
            col = (BRIGHT if c.bold else BASE).get(c.fg, (170,170,170))
            if c.data in "█▀▄▌▐":
                x0, y0 = x*CW, y*CH
                box = {"█": (0,0,CW,CH), "▀": (0,0,CW,CH//2), "▄": (0,CH//2,CW,CH), "▌": (0,0,CW//2,CH), "▐": (CW//2,0,CW,CH)}[c.data]
                d.rectangle((x0+box[0], y0+box[1], x0+box[2]-1, y0+box[3]-1), fill=col)
            else:
                d.text((x*CW, y*CH), c.data, fill=col, font=font)
    imgs.append(im.convert("P", palette=Image.ADAPTIVE, colors=32))
orig = splash.Screen.show
count = [0]
def show(self, frame, t=0.0):
    orig(self, frame, t); count[0] += 1
    if count[0] > 210 + 48 * 2: raise KeyboardInterrupt
    snap()
splash.Screen.show = show
otag = splash.Screen.tagline
def tagline(self):
    otag(self); snap()
splash.Screen.tagline = tagline
try: splash.main()
except KeyboardInterrupt: pass
still = imgs[int(len(imgs) * 0.8)]
imgs = imgs[::STEP]
imgs[0].save(OUT, save_all=True, append_images=imgs[1:], duration=round(1000 * STEP / 30), loop=0, optimize=True)
still.save(OUT[:-4] + ".png")
print(f"wrote {OUT} ({len(imgs)} frames, {os.path.getsize(OUT) // 1024} KB) and {OUT[:-4]}.png")