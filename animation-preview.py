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
                   apply_frost, preview, duotone, shades, read_tint)
from plymouth import layout, dot, angle, NDOTS, DOT, RING, PERIOD

IN_FRAMES, SEL_FRAMES, OUT_FRAMES, MOVE_FRAMES = 9, 5, 7, 14
# menu.c's durations, in milliseconds. The frame counts above are the resolution
# of the easing curve, not the length of the animation: the bootloader runs each
# one by the clock and draws as many frames as the machine manages.
IN_STEP_MS, OUT_MS, MOVE_MS = 40, 280, 450
IN_RISE    = 44          # ANIM_IN_RISE: how far a tile climbs into place, at 2160
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


def save_gif(name, frames, ms, scale=None, hold=0, slow=1):
    """Write the animation as a GIF, without turning the photograph into a poster.

    A GIF carries at most 256 colours. Asking for 64 of them, and choosing them
    afresh for every frame, is what made these look like a different project
    from the screenshots beside them: a dune lit by a low sun is a long smooth
    ramp of one hue, and 64 entries cannot hold a ramp, so it came out as bands
    of flat orange with the tile and the label pulled along with it -- and the
    bands moved between frames, because each frame had picked its own 64.

    So: one palette for the whole animation, chosen from every frame at once,
    with all 256 entries, and Floyd-Steinberg to break up what is left. It costs
    file size -- dithering is noise, and noise does not compress -- which is
    why the frames are 960 wide and not 1920.
    """
    size   = scale or SCALE
    frames = [f.resize(size, Image.LANCZOS).convert("RGB") for f in frames]

    tall = Image.new("RGB", (size[0], size[1] * len(frames)))
    for i, f in enumerate(frames):
        tall.paste(f, (0, i * size[1]))
    shared = tall.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE)

    frames = [f.quantize(palette=shared, dither=Image.FLOYDSTEINBERG) for f in frames]

    # How long each frame is held, and how long the last one is held for.
    #
    # These animations last between half a second and one; played at their true
    # speed in a loop that restarts the instant it ends, they read as a flicker
    # rather than as a movement, and you cannot see what happened. So the ones
    # that are watched rather than measured are slowed, and the finished picture
    # is held before it starts again. The caption says which are slowed and by
    # how much, because a picture of an animation that runs at a speed the
    # machine does not is worth nothing if it does not say so.
    each = [ms * slow] * len(frames)
    if hold:
        each[-1] = hold
    path = os.path.join(SHOTS, name)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=each, loop=0, optimize=True)
    secs = sum(each) / 1000.0
    print(f"  {name}  {len(frames)} frames  {secs:.1f}s a loop  "
          f"{os.path.getsize(path)/1024:.0f} KB")


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
            # The tile climbs as it fades: the same eased number does both, so
            # it arrives exactly where it stops being transparent. menu.c
            # crops one taller band of photograph per tile and slides the tile
            # up it; here the band is simply the background we already have.
            lift = min(IN_RISE, H - (y + s))
            down = lift - (lift * a) // 256
            box  = (x, y, x + s, y + s + lift)
            band = bg.crop(box)
            tile = menu.crop((x, y, x + s, y + s))
            over = band.copy()
            over.paste(tile, (0, down))
            c.paste(blend(band, over, a), box)
        frames.append(c)
    save_gif("anim-in.gif", frames, IN_STEP_MS, slow=2, hold=1800)

    # --- the menu leaving, and the chosen tile travelling to the middle
    # Colour it the way rEFInd will. The icons on disk are neutral -- the whole
    # arrangement is that the bootloader takes the colour from the photograph at
    # boot -- so a preview that skips that step shows Windows in Windows blue and
    # the menu beside it in the colour of the sand, which is two pictures of two
    # different programs.
    tint  = read_tint(ASSETS)
    table = shades(Image.open(os.path.join(ASSETS, "background.png")).convert("RGBA"),
                   1.0)["ramp"] if tint else None
    icon = Image.open(os.path.join(ASSETS, "icons", f"{icons[0]}.png")).convert("RGBA")
    if tint:
        icon = duotone(icon, table, tint / 100.0)
    icon = icon.resize((BIG, BIG), Image.LANCZOS)
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

    # The tile has landed; from here only the ring turns.
    #
    # Every frame is drawn on the still, not on the frame before it. Drawing
    # each one on its predecessor left the dots where they had been as well as
    # where they were, so eighteen frames added up to a solid ring being traced
    # out -- which is a perfectly nice animation, and not the one the bootloader
    # runs.
    landed = frames[-1].convert("RGBA")
    d = dot()
    for k in range(18):
        c = landed.copy()
        for i in range(NDOTS):
            ang = angle(k * PERIOD / 18, i)
            c.alpha_composite(d, (int(cx + RING * math.cos(ang) - DOT / 2),
                                  int(cy + RING * math.sin(ang) - DOT / 2)))
        frames.append(c.convert("RGB"))
    save_gif("anim-handoff.gif", frames,
             (OUT_MS + MOVE_MS) // (OUT_FRAMES + MOVE_FRAMES), slow=2, hold=1200)

    # --- the ring on its own, close up
    #
    # This used to be a file in screenshots/ that nothing here produced, which
    # meant the one picture in the README of the thing the ring actually does
    # was the one picture that could not be checked against the code. It is the
    # same dots on the same eased path as the splash above, cropped to the ring.
    spin, span = [], int(RING * 2 + DOT * 3)
    box = (int(cx - span / 2), int(cy - span / 2),
           int(cx - span / 2) + span, int(cy - span / 2) + span)
    plate = landed
    for k in range(45):
        c = plate.copy()
        for i in range(NDOTS):
            ang = angle(k * PERIOD / 45, i)
            c.alpha_composite(d, (int(cx + RING * math.cos(ang) - DOT / 2),
                                  int(cy + RING * math.sin(ang) - DOT / 2)))
        spin.append(c.convert("RGB").crop(box))
    # True speed: one turn is 1.8 seconds on the machine and 1.8 seconds here.
    # It loops without a seam, so there is nothing to hold at the end.
    save_gif("spinner.gif", spin, int(PERIOD * 1000 / 45), scale=(200, 200))


if __name__ == "__main__":
    main()
