#!/usr/bin/env python3
"""Generate a Plymouth theme that carries on from the boot menu.

The splash is the menu with one tile left: the same photograph, the same frosted
panel at the same coordinates, holding the logo and the name of the system that
was chosen. Underneath it turns a ring of dots.

What rEFInd cannot do, Plymouth can do for free. A panel inside a boot menu icon
cannot blur what is behind it because it does not know where it will be drawn --
that is why the boot menu needed a patched bootloader. Here the background never
moves and neither does the panel, so the frost is composited once, into the
image, and costs nothing at boot: 85 ms to decode 3840x2160, once.

    ./build.py && ./plymouth.py && sudo ./setup.sh
"""
import argparse, math, os, re, shutil, sys
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import (apply_frost, duotone, shades, read_tint, W, H, TILE, TILE1,
                   XSP, YSP, ICON_OFF, PLATE_X, PLATE_Y, PLATE, BIG, R0Y,
                   FROST, SS, DOT_PX)

NAME    = "refind-frosted"
NDOTS   = 6            # Windows uses five; six closes the ring more evenly
DOT     = DOT_PX       # one dot, at 3840x2160; build.py draws it
RING    = 70           # radius of the circle the dots travel
# 70, not the 110 this started at. The ring is a small thing under a name, the
# way Windows draws it -- 140px across at 3840x2160, 6.5% of the screen's height.
# At 110 it was 10%, which reads as a hoop rather than as a spinner.
PERIOD  = 1.8          # seconds for one turn
STAGGER = 0.100        # fraction of a period between one dot and the next
SWING   = 0.55         # 0 = constant speed, 1 = a full stop at the top
# Those four are not free. The dots span 2*pi * g'(p) * (NDOTS-1) * STAGGER of
# the circle, and g'(p) runs between 1-SWING and 1+SWING, so the arc closes to
# 81 degrees and opens to 279. At its tightest that is 99px of arc holding 78px
# of dots: they gather without ever colliding, which is the whole trick.


def which_os():
    """Name the system this theme is being built for, from os-release."""
    info = {}
    try:
        for line in open("/etc/os-release"):
            if "=" in line:
                k, v = line.rstrip().split("=", 1)
                info[k] = v.strip('"')
    except OSError:
        pass
    return info.get("ID", "linux"), info.get("NAME", "Linux")


def pick_icon(assets, os_id):
    """The same icon the boot menu would show for this system."""
    for stem in (f"os_{os_id}", "os_linux", "os_unknown"):
        p = os.path.join(assets, "icons", f"{stem}.png")
        if os.path.exists(p):
            return p, stem
    sys.exit("no icon found -- run ./build.py first")


def layout(icon):
    """Where the tile and the ring go, so that what you see is in the middle.

    Centring the tile is not the same as centring the picture. The icon is a
    panel with a name under it inside a larger transparent square, and the ring
    hangs below that again, so a tile in the middle of the screen leaves the
    group people actually look at sitting 195px low at 3840x2160.

    So measure the ink rather than the boxes: the top of the panel comes from the
    icon's own alpha channel, the bottom from where the ring is, and the whole
    group is shifted until that span is centred. Reading it off the alpha means
    an icon with a longer name, or none at all, still lands right."""
    tile_x = (W + XSP - (TILE + XSP)) // 2       # rEFInd's own centring, n = 1
    tile_y = R0Y
    cy     = tile_y + TILE + YSP + TILE1 + YSP + 75
    # The same threshold rEFInd uses. ImageInkTop() in menu.c takes the first
    # row whose alpha exceeds 8; Pillow's getbbox() takes the first row whose
    # alpha exceeds 0, and the icons fade in from alpha 1 over their top
    # thirty-odd rows. Two different answers, 37 rows apart, put the splash 18
    # pixels below the frame the boot menu had just handed over -- at the one
    # moment the whole design is about the two being the same picture.
    alpha  = icon.split()[3].point(lambda v: 255 if v > 8 else 0)
    box    = alpha.getbbox()
    top    = tile_y + ICON_OFF + (box[1] if box else 0)
    bottom = cy + RING + DOT // 2
    shift  = H // 2 - (top + bottom) // 2
    return tile_x, tile_y + shift, W // 2, cy + shift


