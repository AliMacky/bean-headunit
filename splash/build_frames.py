#!/usr/bin/env python3
"""Build the Mr. Bean boot splash: a night rally stage in the forest.

Run this on your computer (or the Pi) whenever you change the art. It writes one
JSON file per style and size into frames/. The splash (splash.py) only reads
one of those files and prints text, so the Pi never needs Pillow at boot.

  pip3 install pillow numpy     (once)
  sudo apt install python3-pil python3-numpy     (Pi)
  python3 build_frames.py                     build everything into frames/
  python3 preview_gif.py frames/braille-110.json preview.gif   watch it

Two styles are built:
  half     for the Pi's own console (tty1). The car is ASCII art and the name
           is block characters (the console has no braille glyphs).
           --console-car blocks draws the car in half blocks instead.
  braille  2x4 dots per character, for normal terminals (SSH)

How a frame is made:
  * The car, its taillights and the name are drawn as pixels, then turned
    into ASCII (console) or braille (terminals) by matching character shapes.
    A few effects (speed lines, brake light rays, exhaust flames) stay pixels.
  * Everything else (stars, trees, the dirt road, dust, the headlight
    beams) is real ASCII text: letters, numbers and symbols.
  * Every character cell also gets a color code (see COLORS below), which
    the splash turns into ANSI colors.

Timeline (seconds):
  0.0 - 0.9  Night in the forest. His headlights fade up and reach in from
             the left before the car arrives.
  0.9 - 3.0  He comes through. The camera pans with him: gravel streams by,
             near trees slide past faster than far ones (parallax), dust
             trails behind, speed lines. The beams light up whatever they
             hit.
  3.0 - 3.9  Hard on the brakes: nose dives, taillights flare, the dust
             right behind the car picks up a red glow.
  3.9 - 4.8  Stops dead center. Shake, rebound, two exhaust pops.
  4.8 - 5.5  High beams, flashed twice.
  5.5 - 7.0  MR. BEAN streaks in and locks, then a glint runs across it.
  then       A seamless idle loop (twinkling stars, breathing beams) that
             the splash repeats until the head unit UI takes over.

Every time-based effect in the idle loop repeats exactly every LOOP_S
seconds, so the loop has no visible seam.
"""

import argparse
import json
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    import numpy as np
except ImportError:  # only needed for the console (half) style
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
SS = 3                    # supersampling for the pixel-drawn parts

FPS = 30
INTRO_S = 7.0
LOOP_S = 1.6              # idle loop length; loop effects repeat on this period
NAME = "MR. BEAN"

# Timeline marks.
T_IN, T_BRAKE, T_STOP = 0.9, 3.0, 3.9
T_POPS = (T_STOP + 0.35, T_STOP + 0.6)
T_FLASHES = (4.85, 5.15)
T_NAME = 5.5

# Color codes stored per character; splash.py maps them to ANSI.
C_DEFAULT, C_GRAY, C_WHITE, C_GREEN = ".", "g", "w", "G"
C_YELLOW, C_YELLOW_HI, C_RED, C_RED_HI = "y", "Y", "r", "R"

# ASCII material.
BEAM_LEVELS = [".,`'", ":;-~", "=+17i", "*x350", "#%8&@"]   # dim -> bright
GRAVEL = ".,:;'`"
STONES = "oO0"
RUTS = "=~-"
TUFTS = "wvWV\"',"
DUST_CHARS = ".,`':;"
NEAR_TREE_FILL = "#%&8$*+:"
FAR_TREE_FILL = ".:+*"

BRAILLE_BITS = [(0, 0, 1), (0, 1, 2), (0, 2, 4), (1, 0, 8),
                (1, 1, 16), (1, 2, 32), (0, 3, 64), (1, 3, 128)]
