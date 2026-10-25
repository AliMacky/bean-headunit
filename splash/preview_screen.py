#!/usr/bin/env python3
"""Preview the whole screen exactly as the Pi's console will show it.

  pip3 install pyte pillow
  python3 preview_screen.py screen.gif [columns rows]

Runs the real splash.py against an emulated Linux console (default 240x67,
what a 1080p screen gives you), so the sky, layout, tagline and colors are
the same as on the Pi. Also saves a still of the idle scene as screen.png.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.update(TERM="linux", SPLASH_WAIT_MAX="0", SPLASH_PREROLL="0", SPLASH_ONCE="")
import pyte
from PIL import Image, ImageDraw, ImageFont
import splash

if len(sys.argv) < 2:
    sys.exit(__doc__)
COLS, ROWS = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (240, 67)
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
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", int(CH * 0.85))
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
imgs[0].save(sys.argv[1], save_all=True, append_images=imgs[1:], duration=33, loop=0, optimize=True)
imgs[int(len(imgs)*0.8)].save(sys.argv[1].replace(".gif", ".png"))
print(len(imgs), os.path.getsize(sys.argv[1]) // 1024, "KB")