def still(assets, icon_path):
    """The menu, drawn with a single entry: what the splash sits on.

    The artwork on disk is neutral, because rEFInd colours it at boot. Plymouth
    has no such moment -- its background is a finished picture -- so the same
    colouring is done here, from the same photograph, or the splash would arrive
    in different colours from the menu it is continuing."""
    bg = Image.open(os.path.join(assets, "background.png")).convert("RGBA")
    tint = read_tint(assets)
    table = shades(bg, 1.0)["ramp"] if tint else None
    def paint(path, size):
        im = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        return duotone(im, table, tint / 100.0) if tint else im

    icon = paint(icon_path, BIG)
    r0x, r0y, _, _ = layout(icon)
    ix, iy = r0x + ICON_OFF, r0y + ICON_OFF
    c = bg
    apply_frost(c, Image.open(os.path.join(assets, "frost_big.png")).convert("RGBA"),
                ix, iy, FROST)
    c.alpha_composite(paint(os.path.join(assets, "selection_big.png"), TILE), (r0x, r0y))
    c.alpha_composite(icon, (ix, iy))
    return c.convert("RGB")


def dot(assets=None):
    """The dot the spinner is made of.

    build.py writes it, because its colour is drawn from the photograph like
    every other colour in the theme. A white one drawn here would be the one
    thing on the screen that did not come from the picture."""
    root = assets or os.path.join(HERE, "assets")
    path = os.path.join(root, "dot.png")
    if os.path.exists(path):
        im = Image.open(path).convert("RGBA")
        tint = read_tint(root)
        if tint:
            bg = Image.open(os.path.join(root, "background.png")).convert("RGBA")
            im = duotone(im, shades(bg, 1.0)["ramp"], tint / 100.0)
        return im
    d = Image.new("RGBA", (DOT * SS, DOT * SS), (0, 0, 0, 0))
    ImageDraw.Draw(d).ellipse([0, 0, DOT * SS - 1, DOT * SS - 1], fill=(255, 255, 255, 255))
    return d.resize((DOT, DOT), Image.LANCZOS)


def angle(t, i):
    """Where dot i is at time t.

    Each dot walks the same eased path, a little later than the one before, so
    they bunch where the path is slow and string out where it is fast. That
    gathering and spilling is what makes the Windows spinner read as one moving
    thing rather than six dots on a carousel."""
    p = (t / PERIOD - i * STAGGER) % 1.0
    g = p - SWING * math.sin(2 * math.pi * p) / (2 * math.pi)
    return 2 * math.pi * g - math.pi / 2


