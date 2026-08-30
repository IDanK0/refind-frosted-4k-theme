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

if __name__ == "__main__":
    main()
