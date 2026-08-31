#!/usr/bin/env python3
"""Render the menu against every photograph in the library, on one sheet.

The point is to see what the colour matching does with pictures it was not
tuned on. Nothing is written down per photograph: each of these is the hue the
picture itself yields, and every colour in the theme is a saturation and a
lightness away from it.

    ./library-preview.py            # screenshots/library.png
"""
import colorsys, json, os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build

SHOTS = os.path.join(HERE, "screenshots")
CELL  = (640, 360)
HEAD  = 40
FONTS = "/usr/share/fonts/truetype/dejavu/DejaVuSans"


def main():
    cfg  = json.load(open(os.path.join(HERE, "library", "library.json")))
    work = os.path.join(HERE, "library", ".preview")
    os.makedirs(SHOTS, exist_ok=True)
    entries = []
    for i, b in enumerate(cfg["backgrounds"]):
        src = os.path.join(HERE, "library", os.path.basename(b["file"]))
        out = os.path.join(work, b["slug"])
        build.build(src, cfg.get("default_darken", "auto"), out, quiet=True,
                    blur=cfg.get("default_blur", 0), tint=cfg.get("default_tint", 100))
        shot = os.path.join(work, f"{b['slug']}.png")
        build.preview(out, shot, ["os_win8", "os_ubuntu"], "Boot Windows", scale=(1920, 1080))
        bg = Image.open(os.path.join(out, "background.png"))
        direction, chroma = build.accent(bg)
        hue = build.accent_hue(direction)
        logo = build.shades(bg, 1.0)["ramp"][153]     # where a logo's midtone lands
        entries.append((b["name"], shot, hue, chroma, logo))
        print(f"  {b['name']:31s} hue {hue:5.0f}°  chroma {chroma:3d}  logo {logo}")

    cols  = 2
    rows  = (len(entries) + cols - 1) // cols
    sheet = Image.new("RGB", (CELL[0] * cols, (CELL[1] + HEAD) * rows), (16, 16, 16))
    draw  = ImageDraw.Draw(sheet)
    bold  = ImageFont.truetype(FONTS + "-Bold.ttf", 19)
    plain = ImageFont.truetype(FONTS + ".ttf", 16)
    for i, (name, shot, hue, sat, logo) in enumerate(entries):
        x, y = (i % cols) * CELL[0], (i // cols) * (CELL[1] + HEAD)
        sheet.paste(Image.open(shot).convert("RGB").resize(CELL, Image.LANCZOS), (x, y + HEAD))
        draw.text((x + 8, y + 4), name, font=bold, fill=(255, 200, 120))
        draw.text((x + 8, y + 23),
                  f"hue {hue:.0f}°   chroma {sat}   logo {logo}",
                  font=plain, fill=(190, 190, 190))
    dst = os.path.join(SHOTS, "library.png")
    sheet.save(dst, optimize=True)
    print(f"\n  {dst}  ({os.path.getsize(dst)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