SCRIPT = """\
# Plymouth theme for {NAME}: the boot menu, continued.
#
# The photograph and the frosted panel are already in background.png. The
# background never moves and neither does the panel, so the blur was composited
# once at build time -- what the boot menu needed a patched bootloader for costs
# nothing here. All that is left to do is turn the ring of dots.
#
# Each dot walks the same eased path a little later than the one before it, so
# they gather where the path is slow and spill out where it is fast. That
# gathering is what makes six dots read as one moving thing.

NDOTS   = {NDOTS};
PERIOD  = {PERIOD};
STAGGER = {STAGGER};
SWING   = {SWING};
RING    = {RING}.0 / {H}.0;      # as a fraction of screen height, so it scales
DOT     = {DOT}.0 / {H}.0;
CX      = 0.5;                   # the panel is centred
CY      = {CY}.0 / {H}.0;
REFRESH = 50.0;                  # Plymouth calls the refresh function 50x a second

background = Image("background.png");
dot_image  = Image("dot.png");

# How Plymouth actually lays out more than one screen.
#
# It is not a desktop. script-lib-sprite.c takes the largest display, calls that
# the canvas, and centres every other display on it -- display->x is
# (max_width - this_width) / 2. Then it draws *every* sprite on *every* display,
# offset by that display's origin.
#
# So a theme that makes one background per monitor and places each at its own
# origin does not get one background per monitor. It gets all of them on all of
# them, overlapping: on a 4K screen beside a 1080p one, the 1080p background
# lands in the middle of the 4K one and the 4K background covers the 1080p
# screen offset by 960 pixels. The way to draw on two screens here is to stop
# trying to, and draw once on the canvas they are both windows onto. Everything
# in this theme is centred, so the smaller screen sees the middle of it, which
# is the tile, the name and the ring.
W = Window.GetWidth();
H = Window.GetHeight();
if (W < 1) {{
    W = 1024;
    H = 768;
}}

if (background != NULL) {{
    # Only resample if the picture is not already the size of the canvas.
    # Plymouth's resize is a 2x2 tap over 8.3 million pixels, single threaded,
    # in the initramfs: worth not doing for a picture that is already right. It
    # usually is -- the theme is built for this screen.
    picture = background;
    if (background.GetWidth() != W) {{
        picture = background.Scale(W, H);
    }} else {{
        if (background.GetHeight() != H) {{
            picture = background.Scale(W, H);
        }}
    }}
    wallpaper = Sprite(picture);
    wallpaper.SetPosition(0, 0, -100);
}}

# The size of a point of type is the one measurement in this theme that is not a
# fraction of the screen, so it is the one that has to be worked out. 24 point is
# right on a 1080-line screen; on a 4K screen it is half of what it should be.
FONT = "Ubuntu " + Math.Int(24 * H / 1080.0);

dot_size = Math.Int(DOT * H);
if (dot_size < 3) {{
    dot_size = 3;
}}
ring_r = RING * H;
ring_x = CX * W;
ring_y = CY * H;
for (d = 0; d < NDOTS; d++) {{
    dots[d] = Sprite(dot_image.Scale(dot_size, dot_size));
}}

# Anything not covered by a screen -- letterboxing, a monitor plugged in later --
# is black, and not some pixel picked out of the corner of the photograph.
Window.SetBackgroundTopColor(0.0, 0.0, 0.0);
Window.SetBackgroundBottomColor(0.0, 0.0, 0.0);

frame = 0;
fun refresh_callback() {{
    frame++;
    t = frame / REFRESH;
    for (d = 0; d < NDOTS; d++) {{
        p = t / PERIOD - d * STAGGER;
        p = p - Math.Int(p);
        if (p < 0) {{
            p = p + 1;
        }}
        g = p - SWING * Math.Sin(2 * Math.Pi * p) / (2 * Math.Pi);
        a = 2 * Math.Pi * g - Math.Pi / 2;
        dots[d].SetPosition(ring_x + ring_r * Math.Cos(a) - dot_size / 2,
                            ring_y + ring_r * Math.Sin(a) - dot_size / 2, 100);
        dots[d].SetOpacity(1);
    }}
}}

# ---------------------------------------------------------------- messages
# Root is not encrypted here, but a splash that cannot ask for a passphrase
# leaves a machine that needs one waiting at a screen which says nothing.
# Sprites have to be globals.
#
# The three fractions below sit between the ring and 0.75. Plymouth centres
# every display on the largest one and shows each the middle of the canvas, so
# on a 1080-line screen beside a 2160-line one only 0.25 to 0.75 is visible --
# and a passphrase prompt nobody can see is a machine that looks hung.

message_sprite  = Sprite();
prompt_sprite   = Sprite();
bullets_sprite  = Sprite();

fun centre(sprite, image, fraction) {{
    if (image == NULL) {{
        return;
    }}
    sprite.SetImage(image);
    sprite.SetPosition((W - image.GetWidth()) / 2,
                       fraction * H - image.GetHeight() / 2, 200);
    sprite.SetOpacity(1);
}}

fun message_callback(text) {{
    centre(message_sprite, Image.Text(text, 0.85, 0.85, 0.85, 1.0, FONT, "center"), 0.735);
}}
Plymouth.SetMessageFunction(message_callback);

fun display_password_callback(prompt, bullets) {{
    centre(prompt_sprite, Image.Text(prompt, 1.0, 1.0, 1.0, 1.0, FONT, "center"), 0.71);
    # NOT "dots". Plymouth's script has no local scope: every assignment is a
    # global, and `dots` is the array of spinner sprites. Building the row of
    # asterisks in a variable of that name replaced the spinner with a string
    # the first time somebody typed a character of their passphrase, and the
    # next refresh had nothing left to turn.
    bullet_text = "";
    for (i = 0; i < bullets; i++) {{
        bullet_text = bullet_text + "*";
    }}
    if (bullets > 0) {{
        centre(bullets_sprite, Image.Text(bullet_text, 1.0, 1.0, 1.0, 1.0, FONT, "center"), 0.735);
    }} else {{
        bullets_sprite.SetOpacity(0);
    }}
}}
Plymouth.SetDisplayPasswordFunction(display_password_callback);

fun display_normal_callback() {{
    prompt_sprite.SetOpacity(0);
    bullets_sprite.SetOpacity(0);
}}
Plymouth.SetDisplayNormalFunction(display_normal_callback);

fun quit_callback() {{
    if (background != NULL) {{
        wallpaper.SetOpacity(0);
    }}
    for (d = 0; d < NDOTS; d++) {{
        dots[d].SetOpacity(0);
    }}
    message_sprite.SetOpacity(0);
    prompt_sprite.SetOpacity(0);
    bullets_sprite.SetOpacity(0);
}}
Plymouth.SetQuitFunction(quit_callback);

refresh_callback();
Plymouth.SetRefreshFunction(refresh_callback);
"""

