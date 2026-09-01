#!/usr/bin/env python3
"""Regenerate the screenshots in README.md from the built assets.

They are rendered by the same code that lays out the real menu, so a screenshot
cannot drift from what the machine draws: the geometry comes from build.py's
constants, which are rEFInd's own arithmetic, and the frosted glass comes from
apply_frost(), which is the box blur the patched rEFInd runs at draw time.

    ./build.py && ./make-screenshots.py

screenshots/settings.png is the one picture here that is not a render: the
settings panel is drawn by the patched bootloader, not by this file, so it is
photographed from the virtual machine instead.

    ./test-vm.sh --settings     # then vm/shot.png, resized, is settings.png
"""
import math, os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import preview, W, H, TILE, XSP, ICON_OFF, PLATE_X, PLATE_Y, PLATE, R0Y
from plymouth import which_os, PERIOD

ASSETS = os.path.join(HERE, "assets")
SHOTS  = os.path.join(HERE, "screenshots")

def shot(name, icons, label, scale=(1920, 1080)):
    dst = os.path.join(SHOTS, name)
    preview(ASSETS, dst, icons, label, scale=scale)
    print(f"  {name}  {len(icons)} entries")

def handoff(stem, t=0.55, ring=True):
    """The screen rEFInd shows on the way to any system, drawn the way it draws it.

    ring=False is the frame the boot logo is taken from. menu.c copies the screen
    with the tile in place and before the ring starts, because the system being
    handed to draws its own and cannot be asked not to, so a picture of the
    hand-over with our dots in it would be a picture of something that is never
    handed over."""
    import math
    from plymouth import still, dot, angle, layout, NDOTS, DOT, RING
    from build import BIG
    path = os.path.join(ASSETS, "icons", f"{stem}.png")
    c = still(ASSETS, path).convert("RGBA")
    icon = Image.open(path).convert("RGBA").resize((BIG, BIG), Image.LANCZOS)
    _, _, cx, cy = layout(icon)
    if ring:
        d = dot()
        for i in range(NDOTS):
            a = angle(t, i)
            c.alpha_composite(d, (int(cx + RING * math.cos(a) - DOT / 2),
                                  int(cy + RING * math.sin(a) - DOT / 2)))
    return c.convert("RGB")


def label(im, rows):
    """Caption a stacked comparison, in the picture rather than beside it.

    Two frames of the same dune are hard to tell apart at a glance, which is the
    point being made and also the reason the point is invisible without a word
    on each half."""
    from build import FONT_BOLD
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT_BOLD, 20)
    for text, y in rows:
        d.text((21, y + 1), text, font=f, fill=(0, 0, 0))
        d.text((20, y),     text, font=f, fill=(235, 235, 235))