HALF_BITS = [(0, 0, 1), (0, 1, 2)]


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def ease_out(t, p=3):
    return 1 - (1 - clamp(t)) ** p


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def hashf(*v):
    """Deterministic pseudo-random number in [0, 1) from integers."""
    h = 2166136261
    for x in v:
        h = ((h ^ (x & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    h ^= h >> 15
    return h / 4294967296


def loop_wave(t, phase, cycles=1):
    """A 0..1 wave that repeats exactly every LOOP_S seconds."""
    return 0.5 + 0.5 * math.sin(phase + 2 * math.pi * cycles * t / LOOP_S)


# =============================================================================
# The car (traced from a side photo of an NB with the hardtop)
# =============================================================================
# Photo pixel coordinates: car faces right, ground at y=1048.

X0, X1 = 40, 1975          # car extents
Y0, GROUND = 400, 1048     # top of the drawing, ground line
DROP = 20                  # body sits this much lower than stock

REAR_W, FRONT_W = (435, 878), (1655, 882)  # wheel centers
TIRE_R, RIM_R, ARCH_R = 170, 122, 184


def bezier(p0, p1, p2, n=14):
    pts = []
    for i in range(1, n + 1):
        t = i / n
        pts.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                    (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]))
    return pts


HOOD = bezier((1300, 606), (1735, 596), (1938, 756))  # convex, like the real one

BODY = [
    (72, 840), (54, 795), (56, 742), (74, 690), (96, 640), (112, 608),   # rear
    (250, 588), (440, 586),                                               # trunk
    (480, 556), (560, 500), (640, 452), (705, 426), (800, 418), (1000, 420),
    (1036, 432), (1100, 470), (1200, 540), (1300, 606),                   # hardtop
    *HOOD,
    (1956, 784), (1963, 825), (1960, 880),                                # nose
    (1972, 945), (1968, 968), (1820, 972),                                # front lip
    (1460, 962), (620, 962),                                              # side skirt
    (250, 915), (110, 880),                                               # rear valance
]
SPOILER = [(84, 568), (100, 556), (200, 545), (335, 546), (335, 572), (160, 590), (112, 608)]
HARDTOP_WINDOW = [(478, 576), (572, 498), (640, 468), (642, 576)]
SIDE_WINDOW = [(724, 466), (1022, 452), (1286, 602), (1240, 612), (736, 628)]

# NB taillight seen from the side: a rounded wedge wrapping the rear corner.
TAILLIGHT = [(60, 712), (66, 680), (80, 656), (100, 642), (122, 640), (136, 652),
             (140, 684), (134, 716), (118, 738), (94, 746), (72, 740)]
TAILLIGHT_CENTER = (100, 694)
HEADLIGHT = [(1878, 710), (1926, 724), (1944, 770), (1904, 766)]
EXHAUST = (60, 888)


def car_layers(width_px, wheel_angle):
    """Draw the car `width_px` wide. Returns (body, silhouette mask, taillight)."""
    k = width_px / (X1 - X0)
    h = int((GROUND + 6 - Y0) * k)
    img = Image.new("L", (width_px, h), 0)
    mask = Image.new("L", (width_px, h), 0)
    tail = Image.new("L", (width_px, h), 0)
    d, m, tl = ImageDraw.Draw(img), ImageDraw.Draw(mask), ImageDraw.Draw(tail)

    def P(x, y, drop=True):
        return ((x - X0) * k, (y - Y0 + (DROP if drop else 0)) * k)

    def W(v):
        return max(1, int(v * k))

    def circle(c, r, **kw):
        cx, cy = c
        d.ellipse([P(cx - r, cy - r, False), P(cx + r, cy + r, False)], **kw)

    for target in (d, m):
        target.polygon([P(x, y) for x, y in BODY], fill=255)
        target.polygon([P(x, y) for x, y in SPOILER], fill=255)
    for cx, cy in (REAR_W, FRONT_W):
        m.ellipse([P(cx - TIRE_R, cy - TIRE_R, False), P(cx + TIRE_R, cy + TIRE_R, False)], fill=255)
        circle((cx, cy), ARCH_R, fill=0)

    # Antenna.
    for target in (d, m):
        target.line([P(368, 508), P(425, 566)], fill=255, width=W(7))

    # Glass, A-pillar, mirror.
    d.polygon([P(*p) for p in HARDTOP_WINDOW], fill=0)
    d.polygon([P(*p) for p in SIDE_WINDOW], fill=0)
    d.line([P(1036, 440), P(1290, 604)], fill=255, width=W(22))
    d.ellipse([P(1012, 578), P(1128, 646)], fill=255)
    d.line([P(1070, 640), P(1100, 668)], fill=255, width=W(16))

    # Panel lines and details.
    lw = W(9)
    d.line([P(706, 636), P(712, 760), P(745, 880), P(790, 920), P(1320, 922),
            P(1348, 870), P(1352, 650)], fill=0, width=lw, joint="curve")   # door
    d.rounded_rectangle([P(760, 688), P(866, 718)], radius=10 * k, fill=0)  # handle
    d.line([P(640, 945), P(1430, 945)], fill=0, width=lw)                     # sill
    d.line([P(112, 612), P(440, 592)], fill=0, width=W(7))                    # trunk
    d.rounded_rectangle([P(128, 796), P(204, 822)], radius=8 * k, fill=0)     # rear marker
    d.polygon([P(*p) for p in HEADLIGHT], fill=0)
    d.rounded_rectangle([P(1878, 820), P(1936, 846)], radius=8 * k, fill=0)   # front marker
    d.line([P(1830, 950), P(1968, 950)], fill=0, width=W(7))                  # lip split

    # Taillight: a dark gap around it in the body, the lens on its own layer
    # so it can be colored red.
    tpts = [P(*p) for p in TAILLIGHT]
    d.polygon(tpts, fill=0, outline=0)
    d.line(tpts + tpts[:1], fill=0, width=W(14))
    cx, cy = P(*TAILLIGHT_CENTER)
    inner = [(cx + (x - cx) * 0.8, cy + (y - cy) * 0.8) for x, y in tpts]
    tl.polygon(inner, fill=255)

    # Wheels: Kogeki-style, five Y spokes.
    for c in (REAR_W, FRONT_W):
        cx, cy = c

        def R(r, a, cx=cx, cy=cy):
            return P(cx + r * math.cos(a), cy + r * math.sin(a), False)

        circle(c, TIRE_R, fill=255)
        circle(c, RIM_R + 14, fill=0)
        circle(c, RIM_R, outline=255, width=W(12))
        for i in range(5):
            a = wheel_angle + i * 2 * math.pi / 5
            d.line([R(30, a), R(64, a)], fill=255, width=W(20))
            for side in (-1, 1):
                d.line([R(60, a), R(84, a + side * 0.20), R(RIM_R - 4, a + side * 0.33)],
                       fill=255, width=W(12), joint="curve")
        circle(c, 38, fill=255)
        for i in range(5):
            a = wheel_angle + math.pi / 5 + i * 2 * math.pi / 5
            lx, ly = cx + 27 * math.cos(a), cy + 27 * math.sin(a)
            d.ellipse([P(lx - 5, ly - 5, False), P(lx + 5, ly + 5, False)], fill=0)
        circle(c, 15, fill=0)

    return img, mask, tail


# =============================================================================
# The name, in a custom JDM-style font
# =============================================================================
# Squared-off, chamfered letters on a 10 x 12 grid, slanted hard right, with a
# speed stripe cut through at braille resolution. Only the letters we need.

S = 2.7  # stroke width


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


GLYPHS = {  # width, filled polygons, polygons cut back out
    "M": (12, [_rect(0, 0, S, 12), _rect(12 - S, 0, 12, 12),
               [(0, 0), (S + 0.4, 0), (6, 6.2), (12 - S - 0.4, 0), (12, 0), (6, 9.6)]],
          [[(0, 0), (1.6, 0), (0, 1.6)]]),
    "R": (10, [_rect(0, 0, S, 12), _rect(0, 0, 8.6, S), _rect(0, 5, 8.6, 5 + S),
               _rect(10 - S, 0, 10, 7.6), [(3.6, 5), (7.4, 5), (10.4, 12), (6.4, 12)]],
          [[(0, 0), (1.6, 0), (0, 1.6)], [(10, 0), (8.2, 0), (10, 1.8)],
           [(10, 7.7), (8.4, 7.7), (10, 6.1)]]),
    "B": (10, [_rect(0, 0, S, 12), _rect(0, 0, 8.6, S), _rect(0, 4.8, 9, 4.8 + S),
               _rect(0, 12 - S, 9.4, 12), _rect(10 - S, 0, 10, 12)],
          [[(0, 0), (1.6, 0), (0, 1.6)], [(10, 0), (8.2, 0), (10, 1.8)],
           [(10, 12), (8.2, 12), (10, 10.2)], [(10, 4.4), (10, 7.9), (8.9, 6.15)]]),
    "E": (9, [_rect(0, 0, S, 12), _rect(0, 0, 9, S), _rect(0, 4.7, 7.6, 4.7 + S),
              _rect(0, 12 - S, 9, 12)],
          [[(0, 0), (1.6, 0), (0, 1.6)]]),
    "A": (10, [_rect(0, 0, S, 12), _rect(10 - S, 0, 10, 12), _rect(0, 0, 10, S),
               _rect(0, 5.6, 10, 5.6 + S)],
          [[(0, 0), (3.2, 0), (0, 3.2)], [(10, 0), (6.8, 0), (10, 3.2)]]),
    "N": (10, [_rect(0, 0, S, 12), _rect(10 - S, 0, 10, 12),
               [(0, 0), (S + 0.9, 0), (10, 12), (10 - S - 0.9, 12)]],
          [[(0, 0), (1.6, 0), (0, 1.6)]]),
    ".": (S, [_rect(0, 12 - S, S, 12)], []),
    " ": (3.2, [], []),
}
LETTER_GAP = 1.5
SLANT = 0.32
STRIPE = (0.64, 0.06)


def name_image(height_px, stripe=True):
    u = height_px / 12
    total = sum(GLYPHS[c][0] for c in NAME) + LETTER_GAP * (len(NAME) - 1)
    w = int(total * u + SLANT * height_px) + 4
    img = Image.new("L", (w, height_px + 2), 0)
    d = ImageDraw.Draw(img)
    x = 0.0
    for ch in NAME:
        gw, polys, cuts = GLYPHS[ch]

        def P(p, x=x):
            return ((x + p[0]) * u + SLANT * (12 - p[1]) * u, p[1] * u)
        for poly in polys:
            d.polygon([P(p) for p in poly], fill=255)
        for cut in cuts:
            d.polygon([P(p) for p in cut], fill=0)
        x += gw + LETTER_GAP
    if stripe and height_px >= 60:  # the stripe only reads at braille resolution
        sy = int(STRIPE[0] * height_px)
        d.rectangle([0, sy, w, sy + max(1, int(STRIPE[1] * height_px))], fill=0)
    return img


# =============================================================================
# Scenery
# =============================================================================

def tree_stamp(rng, height, near):
    """An ASCII pine: {(dx, dy): char}, dy = 0 is the base, negative is up.

    Every tree gets its own shape: how fast it widens, how its branches step
    out in tiers, how dense its needles are, and which characters it uses.
    """
    cells = {}
    trunk = (2 if near else 1) + (1 if rng.random() < 0.3 else 0)
    canopy = max(2, height - trunk)
    slope = rng.uniform(0.28, 0.55)              # skinny spruce ... wide fir
    tier = rng.choice((2, 3, 3, 4))              # rows per branch tier
    step = rng.uniform(0.3, 0.8)                 # how far each tier juts out
    gaps = rng.uniform(0.15, 0.4) if near else rng.uniform(0.35, 0.55)
    fill = "".join(rng.sample(NEAR_TREE_FILL if near else FAR_TREE_FILL, 3 if near else 2))
    top = rng.choice("^^^A*")
    lean = rng.choice((0, 0, 0, -1, 1))          # a few trees lean a little
    for j in range(canopy):
        y = -(height - j)
        hw = int(0.35 + j * slope + (j % tier) * step)
        shift = int(round(lean * j / max(1, canopy) * 1.5))
        if j == 0:
            cells[(shift, y)] = top
            continue
        for dx in range(-hw, hw + 1):
            x = dx + shift
            if dx == -hw:
                cells[(x, y)] = "/"
            elif dx == hw:
                cells[(x, y)] = "\\"
            elif rng.random() >= gaps:
                cells[(x, y)] = rng.choice(fill)
    for y in range(-trunk, 0):
        cells[(0, y)] = "|"
        if near and canopy > 6:
            cells[(1, y)] = "|"
    return cells


# =============================================================================
# Turning pixel layers + ASCII into text rows
# =============================================================================

def compose(layers, w, h, ppc, overlay, blank):
    """Build (text, colors) rows.

    `layers` is a list of (image, color) in priority order. In each cell the
    highest-priority layer with any lit pixel wins the whole cell, so layers
    never mix inside one glyph. Cells with no lit pixels can hold an ASCII
    character from `overlay`.
    """
    prio = Image.new("L", (w, h), 255)
    for idx in range(len(layers) - 1, -1, -1):
        prio.paste(idx, mask=layers[idx][0].point(lambda v: 255 if v > 127 else 0))
    data = prio.tobytes()
    offs = HALF_BITS if ppc == (1, 2) else BRAILLE_BITS
    rows = []
    for r in range(h // ppc[1]):
        text, colors = [], []
        y0 = r * ppc[1]
        for c in range(w // ppc[0]):
            x0 = c * ppc[0]
            vals = [(data[(y0 + dy) * w + x0 + dx], bit) for dx, dy, bit in offs]
            winner = min(v for v, _ in vals)
            if winner != 255:
                bits = sum(bit for v, bit in vals if v == winner)
                text.append({1: "▀", 2: "▄", 3: "█"}[bits] if ppc == (1, 2)
                            else chr(0x2800 + bits))
                colors.append(layers[winner][1])
            elif (c, r) in overlay:
                ch, col = overlay[(c, r)]
                text.append(ch)
                colors.append(col)
            else:
                text.append(blank)
                colors.append(C_DEFAULT)
        rows.append(("".join(text), "".join(colors)))
    return rows



# =============================================================================
# ASCII glyph matching, for the console version of the car and the name
# =============================================================================
# The Pi's console only has whole characters, so half blocks made the car's
# fine parts (wheels, mirror, door line) chunky. On the console the car is
# drawn as ASCII art instead: it is rendered at 8x16 pixels per character,
# its outlines and panel lines are matched against the shapes of real
# characters (/ \\ _ | ( ) ^ ...), and the paintwork is filled with #.
# The name is matched the same way, with block characters allowed.

GLYPH_W, GLYPH_H = 8, 16
# Characters the car outline is drawn with, and the ones used for the name
# (which also gets block characters, since it is solid).
CAR_CHARS = " .,'`-_=|/\\()^"
NAME_CHARS = " .,'`-_~=:;|/\\()<>^v[]"
MATCH_BLOCKS = "\u2588\u2580\u2584\u258c\u2590"
MONO_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "/System/Library/Fonts/Menlo.ttc", "/Library/Fonts/Menlo.ttc",
              "/System/Library/Fonts/Monaco.ttf"]


def _glyph_image(ch):
    """A character as it roughly looks in an 8x16 terminal cell."""
    if ch in MATCH_BLOCKS:
        img = Image.new("L", (GLYPH_W, GLYPH_H), 0)
        d = ImageDraw.Draw(img)
        box = {"\u2588": (0, 0, 8, 16), "\u2580": (0, 0, 8, 8), "\u2584": (0, 8, 8, 16),
               "\u258c": (0, 0, 4, 16), "\u2590": (4, 0, 8, 16)}[ch]
        d.rectangle([box[0], box[1], box[2] - 1, box[3] - 1], fill=255)
        return img
    font = None
    for path in MONO_FONTS:
        try:
            font = ImageFont.truetype(path, 40)
            break
        except OSError:
            continue
    if font is None:
        raise SystemExit("no monospace font found for glyph matching")
    ascent, descent = font.getmetrics()
    w = int(round(font.getlength("M")))
    big = Image.new("L", (w, ascent + descent), 0)
    ImageDraw.Draw(big).text((0, 0), ch, fill=255, font=font)
    return big.resize((GLYPH_W, GLYPH_H), Image.LANCZOS)


class GlyphMatcher:
    def __init__(self, chars):
        if np is None:
            raise SystemExit("the console style needs numpy: pip3 install numpy")
        self.labels, mats = [], []
        for ch in chars:
            a = np.asarray(_glyph_image(ch).filter(ImageFilter.GaussianBlur(0.8)), dtype=np.float32) / 255
            self.labels.append(ch)
            mats.append(a.ravel())
        self.T = np.stack(mats)
        self.T2 = (self.T ** 2).sum(axis=1)

    def match(self, image, cells):
        """Best character for each (col, row) cell of an 8x16-per-cell image."""
        a = np.asarray(image.filter(ImageFilter.GaussianBlur(0.8)), dtype=np.float32) / 255
        patches = np.stack([a[r * GLYPH_H:(r + 1) * GLYPH_H, c * GLYPH_W:(c + 1) * GLYPH_W].ravel()
                            for c, r in cells])
        scores = self.T2[None, :] - 2 * patches @ self.T.T
        return [self.labels[k] for k in scores.argmin(axis=1)]


def cell_cover(image, ncols, nrows):
    a = np.asarray(image, dtype=np.float32) / 255
    return a.reshape(nrows, GLYPH_H, ncols, GLYPH_W).mean(axis=(1, 3))


def ascii_car(matcher, body, mask, tail, c0, r0, ncols, nrows, tail_color):
    """The car as ASCII art: outlines matched to characters, # for the
    paintwork, and the taillight in red.

    body / mask / tail are 8x16-per-cell images already placed on a canvas
    of ncols x nrows cells starting at screen cell (c0, r0).
    """
    lit = Image.composite(tail, body, tail)
    edges = lit.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 60 else 0)
    outline = mask.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 60 else 0)
    lines = Image.composite(outline, edges, outline).filter(ImageFilter.MaxFilter(3))

    line_cov = cell_cover(lines, ncols, nrows)
    lit_cov = cell_cover(lit, ncols, nrows)
    mask_cov = cell_cover(mask, ncols, nrows)
    tail_cov = cell_cover(tail, ncols, nrows)

    line_cells = [(c, r) for r in range(nrows) for c in range(ncols) if line_cov[r, c] > 0.03]
    chars = dict(zip(line_cells, matcher.match(lines, line_cells))) if line_cells else {}

    out = {}
    for r in range(nrows):
        for c in range(ncols):
            ch = chars.get((c, r), " ")
            is_tail = tail_cov[r, c] > 0.25
            if is_tail:
                out[(c0 + c, r0 + r)] = (ch if ch != " " else "#", tail_color)
            elif ch != " ":
                out[(c0 + c, r0 + r)] = (ch, C_WHITE)           # outlines, bright
            elif lit_cov[r, c] > 0.6:
                out[(c0 + c, r0 + r)] = ("#", C_DEFAULT)        # paintwork
            elif mask_cov[r, c] > 0.2:
                out[(c0 + c, r0 + r)] = (" ", C_DEFAULT)       # glass, gaps
    return out