# Every value here must be on ONE line. Plymouth's key-file reader has no notion
# of continuations, so a Description wrapped onto a second line leaves that line
# looking like a key with no "=", the group stops being read there, and
# ModuleName -- which comes after it -- is never seen. Plymouth then loads
# "(null).so", fails, and falls back to the text theme: a boot with no splash at
# all, only console messages, and nothing anywhere saying why.
THEME = """\
[Plymouth Theme]
Name={pretty}
Description=The rEFInd boot menu carried on into the splash: the same photograph, the same frosted panel, holding the system that was chosen.
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/{NAME}
ScriptFile=/usr/share/plymouth/themes/{NAME}/{NAME}.script
"""


def main():
    ap = argparse.ArgumentParser(description="Build the Plymouth theme.")
    ap.add_argument("--assets", default=os.path.join(HERE, "assets"))
    ap.add_argument("--out", default=os.path.join(HERE, "plymouth", NAME))
    ap.add_argument("--os", default=None, help="icon stem to use (default: this system)")
    ap.add_argument("--size", default=None, metavar="WxH",
                    help="compose at this size instead of 3840x2160 -- give the "
                         "resolution the machine actually boots at, and Plymouth "
                         "has nothing left to scale")
    args = ap.parse_args()
    target = None
    if args.size:
        try:
            tw, th = (int(v) for v in args.size.lower().split("x"))
        except ValueError:
            sys.exit("--size wants WxH, like 3840x2160")
        if tw < 320 or th < 240 or tw > 16384 or th > 16384:
            sys.exit("--size is out of range")
        target = (tw, th)

    os_id, os_name = which_os()
    if args.os:
        os_id = args.os
    icon_path, stem = pick_icon(args.assets, os_id)

    os.makedirs(args.out, exist_ok=True)
    _, _, _, cy = layout(Image.open(icon_path).convert("RGBA").resize((BIG, BIG), Image.LANCZOS))
    # Composed at 3840x2160 -- the master, and the size everything in this
    # project is drawn at -- and then brought to the screen's own size here,
    # with Lanczos, rather than left for Plymouth to scale with a two-tap
    # filter at draw time. Reducing 4K to a smaller panel with two taps is
    # what made the splash look grainy while the same photograph looked clean
    # in the boot menu: the menu is drawn at the size it is shown.
    picture = still(args.assets, icon_path)
    if target and (target != picture.size):
        picture = picture.resize(target, Image.LANCZOS)
    picture.save(os.path.join(args.out, "background.png"), "PNG", optimize=True)
    dot(args.assets).save(os.path.join(args.out, "dot.png"))
    open(os.path.join(args.out, f"{NAME}.script"), "w").write(
        SCRIPT.format(NAME=NAME, NDOTS=NDOTS, PERIOD=PERIOD, STAGGER=STAGGER,
                      SWING=SWING, RING=RING, DOT=DOT, H=H, CY=cy))
    open(os.path.join(args.out, f"{NAME}.plymouth"), "w").write(
        THEME.format(NAME=NAME, pretty="rEFInd Frosted"))

    size = sum(os.path.getsize(os.path.join(args.out, f)) for f in os.listdir(args.out))
    print(f"  system     {os_name} -> {stem}.png")
    print(f"  spinner    {NDOTS} dots, radius {RING}px, {PERIOD}s a turn, centre y={cy}")
    print(f"  centred    on the ink, not on the tile")
    print(f"  size       {picture.size[0]}x{picture.size[1]}"
          + ("  (composed at 3840x2160, brought here with Lanczos)"
             if picture.size != (W, H) else "  (the master size, nothing scaled)"))
    print(f"  theme      {args.out}  ({size/1048576:.1f} MB)")


if __name__ == "__main__":
    main()
