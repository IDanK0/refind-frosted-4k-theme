#!/usr/bin/env python3
"""Generate every asset of the rEFInd theme from a single background photo.

Geometry is taken from rEFInd's own layout arithmetic (refind/menu.c), so the
frosted tiles and the OS labels — which are baked into the background image —
land exactly under the icons rEFInd will draw.

    ./build.py                                  # library default
    ./build.py --background library/desert-skies.jpg --darken 60
    ./build.py --background ~/mine.png --darken 0 --preview-only
"""
import argparse, json, math, os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageStat

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- geometry
W, H = 3840, 2160
XSP, YSP = 8, 16          # TILE_XSPACING / TILE_YSPACING, #define'd in menu.c
SS = 4                    # supersampling for the vector artwork
BIG, SMALL, NTOOLS = 549, 48, 5

TILE  = (BIG * 9) // 8            # TileSizes[0] = big_icon_size * 9/8
TILE1 = (SMALL * 4) // 3          # TileSizes[1] = small_icon_size * 4/3
R0X   = (W + XSP - (TILE + XSP) * 2) // 2
R0Y   = (H // 2) - TILE // 2      # the OS row is always vertically centred
R1Y   = R0Y + TILE + YSP
R1X   = (W + XSP - (TILE1 + XSP) * NTOOLS) // 2
TXTY  = R1Y + TILE1 + YSP
POS   = [R0X, R0X + TILE + XSP]
CEN   = [p + TILE // 2 for p in POS]
OFF   = (TILE - BIG) // 2
MAXVIS = W // (TILE + XSP) - 1

PLATE, LOGO_VIS, F_OS, LBL_Y = 340, 218, 66, 1290
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
# luminance is sampled here to warn when a photo will wash the tiles out
BOX = (1299, 850, 2541, 1400)
# luminance the Mojave original sat at; the target for --darken auto
TARGET_LUM = 30.0

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
    m = S * 0.09; d.ellipse([m, m, S - m, S - m], outline=GR, width=int(S * 0.075))
    d.ellipse([S * .44, S * .24, S * .56, S * .36], fill=GR)
    d.rounded_rectangle([S * .44, S * .43, S * .56, S * .76], radius=S * .06, fill=GR)
def t_hidden(d, S):
    d.polygon([(S*.14,S*.50),(S*.50,S*.12),(S*.88,S*.12),(S*.88,S*.50),(S*.52,S*.88),(S*.14,S*.50)],
              outline=GR, width=int(S * .075))
    d.ellipse([S*.68,S*.22,S*.80,S*.34], fill=GR)
def t_power(d, S):
    m = S * .16; d.arc([m, m, S - m, S - m], -55, 235, fill=GR, width=int(S * .085))
    d.rounded_rectangle([S*.455,S*.10,S*.545,S*.46], radius=S*.045, fill=GR)
def t_reset(d, S):
    m = S * .16; d.arc([m, m, S - m, S - m], 120, 60, fill=GR, width=int(S * .085))
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

# order matters: it is the order rEFInd adds the default tools
TOOLS = [(t_about, "func_about.png"), (t_hidden, "func_hidden.png"),
         (t_power, "func_shutdown.png"), (t_reset, "func_reset.png"),
         (t_chip,  "func_firmware.png")]

# -------------------------------------------------------------------- glass
def frost(img, cx, cy, s):
    """Bake a frosted panel: a real blur of the photo, done once, at zero
    runtime cost. rEFInd has no compositor, so live blur is impossible."""
    x, y = cx - s // 2, cy - s // 2
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).rounded_rectangle([x+6, y+14, x+s+6, y+s+14], radius=int(s*.19), fill=90)
    img.paste(Image.new("RGB", (W, H), (4, 6, 14)), (0, 0), sh.filter(ImageFilter.GaussianBlur(26)))
    p = img.crop((x, y, x + s, y + s)).filter(ImageFilter.GaussianBlur(34))
    p = ImageEnhance.Brightness(p).enhance(1.34)
    p = Image.blend(p, Image.new("RGB", (s, s), (226, 233, 250)), 0.19)
    gr = Image.new("L", (1, s)); gr.putdata([int(52 * (1 - i / s)) for i in range(s)])
    p = Image.composite(Image.new("RGB", (s, s), (255,) * 3), p, gr.resize((s, s)))
    m = Image.new("L", (s * SS, s * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, s*SS-1, s*SS-1], radius=int(s*SS*.19), fill=255)
    img.paste(p, (x, y), m.resize((s, s), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.6)))
    rm = Image.new("RGBA", (s * SS, s * SS), (0, 0, 0, 0))
    ImageDraw.Draw(rm).rounded_rectangle([3, 3, s*SS-4, s*SS-4], radius=int(s*SS*.19),
                                         outline=(255, 255, 255, 150), width=5 * SS)
    rm = rm.resize((s, s), Image.LANCZOS)
    fade = Image.new("L", (1, s)); fade.putdata([int(255 * (1 - .72 * i / s)) for i in range(s)])
    img.paste(Image.new("RGB", (s, s), (255,) * 3), (x, y),
              Image.composite(rm.split()[3], Image.new("L", (s, s), 0), fade.resize((s, s))))

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

