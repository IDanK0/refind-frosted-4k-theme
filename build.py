#!/usr/bin/env python3
"""Generate every asset of the rEFInd theme from a single background photo.

Nothing is baked into the background any more. The frosted plate and the OS
name live inside each icon, so they travel with the entry: rEFInd re-centres
the row every time the number of entries changes

    row0PosX = (UGAWidth + 8 - (TileSizes[0] + 8) * row0Count) / 2

and anything painted into the background at a fixed position would be left
behind. Putting the plate in the icon makes the theme correct for two entries,
for five, and for whatever a USB stick adds tomorrow.

    ./build.py                                  # library default
    ./build.py --background library/desert-skies.jpg --darken 60
    ./build.py --background ~/mine.png --darken auto
"""
import argparse, colorsys, glob, json, math, os, sys
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageStat

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- geometry
W, H = 3840, 2160
XSP, YSP = 8, 16          # TILE_XSPACING / TILE_YSPACING, #define'd in menu.c
SS = 4                    # supersampling for the vector artwork
BIG, SMALL = 549, 48

TILE   = (BIG * 9) // 8           # TileSizes[0] = big_icon_size * 9/8
TILE1  = (SMALL * 4) // 3         # TileSizes[1] = small_icon_size * 4/3
R0Y    = (H // 2) - TILE // 2     # the OS row is always vertically centred
MAXVIS = W // (TILE + XSP) - 1    # entries rEFInd will show without scrolling

# inside the BIG icon canvas
FROST     = 14                    # frost_radius in refind.conf; the preview matches it
GLASS_A   = 36                    # how much of the panel's own tint there is
VEIL_A    = 18                    # the raking light across the top of it
# These three decide whether the panel reads as glass or as a painted tile. Too
# much blur and too much tint compound: a wide blur averages the whole panel to
# one colour and the tint then covers what little is left, so the photograph
# disappears and a pale rectangle is all that remains. Measured on a detailed
# photograph, going from (32, 64, 46) to (14, 36, 18) lifts how much of the
# picture survives behind the glass from 20.8 to 24.4 and drops the panel's
# lightness from 101 to 79.
PLATE     = 340                   # frosted tile
PLATE_Y   = 64                    # pushed up to leave room for the name
LOGO      = 218
NAME_SIZE = 56
DOT_PX    = 20                    # one dot of the spinner, at 3840x2160
NAME_Y    = PLATE_Y + PLATE + 22
ICON_OFF  = (TILE - BIG) // 2     # icon is centred in the tile
PLATE_X   = (BIG - PLATE) // 2

FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BOX = (1299, 850, 2541, 1400)     # strip sampled to judge how bright a photo is
TARGET_LUM = 30.0                 # what --darken auto aims for
TARGET_DETAIL = 0.60              # what --blur auto aims for
BLUR_STEPS = (0, 4, 8, 12, 16, 20, 26, 34, 44)

# rEFInd matches an icon by OS name; give each one a readable label so a
# system detected next year arrives already named.
NAMES = {
    "arch": "Arch Linux", "artful": "Ubuntu", "bionic": "Ubuntu", "centos": "CentOS",
    "chakra": "Chakra", "chrome": "ChromeOS", "clover": "Clover",
    "crunchbang": "CrunchBang", "debian": "Debian", "devuan": "Devuan",
    "elementary": "elementary OS", "endeavouros": "EndeavourOS", "fedora": "Fedora",
    "freebsd": "FreeBSD", "frugalware": "Frugalware", "gentoo": "Gentoo",
    "gummiboot": "systemd-boot", "haiku": "Haiku", "hwtest": "Hardware Test",
    "kubuntu": "Kubuntu", "legacy": "Legacy Boot", "linux": "Linux",
    "linuxmint": "Linux Mint", "lubuntu": "Lubuntu", "mac": "macOS",
    "mageia": "Mageia", "mandriva": "Mandriva", "manjaro": "Manjaro",
    "netbsd": "NetBSD", "network": "Network", "opensuse": "openSUSE",
    "redhat": "Red Hat", "refind": "rEFInd", "refit": "rEFIt",
    "slackware": "Slackware", "suse": "SUSE", "systemd": "systemd-boot",
    "trusty": "Ubuntu", "ubuntu": "Ubuntu", "uefi": "UEFI", "unknown": "",
    "void": "Void Linux", "win": "Windows", "win8": "Windows",
    "xenial": "Ubuntu", "xubuntu": "Xubuntu", "zesty": "Ubuntu",
}

# ------------------------------------------------------------------ artwork
def aa(n, fn):
    """Draw at 4x and shrink: cheap, reliable antialiasing."""
    im = Image.new("RGBA", (n * SS, n * SS), (0, 0, 0, 0))
    fn(ImageDraw.Draw(im), n * SS)
    return im.resize((n, n), Image.LANCZOS)

def logo_windows(d, S):
    h = S * 0.94; g = S * 0.046; s = (h - g) / 2; r = s * 0.11; C = S / 2
    for gx in (0, 1):
        for gy in (0, 1):
            x, y = C - h / 2 + gx * (s + g), C - h / 2 + gy * (s + g)
            d.rounded_rectangle([x, y, x + s, y + s], radius=r, fill=(96, 190, 245, 255))

def logo_ubuntu(d, S):
    C = S / 2; R = S * 0.372; T = int(S * 0.093); DOT = S * 0.105
    for a in (-90, 30, 150):
        d.arc([C - R, C - R, C + R, C + R], a + 26, a + 94, fill=(245, 130, 80, 255), width=T)
    for a in (-90, 30, 150):
        x, y = C + R * math.cos(math.radians(a)), C + R * math.sin(math.radians(a))
        d.ellipse([x - DOT, y - DOT, x + DOT, y + DOT], fill=(245, 130, 80, 255))

GR = (232, 238, 250, 255)
def t_about(d, S):
    m = S * .09; d.ellipse([m, m, S - m, S - m], outline=GR, width=int(S * .075))
    d.ellipse([S*.44, S*.24, S*.56, S*.36], fill=GR)
    d.rounded_rectangle([S*.44, S*.43, S*.56, S*.76], radius=S*.06, fill=GR)
def t_hidden(d, S):
    d.polygon([(S*.14,S*.50),(S*.50,S*.12),(S*.88,S*.12),(S*.88,S*.50),(S*.52,S*.88),(S*.14,S*.50)],
              outline=GR, width=int(S*.075))
    d.ellipse([S*.68, S*.22, S*.80, S*.34], fill=GR)
def t_power(d, S):
    m = S * .16; d.arc([m, m, S - m, S - m], -55, 235, fill=GR, width=int(S*.085))
    d.rounded_rectangle([S*.455, S*.10, S*.545, S*.46], radius=S*.045, fill=GR)
def t_reset(d, S):
    m = S * .16; d.arc([m, m, S - m, S - m], 120, 60, fill=GR, width=int(S*.085))
    d.polygon([(S*.80,S*.10),(S*.90,S*.42),(S*.58,S*.34)], fill=GR)
def t_chip(d, S):
    a, b = S * .26, S * .74
    d.rounded_rectangle([a,a,b,b], radius=S*.07, outline=GR, width=int(S*.07))
    d.rounded_rectangle([S*.42,S*.42,S*.58,S*.58], radius=S*.03, fill=GR)
    for t in (.38, .5, .62):
        d.rectangle([S*t-S*.022, S*.10, S*t+S*.022, a], fill=GR)
        d.rectangle([S*t-S*.022, b, S*t+S*.022, S*.90], fill=GR)
        d.rectangle([S*.10, S*t-S*.022, a, S*t+S*.022], fill=GR)
        d.rectangle([b, S*t-S*.022, S*.90, S*t+S*.022], fill=GR)
TOOLS = [(t_about, "func_about.png"), (t_hidden, "func_hidden.png"),
         (t_power, "func_shutdown.png"), (t_reset, "func_reset.png"),
         (t_chip,  "func_firmware.png")]

# -------------------------------------------------------------------- colour
def accent(im):
    """The photograph's characteristic colour, as a hue and a saturation.

    A plain average is useless here: opposite hues cancel and everything comes
    out grey. So the hues are averaged as points on a circle, weighted by how
    colourful and how bright each pixel is, which lets a small bright sky decide
    the answer over a large dark dune -- which is what the eye does too."""
    small = im.convert("RGB").resize((240, 135), Image.LANCZOS)
    raw = small.tobytes()
    x = y = weight = sat = 0.0
    for i in range(0, len(raw), 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        w = (s ** 1.5) * v
        if w <= 0:
            continue
        a = h * 2 * math.pi
        x += math.cos(a) * w
        y += math.sin(a) * w
        weight += w
        sat += s * w
    if weight < 1e-6:
        return 0.0, 0.0
    return (math.atan2(y, x) % (2 * math.pi)) / (2 * math.pi), sat / weight


def shades(im, strength=1.0):
    """Every colour in the theme, drawn from the photograph.

    One hue runs through all of it -- the panel, the logos, the names, the tool
    glyphs, the dots of the spinner -- at different saturations and lightnesses,
    so nothing on the screen is a colour the picture does not contain. At
    strength 0 these are the plain neutrals the theme used before."""
    NEUTRAL = {"plate": (214, 226, 248), "dark": (30, 34, 44), "light": (255, 255, 255),
               "glyph": (232, 238, 250), "text": (160, 160, 160)}
    if strength <= 0:
        return NEUTRAL
    h, s = accent(im)
    def hsv(sf, cap, v):
        return tuple(int(x * 255) for x in colorsys.hsv_to_rgb(h, min(s * sf, cap), v))
    def mix(a, b, k):
        return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))
    k = min(1.0, strength)
    return {
        "plate": mix(NEUTRAL["plate"], hsv(0.16, 0.16, 0.93), k),
        "dark":  mix(NEUTRAL["dark"],  hsv(0.85, 0.60, 0.22), k),
        "light": mix(NEUTRAL["light"], hsv(0.30, 0.22, 0.90), k),
        "glyph": mix(NEUTRAL["glyph"], hsv(0.30, 0.22, 0.90), k),
        "text":  mix(NEUTRAL["text"],  hsv(0.30, 0.22, 0.63), k),
    }


