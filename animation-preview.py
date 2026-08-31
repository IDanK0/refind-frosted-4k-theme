#!/usr/bin/env python3
"""Render what the animations look like, without rebooting.

The easing here is the same integer arithmetic menu.c uses -- no floating point,
0..256, cubic ease-out -- so a change to the timing can be looked at before it is
compiled into a bootloader. Frame counts and the frame interval are the
ANIM_* constants from the patch.

    ./build.py && ./animation-preview.py
"""
import os, sys, math
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import (W, H, TILE, TILE1, XSP, YSP, ICON_OFF, R0Y, BIG, FROST,
                   apply_frost, preview)
from plymouth import layout, dot, angle, NDOTS, DOT, RING, PERIOD

IN_FRAMES, SEL_FRAMES, OUT_FRAMES, MOVE_FRAMES = 9, 5, 7, 14
# menu.c's durations, in milliseconds. The frame counts above are the resolution
# of the easing curve, not the length of the animation: the bootloader runs each
# one by the clock and draws as many frames as the machine manages.
IN_STEP_MS, OUT_MS, MOVE_MS = 40, 280, 450
FRAME_MS   = 10
FONT_H     = 52
SHOTS      = os.path.join(HERE, "screenshots")
ASSETS     = os.path.join(HERE, "assets")
SCALE      = (960, 540)


def ease_out(t, n):
    """EaseOut() from menu.c, to the integer."""
    if n == 0 or t >= n:
        return 256
    left = 256 - (256 * t) // n
    return 256 - (left ** 3) // (256 * 256)


def blend(a, b, alpha):
    return Image.blend(a.convert("RGB"), b.convert("RGB"), alpha / 256.0)


def menu_frame(icons, chosen=0):
    tmp = os.path.join(SHOTS, ".menu.png")
    preview(ASSETS, tmp, icons, None)
    im = Image.open(tmp).convert("RGB")
    os.remove(tmp)
    return im


def save_gif(name, frames, ms):
    frames = [f.resize(SCALE, Image.LANCZOS).quantize(colors=64, method=Image.MEDIANCUT)
              for f in frames]
    path = os.path.join(SHOTS, name)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=ms, loop=0, optimize=True)
    print(f"  {name}  {len(frames)} frames  {os.path.getsize(path)/1024:.0f} KB")


def main():
    icons = ["os_win8", "os_ubuntu"]
    n     = len(icons)
    bg    = Image.open(os.path.join(ASSETS, "background.png")).convert("RGB")
    menu  = menu_frame(icons)
    r0x   = (W + XSP - (TILE + XSP) * n) // 2

    # --- the menu arriving: each tile a beat after the one before it
    tiles = [(r0x + i * (TILE + XSP), R0Y) for i in range(n)]
    r1x   = (W + XSP - (TILE1 + XSP) * 5) // 2
    tiles += [(r1x + i * (TILE1 + XSP), R0Y + TILE + YSP) for i in range(5)]
    sizes = [TILE] * n + [TILE1] * 5
    frames = []
    for f in range(1, IN_FRAMES + len(tiles) + 1):
        c = bg.copy()
        for i, ((x, y), s) in enumerate(zip(tiles, sizes)):
            a = ease_out(f - i, IN_FRAMES) if f > i else 0
            box = (x, y, x + s, y + s)
            c.paste(blend(bg.crop(box), menu.crop(box), a), box)
        frames.append(c)
    save_gif("anim-in.gif", frames, IN_STEP_MS)

    # --- the menu leaving, and the chosen tile travelling to the middle
    icon = Image.open(os.path.join(ASSETS, "icons", f"{icons[0]}.png")) \
                .convert("RGBA").resize((BIG, BIG), Image.LANCZOS)
    dest_x, dest_y, cx, cy = layout(icon)
    from_x, from_y = tiles[0]
    strip_y = R0Y
    strip_h = min(TILE + YSP + TILE1 + YSP + 4 * FONT_H, H - strip_y)
    sbox    = (0, strip_y, W, strip_y + strip_h)
    held    = menu.crop((from_x, from_y, from_x + TILE, from_y + TILE))
    frames  = []
    for f in range(1, OUT_FRAMES + 1):
        c = menu.copy()
        c.paste(blend(menu.crop(sbox), bg.crop(sbox), ease_out(f, OUT_FRAMES)), sbox)
        c.paste(held, (from_x, from_y))
        frames.append(c)

    sel  = Image.open(os.path.join(ASSETS, "selection_big.png")).convert("RGBA")
    mask = Image.open(os.path.join(ASSETS, "frost_big.png")).convert("RGBA")

    def tile_at(x, y):
        """The tile composed where it is now: glass shows what is behind it, and
        what is behind it changes as it moves."""
        c = bg.copy().convert("RGBA")
        apply_frost(c, mask, x + ICON_OFF, y + ICON_OFF, FROST)
        c.alpha_composite(sel, (x, y))
        c.alpha_composite(icon, (x + ICON_OFF, y + ICON_OFF))
        return c.crop((x, y, x + TILE, y + TILE)).convert("RGB")

    for f in range(1, MOVE_FRAMES + 1):
        a = ease_out(f, MOVE_FRAMES)
        x = from_x + (dest_x - from_x) * a // 256
        y = from_y + (dest_y - from_y) * a // 256
        c = bg.copy()
        c.paste(tile_at(x, y), (x, y))
        frames.append(c)

    d = dot()
    for k in range(18):
        c = frames[-1].copy().convert("RGBA")
        for i in range(NDOTS):
            ang = angle(k * PERIOD / 18, i)
            c.alpha_composite(d, (int(cx + RING * math.cos(ang) - DOT / 2),
                                  int(cy + RING * math.sin(ang) - DOT / 2)))
        frames.append(c.convert("RGB"))
    save_gif("anim-handoff.gif", frames, (OUT_MS + MOVE_MS) // (OUT_FRAMES + MOVE_FRAMES))


if __name__ == "__main__":
    main()
