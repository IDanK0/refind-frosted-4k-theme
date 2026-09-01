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
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps, ImageStat

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- geometry
#
# Every measurement here is stated at 3840x2160 and scaled to the screen the
# theme is actually being built for. It used to be stated at 3840x2160 and used
# at 3840x2160, full stop, which is fine on a 4K monitor and wrong everywhere
# else: a 549-pixel icon on a 1080-line screen is half the height of the screen,
# and rEFInd would fit two of them across it and scroll.
#
# XSP and YSP do not scale. They are TILE_XSPACING and TILE_YSPACING, #define'd
# in menu.c as 8 and 16, and the bootloader uses those numbers whatever the
# screen is.
MASTER_W, MASTER_H = 3840, 2160
W, H = MASTER_W, MASTER_H
XSP, YSP = 8, 16          # TILE_XSPACING / TILE_YSPACING, #define'd in menu.c
SS = 4                    # supersampling for the vector artwork
BIG, SMALL = 549, 48

# inside the BIG icon canvas
FROST     = 14                    # frost_radius in refind.conf; the preview matches it
GLASS_A   = 24                    # how much of the panel's own tint there is
VEIL_A    = 10                    # the raking light across the top of it
RIM_A     = 205                   # the lit edge of the pane
HAIR_A    = 210                   # a bright hairline just inside the top edge
SWEEP_A   = 0                     # a reflection lying diagonally across the pane;
                                  # 0 is off, and off is the default -- it reads as a
                                  # streak more than as glass. The rim and the hairline
                                  # carry the surface on their own.
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
DOT_PX    = 13                    # one dot of the spinner, at 3840x2160
SHADOW_BLUR, SHADOW_DROP, SHADOW_A = 34, 10, 58    # only visible on a light photograph

# Everything that follows is derived from the above, and has to be recomputed
# when the size changes. The module-level values are the 4K ones, so anything
# that imports build.py without asking for a size gets exactly what it always
# got.
_AT_4K = dict(BIG=549, SMALL=48, PLATE=340, PLATE_Y=64, LOGO=218, NAME_SIZE=56,
              DOT_PX=13, FROST=14, SHADOW_BLUR=34, SHADOW_DROP=10)


def configure(width, height):
    """Set the geometry for a screen of this size. Call before anything else."""
    global W, H, BIG, SMALL, PLATE, PLATE_Y, LOGO, NAME_SIZE, DOT_PX, FROST
    global SHADOW_BLUR, SHADOW_DROP, TILE, TILE1, R0Y, MAXVIS, NAME_Y
    global ICON_OFF, PLATE_X, BOX

    W, H = int(width), int(height)
    k = H / MASTER_H
    for name, at4k in _AT_4K.items():
        globals()[name] = max(1, int(round(at4k * k)))
    _derive()


