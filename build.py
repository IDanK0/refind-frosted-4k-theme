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
GLASS_A   = 24                    # how much of the panel's own tint there is
VEIL_A    = 10                    # the raking light across the top of it
RIM_A     = 205                   # the lit edge of the pane
HAIR_A    = 210                   # a bright hairline just inside the top edge
SWEEP_A   = 34                    # a reflection lying diagonally across the pane
SWEEP_AT, SWEEP_W = 0.34, 0.22    # where it falls, and how broad it is
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
SHADOW_BLUR, SHADOW_DROP, SHADOW_A = 26, 14, 130   # only visible on a light photograph
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
    colourful and how bright each pixel is.

    Brightness has to count for a great deal -- v cubed, not v. With v alone, a
    vast dark dune drags the circular mean away from the small bright sky that
    the eye actually reads the picture by: on the default photograph that landed
    on 341 degrees, a pink, when the sky is at 13 and the picture is plainly
    warm. Cubed, it comes out at 17."""
    small = im.convert("RGB").resize((240, 135), Image.LANCZOS)
    raw = small.tobytes()
    x = y = weight = sat = 0.0
    for i in range(0, len(raw), 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        w = (s ** 1.5) * (v ** 3)
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


# How far each part of the theme is pushed towards the photograph's hue, as
# (factor, floor, ceiling, lightness) applied to the picture's own saturation.
# The floor matters: scaling saturation purely in proportion leaves a muted
# photograph with a theme indistinguishable from grey, which is not what asking
# for the picture's colour means. The ceiling stops a vivid one shouting.
TONE = {
    "plate": (0.18, 0.05, 0.12, 0.92),   # the panel's own tint
    "dark":  (0.30, 0.08, 0.20, 0.20),   # unused since the ramp took over
    "light": (0.22, 0.06, 0.14, 0.88),   # the border, the names, the tool glyphs
    "glyph": (0.22, 0.06, 0.14, 0.88),
    "text":  (0.22, 0.06, 0.14, 0.63),   # the line rEFInd writes at the bottom
}
# These are deliberately near-neutral. The point is a warm grey that belongs to
# the photograph, not a coloured theme: at the default photograph's 43%
# saturation they come out around 0.09, which is a tint you read as warmth
# rather than as a colour. What makes it look like more than that is the ramp
# below, which stops a logo turning grey in its own middle.
# The ramp a logo is laid along: (chroma at the peak, how broad the peak is,
# lightness at the dark end, at the light end). The chroma has to peak in the
# middle rather than run straight from a dark colour to a light one, because a
# straight line between two colours passes through their average -- which is
# nearly grey -- and a logo sits in the middle of its own range, exactly where
# that happens. The Windows blue lands at 0.60 of the way up; a straight ramp
# gives it a saturation of 0.17, this gives it 0.43.
LOGO_RAMP  = (0.28, 1.4, 0.18, 0.86)
GREY_PHOTO = 0.04       # below this the picture has no colour to lend


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
    if s < GREY_PHOTO:
        return NEUTRAL
    k = min(1.0, strength)
    def mix(a, b):
        return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))
    out = {}
    for part, (sf, lo, hi, v) in TONE.items():
        c = colorsys.hsv_to_rgb(h, max(lo, min(s * sf, hi)), v)
        out[part] = mix(NEUTRAL[part], tuple(int(x * 255) for x in c))
    peak, bulge, v_dark, v_light = LOGO_RAMP
    out["ramp"] = ramp(h, max(0.08, min(s * 0.28, peak)), bulge, v_dark, v_light)
    return out


def ramp(h, peak, bulge, v_dark, v_light):
    """256 colours from dark to light in one hue, chroma fullest in the middle."""
    table = []
    for i in range(256):
        t = i / 255
        sat = peak * (1 - abs(2 * t - 1) ** bulge)
        val = v_dark + (v_light - v_dark) * t
        table.append(tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, sat, val)))
    return table


def duotone(img, table, strength):
    """Re-lay a logo along a ramp, keeping its shape.

    Not a wash of colour over the top: the logo's own lightness picks the point
    on the ramp, so the shape and its internal contrast survive while the hue
    becomes the photograph's. Strength mixes it back with the original, so 0
    leaves Windows blue and Ubuntu orange exactly as they are."""
    if strength <= 0 or table is None:
        return img
    r, g, b, a = img.split()
    rgb = Image.merge("RGB", (r, g, b))
    lum = rgb.convert("L")
    laid = Image.merge("RGB", [lum.point([table[i][c] for i in range(256)]) for c in range(3)])
    out = Image.blend(rgb, laid, min(1.0, strength))
    out.putalpha(a)
    return out


# -------------------------------------------------------------------- glass
def plate_shadow(blur=SHADOW_BLUR, drop=SHADOW_DROP, alpha=SHADOW_A):
    """What lifts the panel off the photograph.

    A blurred rounded rectangle is doing more work here than the blur behind the
    glass is. On a smooth photograph there is nothing behind the panel to soften,
    so the frost has nothing to show and the panel reads as a flat translucent
    rectangle no matter how strong it is. A shadow does not care what is behind
    it: it says the panel is a separate thing, above the picture, which is the
    cue the eye is actually reading.

    It is punched out under the panel itself -- you do not see a thing's own
    shadow through the front of it -- and it lives inside the icon, so it travels
    with the entry the way everything else does."""
    r = int(PLATE * .19)
    sh = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [PLATE_X, PLATE_Y + drop, PLATE_X + PLATE - 1, PLATE_Y + PLATE + drop - 1],
        radius=r, fill=(0, 0, 0, alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    hole = Image.new("L", (BIG, BIG), 255)
    ImageDraw.Draw(hole).rounded_rectangle(
        [PLATE_X, PLATE_Y, PLATE_X + PLATE - 1, PLATE_Y + PLATE - 1], radius=r, fill=0)
    sh.putalpha(ImageChops.multiply(sh.split()[3], hole))
    return sh


def plate(s, fill=None, light=(255, 255, 255)):
    """A pane of frosted glass.

    The blur behind it is drawn by rEFInd at draw time -- see the patch -- so
    what is built here is only the pane itself: its tint, the light raking across
    it, and the rim. The rim is not uniform: glass catches light along one edge
    and goes nearly dark along the opposite one, and a rim of the same brightness
    all the way round is the difference between a pane and a rounded rectangle."""
    p = Image.new("RGBA", (s * SS, s * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(p); r = int(s * SS * .19)
    d.rounded_rectangle([0, 0, s*SS-1, s*SS-1], radius=r,
                        fill=tuple(fill or (214, 226, 248)) + (GLASS_A,))
    g = Image.new("L", (1, s * SS))
    g.putdata([int(VEIL_A * (1 - i / (s * SS))) for i in range(s * SS)])   # raking light
    veil = Image.new("RGBA", (s*SS, s*SS), tuple(light) + (255,))
    veil.putalpha(g.resize((s*SS, s*SS)))
    m = Image.new("L", (s*SS, s*SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, s*SS-1, s*SS-1], radius=r, fill=255)
    p.alpha_composite(Image.composite(veil, Image.new("RGBA", (s*SS, s*SS), (0,0,0,0)), m))

    # A reflection lying across the pane. This is the one that does the work: a
    # dark photograph gives the frost nothing to blur and a shadow nothing to
    # darken, so neither of them says "glass". A reflection does not depend on
    # what is behind at all -- it is light on the surface, and it is what the eye
    # reads a glossy pane by. Its value depends only on x + y, so it is built
    # from a single line rather than pixel by pixel.
    n = s * SS
    line = Image.new("L", (2 * n, 1))
    line.putdata([int(SWEEP_A * max(0.0, 1 - abs(t / (2 * n) - SWEEP_AT) / SWEEP_W) ** 2)
                  for t in range(2 * n)])
    diag = Image.new("L", (n, n))
    for y in range(n):
        diag.paste(line.crop((y, 0, y + n, 1)), (0, y))
    sweep = Image.new("RGBA", (n, n), tuple(light) + (255,))
    sweep.putalpha(diag)
    p.alpha_composite(Image.composite(sweep, Image.new("RGBA", (n, n), (0, 0, 0, 0)), m))

    # a hairline of light just inside the top edge, the way a bevel catches it
    hair = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(hair).rounded_rectangle([5*SS, 5*SS, n-1-5*SS, n-1-5*SS], radius=r,
                                           outline=(255, 255, 255, 255), width=2 * SS)
    ramp = Image.new("L", (1, n))
    ramp.putdata([int(HAIR_A * max(0.0, 1 - i / (n * 0.45))) for i in range(n)])
    hair.putalpha(ImageChops.multiply(hair.split()[3], ramp.resize((n, n))))
    p.alpha_composite(hair)

    rim = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle([3, 3, n-4, n-4], radius=r,
                                          outline=tuple(light) + (RIM_A,), width=5 * SS)
    p.alpha_composite(rim)

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
    t.alpha_composite(plate_shadow())
    t.alpha_composite(plate_img, (PLATE_X, PLATE_Y))
    inner = (aa(LOGO, drawer) if drawer else
             Image.open(stock).convert("RGBA").resize((LOGO, LOGO), Image.LANCZOS))
    if tone:
        inner = duotone(inner, tone[0], tone[1])
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

    tone = (C.get("ramp"), tint / 100.0)
    pl = plate(PLATE, C["plate"], C["light"])
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
        # Use the font that was generated, not a fresh one drawn here. Redrawing
        # it is how the preview came to show a grey line while the menu drew a
        # tinted one -- two pieces of code choosing a colour, only one of which
        # rEFInd ever sees. This reads the atlas and applies rEFInd's own rule
        # from libeg/text.c: on a background darker than 128 the glyphs are
        # inverted, r, g and b but not alpha.
        atlas = Image.open(f"{assets}/font.png").convert("RGBA")
        cw, ch = atlas.width // 96, atlas.height
        band = c.crop((0, txty, W, min(H, txty + ch))).convert("L")
        if ImageStat.Stat(band).mean[0] < 128:
            r, g, b, a = atlas.split()
            atlas = Image.merge("RGBA", (ImageChops.invert(r), ImageChops.invert(g),
                                         ImageChops.invert(b), a))
        x = (W - cw * len(label)) // 2
        for ch_ in label:
            i = ord(ch_) - 32
            if 0 <= i < 95:
                c.alpha_composite(atlas.crop((i*cw, 0, (i+1)*cw, ch)), (x, txty))
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