def ascii_solid(matcher, image, c0, r0, ncols, nrows, color, min_cover=0.15):
    """A solid shape (the name) matched to block and ASCII characters."""
    cov = cell_cover(image, ncols, nrows)
    cells = [(c, r) for r in range(nrows) for c in range(ncols) if cov[r, c] >= min_cover]
    if not cells:
        return {}
    return {(c0 + c, r0 + r): (ch, color) for (c, r), ch in zip(cells, matcher.match(image, cells))}


# =============================================================================
# The animation
# =============================================================================

def car_state(t):
    """Car position (0 = start, 1 = parked), speed (0..1), braking, pitch."""
    if t < T_IN:
        return 0.0, 1.0, 0.0, 0.0
    if t < T_STOP:
        u = (t - T_IN) / (T_STOP - T_IN)
        braking = smooth((t - T_BRAKE) / 0.25) * (1 - smooth((t - T_STOP + 0.1) / 0.1))
        return ease_out(u, 3), (1 - u) ** 2, braking, -2.4 * braking
    u = t - T_STOP
    pitch = 1.8 * math.exp(-5 * u) * math.sin(u * 13) if u < 1.0 else 0.0
    return 1.0, 0.0, 0.0, pitch


# Camera pan in whole columns per frame: road / near trees / far trees.
CRUISE_COLS = 3
NEAR_STEP = {3: 2, 2: 1, 1: 1, 0: 0}
FAR_STEP = {3: 1, 2: 1, 1: 0, 0: 0}