# --------------------------------------------------------------------- main
def build(background, darken, out, preview_path=None, quiet=False):
    say = (lambda *a: None) if quiet else print
    os.makedirs(os.path.join(out, "icons"), exist_ok=True)

    say(f"  geometry   TILE={TILE} MaxVisible={MAXVIS} (needs >= 2)")
    assert MAXVIS >= 2, "big_icon_size too large: rEFInd would scroll the OS row"

    # font: BLACK glyphs. libeg/text.c inverts the font on dark backgrounds
    # (255-x), so black here renders as light grey on screen.
    GREY_ON_SCREEN = 160
    fill = 255 - GREY_ON_SCREEN
    f = ImageFont.truetype(FONT_MONO, 44); asc, desc = f.getmetrics()
    cw, ch = math.ceil(f.getlength("M")), asc + desc
    fi = Image.new("RGBA", (cw * 96, ch), (0, 0, 0, 0)); d = ImageDraw.Draw(fi)
    for i in range(95):
        d.text((i * cw, 0), chr(32 + i), font=f, fill=(fill,) * 3 + (255,))
    d.rectangle([95 * cw + 2, 2, 96 * cw - 3, ch - 3], outline=(fill,) * 3 + (255,), width=2)
    fi.save(f"{out}/font.png")
    say(f"  font       cell {cw}x{ch}, glyphs at {fill} -> {GREY_ON_SCREEN} on screen")

    box = BIG * 2                       # drawn at 2x, rEFInd shrinks to BIG
    for fn, name in ((logo_windows, "icon_windows.png"), (logo_ubuntu, "icon_ubuntu.png")):
        t = Image.new("RGBA", (box, box), (0, 0, 0, 0))
        t.alpha_composite(aa(LOGO_VIS * 2, fn), ((box - LOGO_VIS * 2) // 2,) * 2)
        t.save(f"{out}/{name}")
    for fn, name in TOOLS:
        aa(192, fn).save(f"{out}/icons/{name}")

    bg = fit(background)
    lum_raw = luminance(bg)
    if str(darken).lower() == "auto":
        d = 0 if lum_raw <= TARGET_LUM else round((1 - TARGET_LUM / lum_raw) * 100)
        darken = 0 if d < 5 else min(100, d)   # a few percent is not worth applying
        say(f"  darken     auto -> {darken}%  (targeting luminance {TARGET_LUM:.0f})")
    darken = int(darken)
    if darken:
        bg = ImageEnhance.Brightness(bg).enhance(1 - darken / 100)
    lum = luminance(bg)
    say(f"  darken     {darken}%   luminance behind the tiles {lum_raw:.0f} -> {lum:.0f}")
    if lum > 60:
        say(f"  NOTE       that is bright; the frosted tiles and the white labels")
        say(f"             will have little contrast. Try --darken {min(100, round((1-30/lum_raw)*100))}.")

    for c in CEN:
        frost(bg, c, H // 2, PLATE)
    d = ImageDraw.Draw(bg)
    FB = ImageFont.truetype(FONT_BOLD, F_OS)
    bbs = [d.textbbox((0, 0), t, font=FB) for t in ("Windows", "Ubuntu")]
    ink_t = LBL_Y + min(b[1] for b in bbs); ink_b = LBL_Y + max(b[3] for b in bbs)
    above, below = ink_t - (H // 2 + PLATE // 2), R1Y - ink_b
    say(f"  spacing    plate->label {above}px   label->tools {below}px")
    assert below > 0, "the tool row would cover the labels"
    assert abs(above - below) <= 2, f"asymmetric spacing: {above} vs {below}"
    for cx, t in zip(CEN, ("Windows", "Ubuntu")):
        bb = d.textbbox((0, 0), t, font=FB)
        d.text((cx - (bb[2] - bb[0]) // 2, LBL_Y), t, font=FB, fill=(255, 255, 255))
    bg.save(f"{out}/background.png", "PNG", optimize=True)

    ins = (TILE - PLATE) // 2
    sel = Image.new("RGBA", (TILE * SS, TILE * SS), (0, 0, 0, 0)); sd = ImageDraw.Draw(sel)
    a, b = ins * SS, (TILE - ins) * SS
    sd.rounded_rectangle([a, a, b, b], radius=int(PLATE*SS*.19), fill=(255, 255, 255, 34))
    sd.rounded_rectangle([a, a, b, b], radius=int(PLATE*SS*.19), outline=(255, 255, 255, 215), width=5*SS)
    sel.resize((TILE, TILE), Image.LANCZOS).save(f"{out}/selection_big.png")
    ss = Image.new("RGBA", (TILE1 * SS, TILE1 * SS), (0, 0, 0, 0)); s2 = ImageDraw.Draw(ss)
    s2.rounded_rectangle([2, 2, TILE1*SS-3, TILE1*SS-3], radius=int(TILE1*SS*.24), fill=(255, 255, 255, 40))
    s2.rounded_rectangle([2, 2, TILE1*SS-3, TILE1*SS-3], radius=int(TILE1*SS*.24), outline=(255, 255, 255, 190), width=3*SS)
    ss.resize((TILE1, TILE1), Image.LANCZOS).save(f"{out}/selection_small.png")

    if preview_path:
        c = bg.convert("RGBA")
        c.alpha_composite(Image.open(f"{out}/selection_big.png").convert("RGBA"), (POS[0], R0Y))
        for x, n in zip(POS, ("icon_windows.png", "icon_ubuntu.png")):
            c.alpha_composite(Image.open(f"{out}/{n}").convert("RGBA").resize((BIG, BIG), Image.LANCZOS),
                              (x + OFF, R0Y + OFF))
        o1 = (TILE1 - SMALL) // 2
        for i, (_, n) in enumerate(TOOLS):
            c.alpha_composite(Image.open(f"{out}/icons/{n}").convert("RGBA").resize((SMALL, SMALL), Image.LANCZOS),
                              (R1X + i * (TILE1 + XSP) + o1, R1Y + o1))
        c.convert("RGB").save(preview_path)
        say(f"  preview    {preview_path}")
    return lum

if __name__ == "__main__":
    cfg = {}
    lib = os.path.join(HERE, "library", "library.json")
    if os.path.exists(lib):
        cfg = json.load(open(lib))
    ap = argparse.ArgumentParser(description="Build the rEFInd theme assets.")
    ap.add_argument("--background", default=None, help="photo to use (default: library default)")
    ap.add_argument("--darken", default=str(cfg.get("default_darken", 24)),
                    help="0 = untouched, 100 = black, or 'auto' (default: %(default)s)")
    ap.add_argument("--out", default=os.path.join(HERE, "assets"))
    ap.add_argument("--preview", default=None, help="also write a full-screen preview here")
    a = ap.parse_args()
    if str(a.darken).lower() != "auto" and not (a.darken.isdigit() and 0 <= int(a.darken) <= 100):
        sys.exit("--darken must be 0-100 or 'auto'")
    bg = a.background or os.path.join(HERE, "library",
         next(s["file"] for s in cfg["backgrounds"] if s["slug"] == cfg["default"]).split("/")[-1])
    print(f"  background {bg}")
    build(bg, a.darken, a.out, a.preview)
