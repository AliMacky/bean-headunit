#!/usr/bin/env python3
"""Sanity-check built frames for glitches before putting them on the Pi.

  python3 verify_frames.py frames/*.json

Checks that every frame has the same shape, that colors line up with text,
that the car moves smoothly (no backward jumps outside the stop shake),
that nothing flickers in for a single frame, and that the idle loop wraps
around (and is entered) without a visible jump.
"""

import json
import sys

VALID_COLORS = set(".gwGyYrR")


def car_extent(frame, table):
    """Rightmost column of the car (the only thing drawn in the default color)."""
    best = -1
    for idx in frame:
        text, colors = table[idx]
        for c in range(len(text) - 1, -1, -1):
            if colors[c] == "." and text[c] not in " \u2800":
                best = max(best, c)
                break
    return best


def changed_cells(a, b, table):
    n = 0
    for ia, ib in zip(a, b):
        if ia != ib:
            ta, tb = table[ia][0], table[ib][0]
            n += sum(1 for x, y in zip(ta, tb) if x != y)
    return n


def check(path):
    data = json.load(open(path, encoding="utf-8"))
    table, frames, fps = data["rows"], data["frames"], data["fps"]
    problems = []

    widths = {len(t) for t, _ in table}
    if len(widths) != 1:
        problems.append(f"rows have different widths: {sorted(widths)}")
    for t, c in table:
        if len(t) != len(c):
            problems.append("a row's colors don't match its text length")
            break
        if set(c) - VALID_COLORS:
            problems.append(f"unknown color codes {set(c) - VALID_COLORS}")
            break
    if len({len(f) for f in frames}) != 1:
        problems.append("frames have different heights")

    # Car motion: right edge should only move forward, except during the
    # short shake right after the stop.
    stop = int(3.9 * fps)
    edges = [car_extent(f, table) for f in frames]
    for i in range(1, len(edges)):
        if edges[i] < 0 or edges[i - 1] < 0:
            continue
        step = edges[i] - edges[i - 1]
        in_shake = stop - 1 <= i <= stop + int(0.25 * fps)
        if step < -1 and not in_shake:  # 1 col of wobble is the nose dipping
            problems.append(f"car jumps backward at frame {i} ({step} cols)")
        if step > 25:
            problems.append(f"car jumps {step} cols at frame {i}")

    # Flicker: a frame that differs a lot from both neighbors while the
    # neighbors match each other, i.e. something pops in for a single frame.
    loop_from = data["loop_from"]
    for i in range(1, len(frames) - 1):
        around = changed_cells(frames[i - 1], frames[i + 1], table)
        here = min(changed_cells(frames[i - 1], frames[i], table),
                   changed_cells(frames[i], frames[i + 1], table))
        if here > 60 and here > 4 * max(around, 10):
            problems.append(f"single-frame flicker at frame {i} ({here} cells)")

    loop = frames[loop_from:]
    loop_diffs = [changed_cells(loop[i - 1], loop[i], table) for i in range(1, len(loop))]
    seam = changed_cells(loop[-1], loop[0], table)
    typical = sorted(loop_diffs)[len(loop_diffs) // 2] if loop_diffs else 0
    if seam > 3 * max(typical, 20):
        problems.append(f"loop seam changes {seam} cells (typical {typical})")
    entry = changed_cells(frames[loop_from - 1], frames[loop_from], table)
    if entry > 3 * max(typical, 20):
        problems.append(f"intro -> loop changes {entry} cells (typical {typical})")

    status = "OK" if not problems else "PROBLEMS"
    print(f"{path}: {status}  ({len(frames)} frames, loop seam {seam}, typical loop change {typical})")
    for p in problems[:20]:
        print("   -", p)
    return not problems


if __name__ == "__main__":
    ok = all([check(p) for p in sys.argv[1:]])
    sys.exit(0 if ok else 1)