def duotone(img, dark, light, strength):
    """Re-lay a logo along a ramp between two colours, keeping its shape.

    Not a wash of colour over the top: the logo's own lightness picks the point
    on the ramp, so the shape and its internal contrast survive while the hue
    becomes the photograph's. Strength mixes it back with the original, so 0
    leaves Windows blue and Ubuntu orange exactly as they are."""
    if strength <= 0:
        return img
    r, g, b, a = img.split()
    rgb = Image.merge("RGB", (r, g, b))
    lum = rgb.convert("L")
    ramp = Image.merge("RGB", [
        lum.point([int(dark[c] + (light[c] - dark[c]) * i / 255) for i in range(256)])
        for c in range(3)])
    out = Image.blend(rgb, ramp, min(1.0, strength))
    out.putalpha(a)
    return out


# -------------------------------------------------------------------- glass
def plate(s, fill=None):
    """A frosted panel that does not know what is behind it.

    It cannot blur what is behind it, since it does not know where it will be
    drawn. That is why the photograph itself is softened instead — see detail()
    — leaving this a plain translucent panel with no compensation of any kind."""
    p = Image.new("RGBA", (s * SS, s * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(p); r = int(s * SS * .19)
    d.rounded_rectangle([0, 0, s*SS-1, s*SS-1], radius=r,
                        fill=tuple(fill or (214, 226, 248)) + (GLASS_A,))
    g = Image.new("L", (1, s * SS))
    g.putdata([int(VEIL_A * (1 - i / (s * SS))) for i in range(s * SS)])   # raking light
    veil = Image.new("RGBA", (s*SS, s*SS), (255, 255, 255, 255))
    veil.putalpha(g.resize((s*SS, s*SS)))
    m = Image.new("L", (s*SS, s*SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, s*SS-1, s*SS-1], radius=r, fill=255)
    p.alpha_composite(Image.composite(veil, Image.new("RGBA", (s*SS, s*SS), (0,0,0,0)), m))
    ImageDraw.Draw(p).rounded_rectangle([3, 3, s*SS-4, s*SS-4], radius=r,
                                        outline=(255, 255, 255, 150), width=5 * SS)
    p = p.resize((s, s), Image.LANCZOS)
    a = p.split()[3]
    f = Image.new("L", (1, s)); f.putdata([int(255 * (1 - .28 * i / s)) for i in range(s)])
    p.putalpha(Image.composite(a, Image.new("L", (s, s), 0), f.resize((s, s))))
    return p


def frost_mask():
    """The stencil that tells rEFInd where the glass is.

    Not a picture of the panel: its alpha is the panel's *shape*, at full
    strength. Blending a blur in proportion to a translucent panel's own alpha
    would leave the background a quarter blurred, which reads as a slightly soft
    photograph rather than as glass. Glass scatters everything that passes
    through it, and only then tints it -- so the tint belongs to the compositing
    of the icon that follows, and all that is asked of the stencil is the shape."""
    m = Image.new("RGBA", (BIG * SS, BIG * SS), (0, 0, 0, 0))
    ImageDraw.Draw(m).rounded_rectangle(
        [PLATE_X * SS, PLATE_Y * SS, (PLATE_X + PLATE) * SS - 1, (PLATE_Y + PLATE) * SS - 1],
        radius=int(PLATE * SS * .19), fill=(255, 255, 255, 255))
    return m.resize((BIG, BIG), Image.LANCZOS)


def apply_frost(canvas, mask, x, y, radius):
    """Blur behind the glass, as the patched rEFInd does at draw time.

    rEFInd runs two box passes per axis; two boxes of width 2r+1 have variance
    2*((2r+1)**2 - 1)/12, so a Gaussian of this sigma is the same blur, and the
    preview shows what the machine will actually draw."""
    if radius <= 0:
        return
    sigma = math.sqrt(2 * ((2 * radius + 1) ** 2 - 1) / 12)
    box = (x, y, x + mask.width, y + mask.height)
    region = canvas.crop(box)
    canvas.paste(Image.composite(region.filter(ImageFilter.GaussianBlur(sigma)),
                                 region, mask.split()[3]), box)


def make_icon(plate_img, name, drawer=None, stock=None, tone=None, label=(255, 255, 255)):
    """A self-contained entry: frosted plate, logo, and the name underneath."""
    t = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    t.alpha_composite(plate_img, (PLATE_X, PLATE_Y))
    inner = (aa(LOGO, drawer) if drawer else
             Image.open(stock).convert("RGBA").resize((LOGO, LOGO), Image.LANCZOS))
    if tone:
        inner = duotone(inner, tone[0], tone[1], tone[2])
    t.alpha_composite(inner, ((BIG - LOGO) // 2, PLATE_Y + (PLATE - LOGO) // 2))
    if name:
        d = ImageDraw.Draw(t)
        f = ImageFont.truetype(FONT_BOLD, NAME_SIZE)
        bb = d.textbbox((0, 0), name, font=f)
        while bb[2] - bb[0] > BIG - 20 and f.size > 28:      # long names shrink to fit
            f = ImageFont.truetype(FONT_BOLD, f.size - 4)
            bb = d.textbbox((0, 0), name, font=f)
        d.text((BIG // 2 - (bb[2] - bb[0]) // 2, NAME_Y), name, font=f, fill=tuple(label))
    return t

# ------------------------------------------------------------------ picture
def fit(path):
    """Centre-crop to 16:9 and scale to exactly 3840x2160."""
    im = Image.open(path).convert("RGB"); w, h = im.size
    if w / h > W / H:
        nw = int(h * W / H); im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w * H / W); im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return im.resize((W, H), Image.LANCZOS)

def luminance(im):
    return ImageStat.Stat(im.crop(BOX).convert("L")).mean[0]

def detail(im):
    """High-frequency energy in the strip the plates sit on: how much drawing
    would still be legible through the glass.

    This is what decides --blur auto. The plate cannot blur what is behind it —
    it does not know where rEFInd will draw it — and raising its opacity only
    fades detail rather than removing it. Softening the whole photograph is the
    one treatment that is correct at every position, so it is applied only as
    much as the photograph actually needs."""
    z = im.crop(BOX).convert("L")
    return ImageStat.Stat(ImageChops.difference(z, z.filter(ImageFilter.GaussianBlur(6)))).mean[0]

def auto_blur(im):
    for r in BLUR_STEPS:
        if detail(im if r == 0 else im.filter(ImageFilter.GaussianBlur(r))) <= TARGET_DETAIL:
            return r
    return BLUR_STEPS[-1]

# --------------------------------------------------------------------- main
def build(background, darken, out, preview_path=None, quiet=False, blur="auto", tint=100):
    global GR
    say = (lambda *a: None) if quiet else print
    os.makedirs(os.path.join(out, "icons"), exist_ok=True)
    say(f"  geometry   TILE={TILE}  up to {MAXVIS} entries without scrolling")
    assert MAXVIS >= 2, "big_icon_size too large: rEFInd would scroll the OS row"

    # The photograph is read before anything is drawn, because everything drawn
    # takes its colour from it.
    bg = fit(background)
    tint = 0 if str(tint).lower() in ("off", "false", "no", "none") else int(tint)
    tint = max(0, min(100, tint))
    C = shades(bg, tint / 100.0)
    GR = tuple(C["glyph"]) + (255,)
    if tint:
        h, sat = accent(bg)
        say(f"  colour     matched to the photograph: hue {h*360:.0f}\u00b0, "
            f"saturation {sat*100:.0f}%, at {tint}%")
    else:
        say("  colour     original: Windows blue, Ubuntu orange, white labels")

    # font: the glyphs are drawn INVERTED. libeg/text.c does 255-x on dark
    # backgrounds, so what is written here is the complement of what appears.
    f = ImageFont.truetype(FONT_MONO, 44); asc, desc = f.getmetrics()
    cw, ch = math.ceil(f.getlength("M")), asc + desc
    ink = tuple(255 - c for c in C["text"])
    fi = Image.new("RGBA", (cw * 96, ch), (0, 0, 0, 0)); d = ImageDraw.Draw(fi)
    for i in range(95):
        d.text((i * cw, 0), chr(32 + i), font=f, fill=ink + (255,))
    d.rectangle([95*cw+2, 2, 96*cw-3, ch-3], outline=ink + (255,), width=2)
    fi.save(f"{out}/font.png")
    say(f"  font       cell {cw}x{ch}, written {ink} -> {tuple(C['text'])} on screen")

    tone = (C["dark"], C["light"], tint / 100.0)
    pl = plate(PLATE, C["plate"])
    for stem, name, drawer in (("os_win8", "Windows", logo_windows),
                               ("os_win",  "Windows", logo_windows),
                               ("os_ubuntu", "Ubuntu", logo_ubuntu)):
        make_icon(pl, name, drawer=drawer, tone=tone,
                  label=C["light"]).save(f"{out}/icons/{stem}.png")
    hand = {"os_win8", "os_win", "os_ubuntu"}
    n = len(hand)
    for src in sorted(glob.glob(os.path.join(HERE, "stock-icons", "os_*.png"))):
        stem = os.path.splitext(os.path.basename(src))[0]
        if stem in hand:
            continue
        make_icon(pl, NAMES.get(stem[3:], ""), stock=src, tone=tone,
                  label=C["light"]).save(f"{out}/icons/{stem}.png")
        n += 1
    for fn, name in TOOLS:
        aa(192, fn).save(f"{out}/icons/{name}")
    say(f"  icons      {n} operating systems themed, each carrying its own name")

    # the dot the spinner is made of, for rEFInd and for Plymouth
    dot = Image.new("RGBA", (DOT_PX * SS, DOT_PX * SS), (0, 0, 0, 0))
    ImageDraw.Draw(dot).ellipse([0, 0, DOT_PX*SS-1, DOT_PX*SS-1], fill=tuple(C["light"]) + (255,))
    dot.resize((DOT_PX, DOT_PX), Image.LANCZOS).save(f"{out}/dot.png")

    if str(blur).lower() == "auto":
        blur = auto_blur(bg)
        say(f"  blur       auto -> radius {blur}px  (detail {detail(bg):.2f}, target {TARGET_DETAIL})")
    blur = int(blur)
    if blur:
        bg = bg.filter(ImageFilter.GaussianBlur(blur))
    say(f"  blur       radius {blur}px   detail behind the plates -> {detail(bg):.2f}")
    lum_raw = luminance(bg)
    if str(darken).lower() == "auto":
        d_ = 0 if lum_raw <= TARGET_LUM else round((1 - TARGET_LUM / lum_raw) * 100)
        darken = 0 if d_ < 5 else min(100, d_)
        say(f"  darken     auto -> {darken}%  (targeting luminance {TARGET_LUM:.0f})")
    darken = int(darken)
    if darken:
        bg = ImageEnhance.Brightness(bg).enhance(1 - darken / 100)
    lum = luminance(bg)
    say(f"  darken     {darken}%   luminance behind the tiles {lum_raw:.0f} -> {lum:.0f}")
    if lum > 60:
        say(f"  NOTE       bright; the plates and the names will have little contrast."
            f" Try --darken {min(100, round((1 - TARGET_LUM / lum_raw) * 100))}.")
    bg.save(f"{out}/background.png", "PNG", optimize=True)

    # the highlight has to frame the plate, which sits high inside the icon
    px, py = ICON_OFF + PLATE_X, ICON_OFF + PLATE_Y
    sel = Image.new("RGBA", (TILE * SS, TILE * SS), (0, 0, 0, 0)); sd = ImageDraw.Draw(sel)
    box = [px*SS, py*SS, (px+PLATE)*SS, (py+PLATE)*SS]
    sd.rounded_rectangle(box, radius=int(PLATE*SS*.19), fill=tuple(C["light"]) + (34,))
    sd.rounded_rectangle(box, radius=int(PLATE*SS*.19), outline=tuple(C["light"]) + (215,), width=5*SS)
    sel.resize((TILE, TILE), Image.LANCZOS).save(f"{out}/selection_big.png")
    ss = Image.new("RGBA", (TILE1*SS, TILE1*SS), (0, 0, 0, 0)); s2 = ImageDraw.Draw(ss)
    s2.rounded_rectangle([2, 2, TILE1*SS-3, TILE1*SS-3], radius=int(TILE1*SS*.24), fill=tuple(C["light"]) + (40,))
    s2.rounded_rectangle([2, 2, TILE1*SS-3, TILE1*SS-3], radius=int(TILE1*SS*.24), outline=tuple(C["light"]) + (190,), width=3*SS)
    ss.resize((TILE1, TILE1), Image.LANCZOS).save(f"{out}/selection_small.png")
    frost_mask().save(f"{out}/frost_big.png")

    if preview_path:
        preview(out, preview_path, ["os_win8", "os_ubuntu"], "Boot Windows")
        say(f"  preview    {preview_path}")
    return lum


def preview(assets, dst, icons, label, scale=None):
    """Render the menu exactly as rEFInd lays it out, for any number of entries."""
    n = len(icons)
    r0x = (W + XSP - (TILE + XSP) * n) // 2
    r1y = R0Y + TILE + YSP
    r1x = (W + XSP - (TILE1 + XSP) * 5) // 2
    txty = r1y + TILE1 + YSP
    c = Image.open(f"{assets}/background.png").convert("RGBA")
    # rEFInd frosts the cropped background before it lays the highlight and the
    # icon over it, so do it in that order here too.
    mask = Image.open(f"{assets}/frost_big.png").convert("RGBA")
    for i in range(n):
        apply_frost(c, mask, r0x + i * (TILE + XSP) + ICON_OFF, R0Y + ICON_OFF, FROST)
    c.alpha_composite(Image.open(f"{assets}/selection_big.png").convert("RGBA"), (r0x, R0Y))
    for i, name in enumerate(icons):
        ic = Image.open(f"{assets}/icons/{name}.png").convert("RGBA").resize((BIG, BIG), Image.LANCZOS)
        c.alpha_composite(ic, (r0x + i * (TILE + XSP) + ICON_OFF, R0Y + ICON_OFF))
    o1 = (TILE1 - SMALL) // 2
    for i, (_, fn) in enumerate(TOOLS):
        t = Image.open(f"{assets}/icons/{fn}").convert("RGBA").resize((SMALL, SMALL), Image.LANCZOS)
        c.alpha_composite(t, (r1x + i * (TILE1 + XSP) + o1, r1y + o1))
    if label:
        f = ImageFont.truetype(FONT_MONO, 44); a_, d_ = f.getmetrics()
        cw, ch = math.ceil(f.getlength("M")), a_ + d_
        cell = Image.new("RGBA", (cw * 96, ch), (255, 255, 255, 0)); dd = ImageDraw.Draw(cell)
        for i in range(95):
            dd.text((i * cw, 0), chr(32 + i), font=f, fill=(160,) * 3 + (255,))
        x = (W - cw * len(label)) // 2
        for ch_ in label:
            i = ord(ch_) - 32
            if 0 <= i < 95:
                c.alpha_composite(cell.crop((i*cw, 0, (i+1)*cw, ch)), (x, txty))
            x += cw
    img = c.convert("RGB")
    if scale:
        img = img.resize(scale, Image.LANCZOS)
    img.save(dst)


if __name__ == "__main__":
    cfg = {}
    lib = os.path.join(HERE, "library", "library.json")
    if os.path.exists(lib):
        cfg = json.load(open(lib))
    ap = argparse.ArgumentParser(description="Build the rEFInd theme assets.")
    ap.add_argument("--background", default=None, help="photo to use (default: library default)")
    ap.add_argument("--darken", default=str(cfg.get("default_darken", 24)),
                    help="0 = untouched, 100 = black, or 'auto' (default: %(default)s)")
    ap.add_argument("--blur", default=str(cfg.get("default_blur", "auto")),
                    help="0 = sharp photo, or a radius in px, or 'auto' (default: %(default)s)")
    ap.add_argument("--tint", default=str(cfg.get("default_tint", 100)),
                    help="0-100, or 'off': how far the theme's colours are pulled "
                         "towards the photograph's own (default: %(default)s)")
    ap.add_argument("--out", default=os.path.join(HERE, "assets"))
    ap.add_argument("--preview", default=None, help="also write a full-screen preview here")
    a = ap.parse_args()
    if str(a.darken).lower() != "auto" and not (a.darken.isdigit() and 0 <= int(a.darken) <= 100):
        sys.exit("--darken must be 0-100 or 'auto'")
    if str(a.blur).lower() != "auto" and not (a.blur.isdigit() and 0 <= int(a.blur) <= 60):
        sys.exit("--blur must be 0-60 or 'auto'")
    if str(a.tint).lower() not in ("off", "false", "no", "none") and \
       not (str(a.tint).isdigit() and 0 <= int(a.tint) <= 100):
        sys.exit("--tint must be 0-100 or 'off'")
    bg = a.background or os.path.join(HERE, "library",
         next(s["file"] for s in cfg["backgrounds"] if s["slug"] == cfg["default"]).split("/")[-1])
    print(f"  background {bg}")
    build(bg, a.darken, a.out, a.preview, blur=a.blur, tint=a.tint)
