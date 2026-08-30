#!/usr/bin/env python3
"""Regenerate the screenshots in README.md from the built assets.

They are rendered by the same code that lays out the real menu, so a screenshot
cannot drift from what the machine draws: the geometry comes from build.py's
constants, which are rEFInd's own arithmetic, and the frosted glass comes from
apply_frost(), which is the box blur the patched rEFInd runs at draw time.

    ./build.py && ./make-screenshots.py
"""
import os, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import preview, W, H, TILE, XSP, ICON_OFF, PLATE_X, PLATE_Y, PLATE, R0Y

ASSETS = os.path.join(HERE, "assets")
SHOTS  = os.path.join(HERE, "screenshots")

def shot(name, icons, label, scale=(1920, 1080)):
    dst = os.path.join(SHOTS, name)
    preview(ASSETS, dst, icons, label, scale=scale)
    print(f"  {name}  {len(icons)} entries")

def handoff(stem, t=0.55):
    """The screen rEFInd shows on the way to any system, drawn the way it draws it."""
    import math
    from plymouth import still, dot, angle, NDOTS, DOT, RING
    from build import TILE, TILE1, YSP
    c = still(ASSETS, os.path.join(ASSETS, "icons", f"{stem}.png")).convert("RGBA")
    d = dot()
    cx, cy = c.width // 2, R0Y + TILE + YSP + TILE1 + YSP + 75
    for i in range(NDOTS):
        a = angle(t, i)
        c.alpha_composite(d, (int(cx + RING * math.cos(a) - DOT / 2),
                              int(cy + RING * math.sin(a) - DOT / 2)))
    return c.convert("RGB")


def main():
    if not os.path.exists(os.path.join(ASSETS, "frost_big.png")):
        sys.exit("assets missing -- run ./build.py first")
    os.makedirs(SHOTS, exist_ok=True)

    # what this machine shows
    shot("menu.png", ["os_win8", "os_ubuntu"], "Boot Windows")

    # the same theme after a USB stick and a third system turn up: rEFInd
    # re-centres the row, and every plate travels with its entry
    shot("adaptive.png", ["os_win8", "os_ubuntu", "os_fedora", "os_debian"],
         "Boot Fedora")

    # the glass, at full resolution, against a photograph with detail in it
    full = os.path.join(SHOTS, ".full.png")
    preview(ASSETS, full, ["os_win8", "os_ubuntu"], "Boot Windows")
    r0x = (W + XSP - (TILE + XSP) * 2) // 2
    x = r0x + ICON_OFF + PLATE_X
    y = R0Y + ICON_OFF + PLATE_Y
    Image.open(full).crop((x - 150, y - 120, x + PLATE + 150, y + PLATE + 120)) \
         .save(os.path.join(SHOTS, "detail-glass.png"))
    os.remove(full)
    print("  detail-glass.png  crop at native resolution")

    # The same screen on the way to anything: rEFInd draws it before every
    # handover, from the entry's own icon, so a system nobody has installed yet
    # already has its boot logo.
    grid = Image.new("RGB", (1920, 1080 * 3))
    for i, stem in enumerate(["os_win8", "os_fedora", "os_unknown"]):
        frame = handoff(stem).resize((1920, 1080), Image.LANCZOS)
        grid.paste(frame, (0, i * 1080))
        if stem == "os_win8":
            frame.save(os.path.join(SHOTS, "handoff.png"), optimize=True)
    grid.resize((960, 1620), Image.LANCZOS).save(os.path.join(SHOTS, "handoff-any.png"),
                                                 optimize=True)
    print("  handoff.png, handoff-any.png  the same screen for three systems")

if __name__ == "__main__":
    main()
