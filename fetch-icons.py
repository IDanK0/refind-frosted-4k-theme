#!/usr/bin/env python3
"""Rebuild stock-icons/ from vector sources instead of 128-pixel bitmaps.

rEFInd's icon set is 128x128 PNG. The plate wants 218, so every logo that is not
drawn here as vectors was being enlarged by 1.7 and looked it. This fetches the
vectors instead:

  * rEFInd ships SVG sources for some of its own icons, in icons/svg. Those are
    rasterised at 512.
  * For the rest, Wikimedia Commons has the official logo as SVG and will
    rasterise it at any width. Only the ones checked by eye are listed below --
    a search returns the foundation's letterhead as readily as the daemon, and
    plenty of "logos" are wordmarks that make poor icons.

What is left at 128 is listed at the bottom when this runs, honestly, because
some logos have no vector anywhere and a few are for distributions that no
longer exist.

    ./fetch-icons.py            # needs rsvg-convert and network
"""
import json, os, subprocess, sys, urllib.parse
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, "stock-icons")
SIZE = 512
API  = "https://commons.wikimedia.org/w/api.php"
UA   = "refind-frosted/1.0 (boot theme icon fetch)"

# Sources on Commons, each looked at before being written down here.
COMMONS = {
    "os_arch":      'Arch Linux "Crystal" icon.svg',
    "os_centos":    "CentOS color logo.svg",
    "os_chrome":    "Google Chrome icon (February 2022).svg",
    "os_fedora":    "Fedora icon (2021).svg",
    "os_kubuntu":   "Kubuntu logo.svg",
    "os_linux":     "NewTux.svg",
    "os_linuxmint": "Linux Mint logo without wordmark.svg",
    "os_manjaro":   "Manjaro-logo.svg",
    "os_void":      "Void Linux logo.svg",
    "os_xubuntu":   "Xubuntu logo.svg",
}

# Drawn as vectors by build.py, so whatever is here is never used.
DRAWN = {"os_win8", "os_win", "os_ubuntu",
         "os_artful", "os_bionic", "os_trusty", "os_xenial", "os_zesty"}


def refind_source():
    for p in (os.path.join(HERE, "build", "refind-0.14.2"),
              os.path.expanduser("~/.cache/refind-src/refind-0.14.2")):
        if os.path.isdir(os.path.join(p, "icons", "svg")):
            return os.path.join(p, "icons", "svg")
    return None


FILL = 0.92          # how much of the frame the drawn part of an icon occupies


def normalise(path):
    """Make every icon occupy the same share of its frame.

    rsvg-convert keeps the aspect ratio, so a wide logo rendered into a square
    comes out letterboxed and lands on the plate visibly smaller than its
    neighbours -- Devuan's swoosh arrived at two thirds the size of the bitmap it
    replaced, which reads as a worse icon however much sharper it is. Trimming to
    the ink and re-fitting puts them all on the same footing, which is what a row
    of icons wants anyway."""
    im = Image.open(path).convert("RGBA")
    box = im.split()[3].getbbox()
    if box is None:
        return
    im = im.crop(box)
    side = max(im.size)
    target = int(side / FILL)
    scale = min(target * FILL / im.width, target * FILL / im.height)
    im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                   Image.LANCZOS)
    out = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    out.alpha_composite(im, ((target - im.width) // 2, (target - im.height) // 2))
    out.save(path)


def curl(url, out):
    subprocess.run(["curl", "-sSL", "--max-time", "120", "-A", UA, "-o", out, url],
                   capture_output=True)
    return os.path.exists(out) and os.path.getsize(out) > 2000


def main():
    if subprocess.run(["which", "rsvg-convert"], capture_output=True).returncode:
        sys.exit("install librsvg2-bin")
    svgdir = refind_source()
    if svgdir is None:
        sys.exit("rEFInd source not found -- run ./build-refind.sh first")

    done, notes = {}, []
    for name in sorted(os.listdir(svgdir)):
        stem, ext = os.path.splitext(name)
        if (ext != ".svg") or not stem.startswith("os_") or (stem in DRAWN):
            continue
        out = os.path.join(DEST, stem + ".png")
        if subprocess.run(["rsvg-convert", "-w", str(SIZE), "-h", str(SIZE), "-a",
                           os.path.join(svgdir, name), "-o", out],
                          capture_output=True).returncode == 0:
            done[stem] = "rEFInd's own SVG"

    titles = [f"File:{t}" for t in COMMONS.values()]
    url = API + "?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "titles": "|".join(titles),
        "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": str(SIZE),
        "iiextmetadatafilter": "LicenseShortName"})
    reply = json.loads(subprocess.run(["curl", "-sS", "--max-time", "60", "-A", UA, url],
                                      capture_output=True, text=True).stdout)
    info = {}
    for page in reply.get("query", {}).get("pages", {}).values():
        if "missing" in page:
            continue
        ii = (page.get("imageinfo") or [{}])[0]
        info[page["title"]] = (ii.get("thumburl", ""),
                               ((ii.get("extmetadata") or {}).get("LicenseShortName")
                                or {}).get("value", "?"))
    for stem, title in COMMONS.items():
        thumb, lic = info.get("File:" + title, ("", "?"))
        if thumb and curl(thumb, os.path.join(DEST, stem + ".png")):
            done[stem] = f"Commons, {title} ({lic})"
        else:
            notes.append(f"{stem}: could not fetch {title}")

    for name in os.listdir(DEST):
        if name.startswith("os_") and name.endswith(".png"):
            normalise(os.path.join(DEST, name))

    left = sorted(s[3:] for s in
                  (os.path.splitext(f)[0] for f in os.listdir(DEST) if f.startswith("os_"))
                  if s not in done and s not in DRAWN)
    with open(os.path.join(DEST, "SOURCES.md"), "w") as fh:
        fh.write("# Where these came from\n\n"
                 "Rewritten by `fetch-icons.py`. Everything not listed is rEFInd's own\n"
                 "128-pixel icon set, kept because no vector of it exists anywhere.\n\n")
        for stem in sorted(done):
            fh.write(f"- `{stem}.png` — {done[stem]}\n")
        fh.write(f"\nStill 128 pixels: {', '.join(left)}\n")

    print(f"  {len(done)} icons rebuilt from vectors at {SIZE}px")
    print(f"  {len(DRAWN)} drawn as vectors by build.py")
    print(f"  still 128px: {', '.join(left) if left else 'none'}")
    for n in notes:
        print(f"  ! {n}")


if __name__ == "__main__":
    main()