def icon_sheet():
    """Every themed logo, on the glass, at the size the menu draws it."""
    from build import shades, duotone, read_tint, NAMES
    # One tile per logo, not one per name rEFInd knows. Five Ubuntu release
    # code-names all carry the Ubuntu logo, and a sheet with Ubuntu on it five
    # times says less than one with Ubuntu on it once.
    seen, names = set(), []
    for n in sorted(os.listdir(os.path.join(ASSETS, "icons"))):
        if not (n.startswith("os_") and n.endswith(".png")):
            continue
        label = NAMES.get(n[3:-4], n[3:-4])
        if label in seen:
            continue
        seen.add(label)
        names.append(n)
    tint  = read_tint(ASSETS)
    table = shades(Image.open(os.path.join(ASSETS, "background.png")).convert("RGBA"),
                   1.0)["ramp"] if tint else None
    cols, cell = 12, 160
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (26, 28, 34))
    for i, n in enumerate(names):
        im = Image.open(os.path.join(ASSETS, "icons", n)).convert("RGBA")
        if tint:
            im = duotone(im, table, tint / 100.0)
        im = im.resize((cell, cell), Image.LANCZOS)
        sheet.paste(im, ((i % cols) * cell, (i // cols) * cell), im)
    sheet.save(os.path.join(SHOTS, "icons.png"), optimize=True)
    print(f"  icons.png  {len(names)} logos, every one on the same glass")


def main():
    if not os.path.exists(os.path.join(ASSETS, "frost_big.png")):
        sys.exit("assets missing -- run ./build.py first")
    os.makedirs(SHOTS, exist_ok=True)

    # what this machine shows
    shot("menu.png", ["os_win8", "os_ubuntu"], "Boot Windows")

    # Two entries and four, one above the other.
    #
    # These were two separate pictures of a dark desert with tiles on it, several
    # screens apart, and the thing they were meant to show -- that rEFInd
    # re-centres the row and every plate travels with its entry -- was left for
    # the reader to hold in their head while scrolling. Side by side it is just
    # visible.
    two  = os.path.join(SHOTS, ".two.png")
    four = os.path.join(SHOTS, ".four.png")
    preview(ASSETS, two,  ["os_win8", "os_ubuntu"], "Boot Windows", scale=(1280, 720))
    preview(ASSETS, four, ["os_win8", "os_ubuntu", "os_fedora", "os_debian"],
            "Boot Fedora", scale=(1280, 720))
    pair = Image.new("RGB", (1280, 1444), (24, 24, 28))
    pair.paste(Image.open(two),  (0, 0))
    pair.paste(Image.open(four), (0, 724))
    label(pair, [("two systems", 16), ("four: the row re-centres and the glass moves with it", 740)])
    pair.save(os.path.join(SHOTS, "entries.png"), optimize=True)
    for f in (two, four):
        os.remove(f)
    print("  entries.png  two systems, then four")

    # Every logo the theme draws, on its own glass. Nothing else here shows what
    # the icon set actually is.
    icon_sheet()

    # The same menu with the colour taken from the photograph, and with it left
    # alone. This is the whole of what `tint` does, and it was described in four
    # paragraphs and shown nowhere.
    warm = os.path.join(SHOTS, ".warm.png")
    cold = os.path.join(SHOTS, ".cold.png")
    preview(ASSETS, warm, ["os_win8", "os_ubuntu"], "Boot Windows",
            scale=(1280, 720), tint=100)
    preview(ASSETS, cold, ["os_win8", "os_ubuntu"], "Boot Windows",
            scale=(1280, 720), tint=0)
    pair = Image.new("RGB", (1280, 1444), (24, 24, 28))
    pair.paste(Image.open(warm), (0, 0))
    pair.paste(Image.open(cold), (0, 724))
    label(pair, [("tint 100: the colour is taken from the photograph", 16),
                 ("tint 0: every logo in the colours it came with", 740)])
    pair.save(os.path.join(SHOTS, "tint.png"), optimize=True)
    for f in (warm, cold):
        os.remove(f)
    print("  tint.png  colour from the photograph, and the logos' own")

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
            # What goes into the ACPI table when Windows is chosen: the same
            # frame without our ring, which is what menu.c copies.
            handoff(stem, ring=False).resize((1920, 1080), Image.LANCZOS) \
                .save(os.path.join(SHOTS, "windows-handoff.png"), optimize=True)
    grid.resize((960, 1620), Image.LANCZOS).save(os.path.join(SHOTS, "handoff-any.png"),
                                                 optimize=True)
    print("  handoff-any.png, windows-handoff.png  the same screen for three systems")

    # The Plymouth splash: what the initramfs actually draws.
    #
    # This picture used to be a file in screenshots/ that nothing here produced,
    # so it went on showing a ring of the size it was before the ring was
    # changed, and nobody could tell. It is the theme's own background.png with
    # the theme's own dots on it, in the theme's own places -- the same
    # plymouth.py that writes the theme writes this.
    from plymouth import still, dot, angle, layout, NDOTS, DOT, RING
    from build import BIG
    stem = f"os_{which_os()[0]}"
    if not os.path.exists(os.path.join(ASSETS, "icons", f"{stem}.png")):
        stem = "os_linux"
    path = os.path.join(ASSETS, "icons", f"{stem}.png")
    c    = still(ASSETS, path).convert("RGBA")
    icon = Image.open(path).convert("RGBA").resize((BIG, BIG), Image.LANCZOS)
    _, _, cx, cy = layout(icon)
    d = dot()
    for i in range(NDOTS):
        a = angle(0.35 * PERIOD, i)
        c.alpha_composite(d, (int(cx + RING * math.cos(a) - DOT / 2),
                              int(cy + RING * math.sin(a) - DOT / 2)))
    splash = c.convert("RGB").resize((1920, 1080), Image.LANCZOS)
    splash.save(os.path.join(SHOTS, "plymouth.png"), optimize=True)
    print("  plymouth.png  the splash, drawn by the code that generates it")

    # The handover, in one picture. These were two full-screen photographs of
    # the same dune several screens apart, and the point of them -- that the
    # second is the first, continued by a different program -- is only visible
    # if you can see both at once.
    # The same system on both halves, or the picture says "Windows, then Ubuntu"
    # and the point of it is lost. plymouth.png is necessarily this machine's
    # own system, so the rEFInd frame is drawn for that one too.
    handed = handoff(stem).resize((1280, 720), Image.LANCZOS)
    pair = Image.new("RGB", (1280, 1444), (24, 24, 28))
    pair.paste(handed, (0, 0))
    pair.paste(splash.resize((1280, 720), Image.LANCZOS), (0, 724))
    # Label them. Without it the two halves are so alike that the picture looks
    # like the same image printed twice, which is the claim but not obviously
    # the evidence for it.
    label(pair, [("rEFInd, the last frame it draws", 16),
                 ("Plymouth, a moment later", 740)])
    pair.save(os.path.join(SHOTS, "continues.png"), optimize=True)
    print("  continues.png  the last frame rEFInd draws, and the first Plymouth draws")

if __name__ == "__main__":
    main()