def _derive():
    global TILE, TILE1, R0Y, MAXVIS, NAME_Y, ICON_OFF, PLATE_X, BOX
    TILE   = (BIG * 9) // 8           # TileSizes[0] = big_icon_size * 9/8
    TILE1  = (SMALL * 4) // 3         # TileSizes[1] = small_icon_size * 4/3
    R0Y    = (H // 2) - TILE // 2     # the OS row is always vertically centred
    MAXVIS = W // (TILE + XSP) - 1    # entries rEFInd will show without scrolling
    NAME_Y   = PLATE_Y + PLATE + max(1, round(22 * H / MASTER_H))
    ICON_OFF = (TILE - BIG) // 2      # icon is centred in the tile
    PLATE_X  = (BIG - PLATE) // 2
    # the strip sampled to judge how bright a photograph is, as a fraction of
    # the screen rather than as four numbers that only mean anything at 4K
    BOX = (int(W * 1299 / MASTER_W), int(H * 850 / MASTER_H),
           int(W * 2541 / MASTER_W), int(H * 1400 / MASTER_H))


_derive()

# Pillow refuses to decode anything past about 89 megapixels, on the theory that
# a file claiming to be enormous is probably an attack. Here the file is one the
# person running this chose off their own disk, and a 100-megapixel panorama is
# a photograph, not an attack -- so the ceiling is raised, once, deliberately,
# rather than left to fail with a traceback about decompression bombs. It is
# still a ceiling: half a gigapixel would exhaust the machine.
Image.MAX_IMAGE_PIXELS = 512_000_000


def _font(*names):
    """Find a font file by name, wherever this distribution keeps its fonts.

    Debian puts DejaVu under truetype/dejavu, Fedora under dejavu-sans-fonts,
    Arch under TTF, and asking fontconfig works when none of those do. Hard-coding
    the Debian path made the theme buildable on Debian and nowhere else, which is
    the opposite of the point: the splash has to be installable on whatever
    system is being booted."""
    import subprocess
    roots = ("/usr/share/fonts", "/usr/local/share/fonts",
             os.path.expanduser("~/.local/share/fonts"))
    for name in names:
        for root in roots:
            for path in glob.glob(os.path.join(root, "**", name), recursive=True):
                return path
    # fc-match never says no. Ask it for a font that is not installed and it
    # hands back whatever it thinks is closest, which on a minimal system can be
    # a CJK face -- and then every label in the boot menu is drawn in it without
    # a word of complaint. So check that what came back is actually the family
    # that was asked for.
    for name in names:
        want = os.path.splitext(name)[0]
        family = want.replace("DejaVu", "DejaVu ").split("-")[0].strip()
        try:
            out = subprocess.run(["fc-match", "-f", "%{file}\t%{family}", want],
                                 capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode != 0 or "\t" not in out.stdout:
            continue
        path, _, got = out.stdout.partition("\t")
        if os.path.exists(path.strip()) and "dejavu" in got.strip().lower():
            return path.strip()
    raise SystemExit(
        "no DejaVu font found. Install it:\n"
        "  Debian/Ubuntu   sudo apt install fonts-dejavu-core\n"
        "  Fedora/RHEL     sudo dnf install dejavu-sans-fonts dejavu-sans-mono-fonts\n"
        "  Arch            sudo pacman -S ttf-dejavu\n"
        "  openSUSE        sudo zypper install dejavu-fonts\n"
        "  Alpine          sudo apk add font-dejavu")


FONT_MONO = _font("DejaVuSansMono.ttf")
FONT_BOLD = _font("DejaVuSans-Bold.ttf")
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
def t_settings(d, S):
    C = S / 2; R = S * .30; T = int(S * .10)
    d.ellipse([C-R, C-R, C+R, C+R], outline=GR, width=T)
    d.ellipse([C-S*.085, C-S*.085, C+S*.085, C+S*.085], fill=GR)
    for i in range(8):
        a = math.radians(i * 45)
        x, y = C + math.cos(a) * (R + S*.075), C + math.sin(a) * (R + S*.075)
        d.ellipse([x-S*.055, y-S*.055, x+S*.055, y+S*.055], fill=GR)

def t_chip(d, S):
    a, b = S * .26, S * .74
    d.rounded_rectangle([a,a,b,b], radius=S*.07, outline=GR, width=int(S*.07))
    d.rounded_rectangle([S*.42,S*.42,S*.58,S*.58], radius=S*.03, fill=GR)
    for t in (.38, .5, .62):
        d.rectangle([S*t-S*.022, S*.10, S*t+S*.022, a], fill=GR)
        d.rectangle([S*t-S*.022, b, S*t+S*.022, S*.90], fill=GR)
        d.rectangle([S*.10, S*t-S*.022, a, S*t+S*.022], fill=GR)
        d.rectangle([b, S*t-S*.022, S*.90, S*t+S*.022], fill=GR)
TOOLS = [(t_settings, "func_settings.png"), (t_about, "func_about.png"), (t_hidden, "func_hidden.png"),
         (t_power, "func_shutdown.png"), (t_reset, "func_reset.png"),
         (t_chip,  "func_firmware.png")]

# -------------------------------------------------------------------- colour
def isqrt(n):
    """Integer square root, as theme.c has it."""
    if n <= 0:
        return 0
    r, b = 0, 1 << 62
    while b > n:
        b >>= 2
    while b > 0:
        if n >= r + b:
            n -= r + b
            r = (r >> 1) + b
        else:
            r >>= 1
        b >>= 2
    return r


def accent(im):
    """The photograph's colour: a direction away from grey, and a mean chroma.

    A transcription of SampleAccent() in refind/theme.c, integer for integer, so
    that the preview and the machine cannot disagree about a colour. When these
    were two different formulations -- HSV here, vectors there -- they drifted 24
    levels apart, which is a preview showing a colour the machine will not draw.

    There is no trigonometry in either. Averaging hues wants a circular mean, and
    a circular mean wants sines; but every colour is a grey plus a departure from
    grey, that departure lives in the plane at right angles to the grey axis, and
    averaging departures IS the circular mean written in linear coordinates.

    Brightness is cubed in the weight, because with brightness counting once a
    vast dark dune outvotes the small bright sky the eye reads the picture by."""
    small = im.convert("RGB")
    raw = small.tobytes()
    w_, h_ = small.size
    step = max(1, (w_ * h_) // 60000)
    ax = ay = az = 0
    weight = chroma_sum = count = 0
    for y in range(h_):
        base = y * w_ * 3
        for x in range(0, w_, step):
            i = base + x * 3
            r, g, b = raw[i], raw[i + 1], raw[i + 2]
            hi = r if r > g else g
            if b > hi: hi = b
            lo = r if r < g else g
            if b < lo: lo = b
            c = hi - lo
            if c < 6 or hi < 8:
                continue
            wt = ((c * c) // 256 + 1) * ((hi * hi * hi) // 65536 + 1)
            mid = (r + g + b) // 3
            dx, dy, dz = r - mid, g - mid, b - mid
            ln = isqrt(dx * dx + dy * dy + dz * dz)
            if ln < 1:
                continue
            ax += (dx * wt) // ln
            ay += (dy * wt) // ln
            az += (dz * wt) // ln
            count += 1
            weight += wt
            chroma_sum += c * wt
    if weight < 1 or count < 1:
        return (0, 0, 0), 0
    ax //= count; ay //= count; az //= count
    ln = isqrt(ax * ax + ay * ay + az * az)
    if ln < 1:
        return (0, 0, 0), 0
    return ((ax * 1024) // ln, (ay * 1024) // ln, (az * 1024) // ln), chroma_sum // weight


def accent_hue(direction):
    """Only so it can be said out loud: the direction as an angle, in degrees."""
    dx, dy, dz = direction
    return math.degrees(math.atan2(math.sqrt(3) * (dy - dz), 2 * dx - dy - dz)) % 360


# The colours the theme is drawn in when it is NOT taking them from a photograph.
NEUTRAL = {"plate": (214, 226, 248), "dark": (30, 34, 44), "light": (255, 255, 255),
           "glyph": (232, 238, 250), "text": (160, 160, 160)}

# The ramp a logo is laid along, in the units refind/theme.c uses. These must
# match RAMP_DARK, RAMP_LIGHT, CHROMA_FLOOR, CHROMA_CEILING and RAMP_END there.
RAMP_DARK, RAMP_LIGHT = 46, 219
CHROMA_FLOOR, CHROMA_CEILING = 20, 52
RAMP_END = 107          # what the ends keep of the peak chroma, in 255ths.
# Not zero: a duotone whose chroma vanishes at both ends turns everything white
# back into grey, and the white things here -- the names under the icons, the rim
# of the glass, the dots of the spinner -- are most of what carries the colour.


def ramp(direction, chroma):
    """256 colours from dark to light, chroma fullest in the middle.

    BuildRamp() from refind/theme.c, transcribed. A straight line between a dark
    colour and a light one passes through their average, which is close to grey,
    and the middle of the range is exactly where a logo sits -- so a straight
    ramp takes the colour out of the one part anybody looks at."""
    peak = max(CHROMA_FLOOR, min((chroma * 45) // 100, CHROMA_CEILING))
    out = []
    for t in range(256):
        v = RAMP_DARK + ((RAMP_LIGHT - RAMP_DARK) * t) // 255
        u = 255 - abs(2 * t - 255)
        sat = min((u * (510 - u)) // 255, 255)
        sat = RAMP_END + ((255 - RAMP_END) * sat) // 255
        out.append(tuple(max(0, min(255, v + (direction[k] * peak * sat) // (1024 * 255)))
                         for k in range(3)))
    return out


def shades(im, strength=1.0):
    """What the theme is drawn in. The flat colours are the neutrals, because the
    artwork on disk is neutral and rEFInd colours it at boot; the ramp is what
    does the colouring, and it is computed the same way there and here."""
    # A ramp of None means "this photograph has no colour worth taking" -- a
    # black-and-white picture, or a moonlit one. duotone() understands that and
    # leaves the logo alone. What it must never do is leave the key out
    # altogether: three callers index it directly, and a greyscale photograph
    # used to end the build with a KeyError.
    out = dict(NEUTRAL)
    out["ramp"] = None
    if strength <= 0:
        return out
    direction, chroma = accent(im)
    if chroma < 6:
        return out
    out["ramp"] = ramp(direction, chroma)
    return out


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
    im = Image.open(path)
    # A photograph off a phone or a camera is stored in the sensor's orientation
    # with a tag saying which way up it goes. Ignoring the tag installs a
    # wallpaper on its side, and the person who took it will not know why.
    im = ImageOps.exif_transpose(im).convert("RGB")
    w, h = im.size
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
    # What is written to disk is neutral. The colours are worked out by rEFInd
    # at boot from whatever photograph is in use, so that a picture chosen from
    # the boot menu's own settings screen -- or dropped onto the EFI partition
    # from another operating system entirely -- is themed exactly like the ones
    # that shipped. The tint is only used here to render an honest preview of
    # what the machine will draw.
    C = shades(bg, 0.0)
    GR = tuple(C["glyph"]) + (255,)
    direction, chroma = accent(bg)
    say(f"  colour     assets written neutral; rEFInd tints at boot "
        f"(this photo: hue {accent_hue(direction):.0f}\u00b0, chroma {chroma}, at {tint}%)")

    # font: the glyphs are drawn INVERTED. libeg/text.c does 255-x on dark
    # backgrounds, so what is written here is the complement of what appears.
    # 44 point at 3840x2160. rEFInd draws this bitmap at its own cell size
    # whatever the screen is, so a font drawn for 4K is twice the size it should
    # be on a 1080-line screen -- the hints along the bottom would be as tall as
    # the tool icons.
    f = ImageFont.truetype(FONT_MONO, max(8, round(44 * H / MASTER_H)))
    asc, desc = f.getmetrics()
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
    # The Ubuntu release code-names all carry a mascot that exists only as a
    # 128-pixel bitmap, and all of them are labelled "Ubuntu" anyway -- so they
    # get the Ubuntu logo, drawn as vectors, and nothing is lost but the blur.
    drawn = (("os_win8", "Windows", logo_windows),
             ("os_win",  "Windows", logo_windows),
             ("os_ubuntu", "Ubuntu", logo_ubuntu),
             ("os_artful", "Ubuntu", logo_ubuntu),
             ("os_bionic", "Ubuntu", logo_ubuntu),
             ("os_trusty", "Ubuntu", logo_ubuntu),
             ("os_xenial", "Ubuntu", logo_ubuntu),
             ("os_zesty",  "Ubuntu", logo_ubuntu))
    for stem, name, drawer in drawn:
        make_icon(pl, name, drawer=drawer, tone=tone,
                  label=C["light"]).save(f"{out}/icons/{stem}.png")
    hand = {stem for stem, _, _ in drawn}
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

    with open(f"{out}/theme.conf", "w", encoding="utf-16") as fh:
        fh.write("# Defaults written by build.py. The boot menu's settings screen\r\n"
                 "# rewrites this file; delete it to come back here.\r\n"
                 f"background {os.path.basename(background)}\r\n"
                 f"darken {101 if str(darken).lower() == 'auto' else int(darken)}\r\n"
                 f"tint {tint}\r\n"
                 f"frost_radius {FROST}\r\n"
                 "animations true\r\n")

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


def read_tint(assets):
    """What rEFInd will use, read from the file rEFInd reads."""
    # The boot menu writes UTF-16 with a byte-order mark, because that is what a
    # UEFI program writes. A person editing the file from a text editor writes
    # UTF-8. Both have to be readable, or changing one line by hand silently
    # resets the colour.
    try:
        raw = open(f"{assets}/theme.conf", "rb").read()
    except OSError:
        return 100
    for encoding in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
        for line in text.replace("\r", "\n").split("\n"):
            if line.strip().startswith("tint"):
                try:
                    return int(line.split()[1])
                except (ValueError, IndexError):
                    return 100
        return 100
    return 100


def preview(assets, dst, icons, label, scale=None, tint=None):
    """Render the menu exactly as rEFInd lays it out, for any number of entries.

    The artwork on disk is neutral, because rEFInd colours it at boot. So the
    preview colours it too, with the same arithmetic, or it would be a picture of
    a menu nobody will ever see."""
    n = len(icons)
    r0x = (W + XSP - (TILE + XSP) * n) // 2
    r1y = R0Y + TILE + YSP
    r1x = (W + XSP - (TILE1 + XSP) * 5) // 2
    txty = r1y + TILE1 + YSP
    c = Image.open(f"{assets}/background.png").convert("RGBA")
    if tint is None:
        tint = read_tint(assets)
    table = shades(c, 1.0)["ramp"] if tint else None
    def paint(path, size):
        im = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        return duotone(im, table, tint / 100.0) if tint else im

    # rEFInd frosts the cropped background before it lays the highlight and the
    # icon over it, so do it in that order here too.
    mask = Image.open(f"{assets}/frost_big.png").convert("RGBA")
    for i in range(n):
        apply_frost(c, mask, r0x + i * (TILE + XSP) + ICON_OFF, R0Y + ICON_OFF, FROST)
    c.alpha_composite(paint(f"{assets}/selection_big.png", TILE), (r0x, R0Y))
    for i, name in enumerate(icons):
        c.alpha_composite(paint(f"{assets}/icons/{name}.png", BIG),
                          (r0x + i * (TILE + XSP) + ICON_OFF, R0Y + ICON_OFF))
    o1 = (TILE1 - SMALL) // 2
    for i, (_, fn) in enumerate(TOOLS):
        c.alpha_composite(paint(f"{assets}/icons/{fn}", SMALL),
                          (r1x + i * (TILE1 + XSP) + o1, r1y + o1))
    if label:
        # Use the font that was generated, not a fresh one drawn here. Redrawing
        # it is how the preview came to show a grey line while the menu drew a
        # tinted one -- two pieces of code choosing a colour, only one of which
        # rEFInd ever sees. This reads the atlas and applies rEFInd's own rule
        # from libeg/text.c: on a background darker than 128 the glyphs are
        # inverted, r, g and b but not alpha.
        atlas = Image.open(f"{assets}/font.png").convert("RGBA")
        if tint:
            atlas = duotone(atlas, table, tint / 100.0)
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
    ap.add_argument("--size", default=None, metavar="WxH",
                    help="the screen to draw for (default 3840x2160)")
    a = ap.parse_args()
    if a.size:
        try:
            w, h = (int(v) for v in a.size.lower().split("x"))
        except ValueError:
            sys.exit("--size wants WxH, like 1920x1080")
        if not (640 <= w <= 16384 and 480 <= h <= 16384):
            sys.exit("--size is out of range")
        configure(w, h)
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
    print(f"  screen     {W}x{H}"
          + ("" if (W, H) == (MASTER_W, MASTER_H) else "  (scaled from the 3840x2160 master)"))
    build(bg, a.darken, a.out, a.preview, blur=a.blur, tint=a.tint)

    # The three numbers refind.conf has to agree with. big_icon_size and
    # small_icon_size decide the geometry the artwork was drawn for, and
    # frost_radius is the blur the preview matched -- if the config disagrees
    # with the artwork the menu is subtly wrong in a way nothing reports.
    json.dump({"width": W, "height": H, "big_icon_size": BIG,
               "small_icon_size": SMALL, "frost_radius": FROST},
              open(os.path.join(a.out, "geometry.json"), "w"), indent=1)
    print(f"  geometry   big_icon_size {BIG}, small_icon_size {SMALL}, frost_radius {FROST}")