def camera_cols(t):
    if t < T_BRAKE:
        return CRUISE_COLS
    steps = int((t - T_BRAKE) / 0.1)          # 3 -> 2 -> 1 -> 0, 0.1 s each
    return max(0, CRUISE_COLS - 1 - steps)


def render(style, car_chars, console_car="ascii"):
    ppc = (1, 2) if style == "half" else (2, 4)
    blank = " " if style == "half" else "⠀"
    rng = random.Random(11)

    cw = car_chars * ppc[0]                 # car width in final pixels
    car_h = car_layers(cw * SS, 0)[0].height // SS
    k = cw / (X1 - X0)                       # photo px -> final px

    # Layout (final pixels).
    car_top = int(cw * 0.2)
    ground = car_top + car_h
    road_far = ground - int(cw * 0.075)     # far edge of the road, behind the car
    road_near = ground + int(cw * 0.035)    # near edge, in front
    name_h = max(ppc[1] * 5, int(cw * 0.11))
    name_top = road_near + int(cw * 0.045)
    H = name_top + name_h + int(cw * 0.04)
    H += (-H) % ppc[1]
    final_left = int(cw * 1.25)
    start_left = -int(cw * 1.15)
    W = final_left + cw + int(cw * 0.95)
    W -= W % ppc[0]
    cols, rows = W // ppc[0], H // ppc[1]
    far_row, near_row = road_far // ppc[1], road_near // ppc[1]
    car_rows = car_h / ppc[1]

    # Console: car and name as real characters (or half blocks with --console-car blocks).
    ascii_mode = style == "half" and console_car == "ascii"
    if ascii_mode:
        car_matcher = GlyphMatcher(CAR_CHARS)
        name_matcher = GlyphMatcher(" " + MATCH_BLOCKS)   # blocks only: clean edges
        name_hr = name_image(name_h * GLYPH_W, stripe=False)

    name_big = name_image(name_h * SS)
    name_img = name_big.resize((max(1, name_big.width // SS), name_h + 1), Image.LANCZOS)
    name_left = final_left + (cw - name_img.width) // 2

    def P(x, y, left):
        return (left + (x - X0) * k, car_top + (y - Y0 + DROP) * k)

    # Forest: far row (small, gray, slow) and near row (taller, green, faster).
    forests = []
    for near, gap, hmin, hmax in ((False, (3, 9), 0.3, 0.95), (True, (6, 20), 0.45, 1.25)):
        trees, x = [], -cols
        while x < cols * 4:
            h = rng.uniform(hmin, hmax)
            if rng.random() < 0.12:
                h *= rng.uniform(1.25, 1.6)          # the odd giant
            trees.append((x, tree_stamp(rng, max(3, int(car_rows * h)), near)))
            # trees come in clumps with clearings between them
            x += rng.randint(*gap) if rng.random() > 0.15 else rng.randint(gap[1], gap[1] * 3)
        forests.append((near, trees))

    stars = [(rng.randrange(cols), rng.randrange(max(1, far_row - 2)), rng.random() * 6.28,
              rng.random() < 0.25, rng.choice((1, 2)))
             for _ in range(int(cols * far_row * 0.02))]

    # Per-cell beam flicker: a phase and a speed that loops cleanly.
    beam_phase = [[rng.random() * 6.28 for _ in range(cols)] for _ in range(rows)]
    beam_cycles = [[rng.choice((1, 2)) for _ in range(cols)] for _ in range(rows)]
    beam_pick = [[rng.randrange(1000) for _ in range(cols)] for _ in range(rows)]

    n_intro = int(round(INTRO_S * FPS))
    n_loop = int(round(LOOP_S * FPS))
    road_shift = near_shift = far_shift = 0
    angle = 0.0
    prev_left = float(start_left)
    dust, speed_lines = [], []
    unit = cw / 400

    frames = []
    for i in range(n_intro + n_loop):
        t = i / FPS
        looping = i >= n_intro
        pos, speed, braking, pitch = car_state(min(t, INTRO_S))
        left = start_left + (final_left - start_left) * pos

        # The camera pans a whole number of columns per frame, so the scenery
        # glides instead of stuttering, then steps down quickly when he brakes.
        cam_cols = camera_cols(t) if not looping else 0
        road_shift += cam_cols
        near_shift += NEAR_STEP.get(cam_cols, 0)
        far_shift += FAR_STEP.get(cam_cols, 0)
        cam = cam_cols * ppc[0]                       # pixels this frame
        # Wheels roll with the ground; capped per frame so the spokes never
        # strobe backwards at high speed.
        spin = ((left - prev_left) + cam) / (TIRE_R * k)
        angle += min(spin, 0.5)
        prev_left = left
        shake = 0
        if 0 <= t - T_STOP < 0.25:  # a quick damped wobble as he stops
            u = t - T_STOP
            shake = int(round(math.sin(2 * math.pi * u / 0.12) * (1 - u / 0.25) * 2 * ppc[0]))
        L = int(round(left)) + shake

        def img():
            return Image.new("L", (W, H), 0)

        name_l, flames_l, rays_l, tail_l, car_l, lines_l = img(), img(), img(), img(), img(), img()

        # ---- car ------------------------------------------------------------
        body, mask, tail = car_layers(cw * SS, angle)
        if pitch:
            pivot = (cw * SS * 0.5, body.height)
            body, mask, tail = (x.rotate(pitch, resample=Image.BICUBIC, center=pivot)
                                for x in (body, mask, tail))

        def shrink(x):
            return x.resize((cw, car_h + 1), Image.LANCZOS).point(lambda v: 255 if v > 110 else 0)
        car_l.paste(shrink(body), (L, car_top))
        tail_l.paste(shrink(tail), (L, car_top))
        hole = img()
        hole.paste(shrink(mask), (L, car_top))
        tail_color = C_RED_HI if braking > 0.2 else C_RED

        # ---- brake light rays -------------------------------------------------
        if braking > 0.2:
            d = ImageDraw.Draw(rays_l)
            cx, cy = P(*TAILLIGHT_CENTER, L)
            cx -= cw * 0.02
            for a in (150, 170, 190, 210):
                ra = math.radians(a)
                r0, r1 = cw * 0.03, cw * (0.055 + 0.025 * braking)
                d.line([(cx + r0 * math.cos(ra), cy + r0 * math.sin(ra)),
                        (cx + r1 * math.cos(ra), cy + r1 * math.sin(ra))], fill=255)

        # ---- speed lines ------------------------------------------------------
        if speed > 0.1 and not looping:
            for _ in range(int(5 * speed) + 1):
                speed_lines.append({"x": L - rng.uniform(0, 0.06) * cw,
                                    "y": car_top + rng.uniform(0.05, 0.75) * car_h,
                                    "len": rng.uniform(0.15, 0.45) * cw * speed, "life": 1.0})
        d = ImageDraw.Draw(lines_l)
        for s in speed_lines:
            s["x"] -= cam * 1.4 + unit
            s["life"] -= 0.1
            if s["life"] > 0:
                d.line([(s["x"] - s["len"], s["y"]), (s["x"], s["y"])], fill=255)
        speed_lines = [s for s in speed_lines if s["life"] > 0]

        # ---- exhaust pops -----------------------------------------------------
        for pop in T_POPS:
            if 0 <= t - pop < 0.1:
                big = 1.0 if t - pop < 0.05 else 0.6
                ex, ey = P(*EXHAUST, L)
                fl = cw * 0.075 * big
                ImageDraw.Draw(flames_l).polygon(
                    [(ex, ey - fl * 0.25), (ex - fl, ey - fl * 0.05), (ex - fl * 0.55, ey),
                     (ex - fl * 0.9, ey + fl * 0.15), (ex, ey + fl * 0.22)], fill=255)

        # ---- name ---------------------------------------------------------------
        name_color = C_WHITE
        glint = None
        tn = t - T_NAME
        if tn > 0:
            u = clamp(tn / 0.45)
            if u < 1:
                nx = name_left - (1 - ease_out(u, 4)) * (name_left + name_img.width + cw * 0.3)
                d = ImageDraw.Draw(lines_l)
                for f in (0.15, 0.4, 0.65, 0.9):
                    y = name_top + f * name_h
                    d.line([(nx - cw * 0.5 * (1 - u), y), (nx + name_img.width * 0.1, y)], fill=255)
            else:
                nx = name_left + math.exp(-(tn - 0.45) * 9) * math.sin((tn - 0.45) * 22) * cw * 0.01
            name_l.paste(name_img, (int(round(nx)), name_top))
            g = (tn - 0.8) / 0.5
            if 0 < g < 1:
                glint = name_left + g * (name_img.width + name_h) - name_h * 0.5

        sprite = {}
        if ascii_mode:
            # Car at 8x16 per cell, matched to characters.
            hb, hm, ht = car_layers(cw * GLYPH_W, angle)
            if pitch:
                pivot = (cw * GLYPH_W * 0.5, hb.height)
                hb, hm, ht = (x.rotate(pitch, resample=Image.BICUBIC, center=pivot) for x in (hb, hm, ht))
            c0, r0 = L, car_top // 2
            ncols = cw + 2
            nrows = (car_top + hb.height // GLYPH_W + 2) // 2 - r0 + 1
            canv = [Image.new("L", (ncols * GLYPH_W, nrows * GLYPH_H), 0) for _ in range(3)]
            oy = car_top * GLYPH_W - r0 * GLYPH_H
            for cv, src in zip(canv, (hb, hm, ht)):
                cv.paste(src, (0, oy))
            sprite.update(ascii_car(car_matcher, canv[0], canv[1], canv[2], c0, r0, ncols, nrows, tail_color))
            if tn > 0:
                nl = int(round(nx))
                nc0, nr0 = nl, name_top // 2
                nncols = name_img.width + 2
                nnrows = (name_h + 4) // 2 + 1
                ncanv = Image.new("L", (nncols * GLYPH_W, nnrows * GLYPH_H), 0)
                ncanv.paste(name_hr, (0, name_top * GLYPH_W - nr0 * GLYPH_H))
                sprite.update(ascii_solid(name_matcher, ncanv, nc0, nr0, nncols, nnrows, C_WHITE))

        # Nothing behind the car shows through it (windows included).
        for layer in (lines_l,):
            layer.paste(0, mask=hole)
        car_cells = set()
        hp = hole.load()
        for r in range(rows):
            for c in range(cols):
                x0, y0 = c * ppc[0], r * ppc[1]
                for dx in range(ppc[0]):
                    if any(hp[x0 + dx, y0 + dy] for dy in range(ppc[1])):
                        car_cells.add((c, r))
                        break

        # ==== ASCII scenery, back to front ======================================
        overlay = {}

        # stars
        fade = smooth(t / 0.6)
        for c, r, ph, bright, cyc in stars:
            v = loop_wave(t, ph, cyc) * fade
            if v < 0.25:
                continue
            ch = "*" if (bright and v > 0.75) else ("+" if v > 0.7 else ".")
            overlay[(c, r)] = (ch, C_WHITE if bright and v > 0.6 else C_GRAY)

        # forest
        tree_cells = set()
        for near, trees in forests:
            shift = near_shift if near else far_shift
            for wx, stamp in trees:
                sx = wx - shift
                if sx < -25 or sx > cols + 25:
                    continue
                for (dx, dy), ch in stamp.items():
                    c, r = sx + dx, far_row + dy
                    if 0 <= c < cols and 0 <= r < rows:
                        overlay[(c, r)] = (ch, C_GREEN if near else C_GRAY)
                        tree_cells.add((c, r))

        # headlight beams
        hx, hy = P(1950, 742, L)
        power = 0.62 * smooth(t / 0.7)
        reach = cw * 0.25 + W * 1.5 * smooth(t / 1.4)
        flash = max([math.sin(math.pi * (t - on) / 0.2) for on in T_FLASHES if 0 <= t - on < 0.2] or [0.0])
        up, down = 0.19 + 0.06 * flash, 0.36 + 0.08 * flash
        beam = {}
        for r in range(rows):
            cy = (r + 0.5) * ppc[1]
            if cy > road_near:
                continue
            for c in range(cols):
                dx = (c + 0.5) * ppc[0] - hx
                if dx <= ppc[0] or dx > reach:
                    continue
                a = math.atan2(cy - hy, dx)
                edge = (-a / up) if a < 0 else (a / down)
                if edge >= 1:
                    continue
                inten = (power + 0.5 * flash) * (1 - edge * edge) * (0.5 + 0.5 * math.exp(-dx / (cw * 1.2)))
                inten *= clamp(1.4 * (1 - dx / reach))
                inten *= 0.7 + 0.55 * loop_wave(t, beam_phase[r][c], beam_cycles[r][c])
                lvl = -1
                for li, th in enumerate((0.16, 0.3, 0.46, 0.62, 0.8)):
                    if inten > th:
                        lvl = li
                if lvl >= 0:
                    beam[(c, r)] = lvl
        for (c, r), lvl in beam.items():
            col = C_YELLOW_HI if (flash > 0.5 or lvl >= 3) else C_YELLOW
            if (c, r) in tree_cells:     # light falls on the trees
                overlay[(c, r)] = (overlay[(c, r)][0], col)
            else:
                chars = BEAM_LEVELS[lvl]
                overlay[(c, r)] = (chars[beam_pick[r][c] % len(chars)], col)

        # dirt road (world-locked, scrolls with the camera)
        wshift = road_shift
        span = near_row - far_row
        for r in range(far_row, near_row + 1):
            for c in range(cols):
                wc = c + wshift
                h = hashf(wc, r)
                if r in (far_row, near_row):
                    if h < 0.55:
                        ch, col = TUFTS[int(hashf(wc, r, 7) * len(TUFTS))], C_GREEN
                    elif h < 0.8:
                        ch, col = GRAVEL[int(hashf(wc, r, 3) * len(GRAVEL))], C_GRAY
                    else:
                        continue
                else:
                    rut = (r - far_row) in (span // 3, 2 * span // 3)
                    if rut and h < 0.55:
                        ch = RUTS[int(hashf(wc, r, 5) * len(RUTS))]
                    elif h < 0.04:
                        ch = STONES[int(hashf(wc, r, 9) * len(STONES))]
                    elif h < 0.42:
                        ch = GRAVEL[int(hashf(wc, r, 3) * len(GRAVEL))]
                    else:
                        continue
                    col = C_GRAY
                if (c, r) in beam:
                    col = C_YELLOW_HI if (flash > 0.5 or beam[(c, r)] >= 3) else C_YELLOW
                overlay[(c, r)] = (ch, col)

        # dust from the rear tires: a soft, sparse cloud of small marks
        if T_IN <= t < T_STOP - 0.05:
            rx_, _ = P(REAR_W[0], 0, L)
            heavy = t >= T_BRAKE - 0.1
            for _ in range(3 if heavy else 1):
                dust.append({"x": rx_ + rng.uniform(-6, 6) * unit,
                             "y": ground - rng.uniform(2, 10) * unit,
                             "vx": rng.uniform(-1.4, 0.2) * unit, "vy": rng.uniform(-0.8, -0.2) * unit,
                             "r": rng.uniform(9, 14) * unit * (1.3 if heavy else 1.0),
                             "life": 1.0, "seed": rng.randrange(1 << 20)})
        for p in dust:
            p["x"] += p["vx"] - cam
            p["y"] += p["vy"]
            p["vx"] *= 0.94
            p["vy"] *= 0.95
            p["r"] += 0.5 * unit
            p["life"] -= 0.022
        dust = [p for p in dust if p["life"] > 0]
        if dust:
            dimg = Image.new("L", (cols, rows), 0)
            dd = ImageDraw.Draw(dimg)
            for p in sorted(dust, key=lambda q: q["life"]):
                rx, ry = p["r"] / ppc[0], p["r"] / ppc[1]
                cx, cy = p["x"] / ppc[0], p["y"] / ppc[1]
                dd.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=int(220 * clamp(p["life"] * 1.3)))
            dimg = dimg.filter(ImageFilter.GaussianBlur(1.0))
            dp = dimg.load()
            tx, ty = P(*TAILLIGHT_CENTER, L)
            # Each mark is pinned to the world, so the cloud drifts instead
            # of sparkling in place.
            for r in range(rows):
                for c in range(cols):
                    v = dp[c, r]
                    if v < 40:
                        continue
                    if hashf(c + wshift, r, 77) > v / 255 * 0.75:
                        continue
                    ch = DUST_CHARS[int(hashf(c + wshift, r, 78) * len(DUST_CHARS))]
                    glow = braking > 0.2 and math.hypot(c * ppc[0] - tx, (r * ppc[1] - ty) * 1.3) < cw * 0.14
                    overlay[(c, r)] = (ch, C_RED if glow else C_GRAY)

        for cell in car_cells:
            overlay.pop(cell, None)

        # Pixel layers in priority order.
        if ascii_mode:
            for (c, r), v in sprite.items():
                if 0 <= c < cols and 0 <= r < rows:
                    overlay[(c, r)] = v
            layers = [(flames_l, C_YELLOW_HI), (rays_l, C_RED_HI), (lines_l, C_GRAY)]
        else:
            layers = [(name_l, C_WHITE), (flames_l, C_YELLOW_HI), (rays_l, C_RED_HI),
                      (tail_l, tail_color), (car_l, C_DEFAULT), (lines_l, C_GRAY)]
        rows_out = compose(layers, W, H, ppc, overlay, blank)

        if glint is not None:  # recolor the name cells under the moving glint
            out = []
            for r, (text, colors) in enumerate(rows_out):
                y = r * ppc[1] - name_top
                if 0 <= y <= name_h:
                    colors = "".join(
                        C_YELLOW_HI if (col == C_WHITE and abs((c * ppc[0] - glint) - (name_h - y) * SLANT)
                                        < name_h * 0.35) else col
                        for c, col in enumerate(colors))
                out.append((text, colors))
            rows_out = out
        frames.append(rows_out)

    return {"style": style, "fps": FPS, "car_width": car_chars,
            "final_car_left": final_left // ppc[0], "loop_from": n_intro, "loop_s": LOOP_S, "frames": frames}


def pack(data):
    """Store each unique (text, colors) row once; frames become row indices."""
    table, index, frames = [], {}, []
    for f in data["frames"]:
        ids = []
        for row in f:
            if row not in index:
                index[row] = len(table)
                table.append(list(row))
            ids.append(index[row])
        frames.append(ids)
    return dict(data, version=3, rows=table, frames=frames)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sizes", default="70,110",
                    help="car widths in characters; the splash picks the largest that fits")
    ap.add_argument("--out", default=os.path.join(HERE, "frames"))
    ap.add_argument("--console-car", choices=("ascii", "blocks"), default="ascii",
                    help="how the car looks on the Pi's own screen")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    for style in ("half", "braille"):
        for size in [int(s) for s in args.sizes.split(",")]:
            data = pack(render(style, size, args.console_car))
            path = os.path.join(args.out, f"{style}-{size}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            print(f"wrote {path}: {len(data['frames'])} frames, "
                  f"{os.path.getsize(path) // 1024} KB")


if __name__ == "__main__":
    main()
