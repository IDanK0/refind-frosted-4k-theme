#!/usr/bin/env python3
"""Keep the splash the system boots into the same as the one the boot menu left.

The boot menu writes its choices to theme.conf on the EFI partition -- which
photograph, how far it is dimmed, how much colour is taken from it -- and it can
change them at any time, from its own settings screen, with no operating system
running. The splash cannot be told about that, because it lives in an initramfs
built weeks earlier: it keeps whichever photograph was current the day it was
installed, and diverges from the menu the first time anybody changes anything.

So it is asked, once, per boot. Read the EFI partition, compare it with what the
installed theme was built from, and if they differ, build the theme again and
rebuild the initramfs. It costs nothing when nothing has changed, which is
almost always, and when something has changed the new splash is there from the
next boot.

The size matters as much as the picture. Plymouth scales its background to the
screen with a two-tap filter at draw time; giving it an image that is already
the size of the screen means it scales nothing at all. That is the difference
between a splash that looks like the menu and one that looks like a photograph
of the menu.

    ./splash-sync.py            do it if anything has changed
    ./splash-sync.py --force    do it regardless
    ./splash-sync.py --dry-run  say what would happen
"""
import argparse, glob, hashlib, json, os, shutil, subprocess, sys, tempfile

HERE  = os.path.dirname(os.path.abspath(__file__))
NAME  = "refind-frosted"
THEME = f"/usr/share/plymouth/themes/{NAME}"
STAMP = os.path.join(THEME, "built-from.json")


def esp_dir():
    """Where rEFInd lives, if it lives anywhere."""
    for d in ("/boot/efi/EFI/refind", "/efi/EFI/refind", "/boot/EFI/refind"):
        if os.path.isdir(d):
            return d
    return None


def read_theme_conf(esp):
    """What the boot menu currently says. It writes UTF-16 with a byte-order
    mark, because that is what a UEFI program writes, so decode it as such and
    fall back to UTF-8 for a file somebody edited by hand."""
    path = os.path.join(esp, "theme.conf")
    out  = {}
    if not os.path.exists(path):
        return out
    raw = open(path, "rb").read()
    for enc in ("utf-16", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return out
    for line in text.replace("\r", "\n").split("\n"):
        line = line.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            out[parts[0].lower()] = parts[1].strip()
    return out


def screen_size():
    """The resolution the machine will boot at.

    The preferred mode of the largest connected output, which is what the kernel
    sets before Plymouth draws anything. A machine with no connectors to ask --
    a virtual one, or one whose driver arrives later -- gets the master size,
    which is the size everything in this project is drawn at anyway.
    """
    best = None
    for conn in sorted(glob.glob("/sys/class/drm/card*-*/")):
        try:
            if open(os.path.join(conn, "status")).read().strip() != "connected":
                continue
            mode = open(os.path.join(conn, "modes")).readline().strip()
        except OSError:
            continue
        # "3840x2160", sometimes "1920x1080i" for an interlaced mode
        if "x" not in mode:
            continue
        across, _, down = mode.partition("x")
        down = "".join(c for c in down if c.isdigit())
        if not (across.isdigit() and down):
            continue
        w, h = int(across), int(down)
        if (best is None) or (w * h > best[0] * best[1]):
            best = (w, h)
    return best or (3840, 2160)


def want(esp, size):
    """Everything the installed theme ought to have been built from."""
    conf  = read_theme_conf(esp)
    photo = conf.get("background")
    path  = os.path.join(esp, "backgrounds", photo) if photo else None
    if path and not os.path.exists(path):
        path = None
    stat = os.stat(path) if path else None
    # The bootloader has no word for "automatic" in a number, so it writes 101,
    # one past the end of the scale. build.py spells the same thing "auto".
    darken = conf.get("darken", "auto")
    if darken.strip() == "101":
        darken = "auto"
    return {
        "photo":  photo,
        "bytes":  stat.st_size if stat else 0,
        "darken": darken,
        "tint":   conf.get("tint", "100"),
        "width":  size[0],
        "height": size[1],
        "os":     open("/etc/os-release").read() if os.path.exists("/etc/os-release") else "",
    }, path


def have():
    try:
        return json.load(open(STAMP))
    except (OSError, ValueError):
        return None


def generator():
    """Where build.py and plymouth.py are. Beside this script when it is run
    from the source tree, and in /usr/local/share when it was installed."""
    for d in (HERE, f"/usr/local/share/{NAME}"):
        if os.path.exists(os.path.join(d, "build.py")) and \
           os.path.exists(os.path.join(d, "plymouth.py")):
            return d
    return None


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def rebuild_initramfs(dry):
    """Whichever of the two this system has. Debian and Ubuntu build an
    initramfs with initramfs-tools; Fedora, openSUSE and Arch use dracut. Both
    are asked to rebuild every kernel they know about, because the splash has to
    be there whichever one is chosen."""
    if shutil.which("update-initramfs"):
        cmd = ["update-initramfs", "-u", "-k", "all"]
    elif shutil.which("dracut"):
        cmd = ["dracut", "--force", "--regenerate-all"]
    else:
        print("  initramfs  no update-initramfs and no dracut: nothing rebuilt")
        return False
    print(f"  initramfs  {' '.join(cmd)}")
    if not dry:
        run(cmd, stdout=subprocess.DEVNULL)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true", help="rebuild even if nothing changed")
    ap.add_argument("--dry-run", action="store_true", help="say what would happen")
    ap.add_argument("--size", default=None, metavar="WxH",
                    help="compose at this size instead of the screen's own")
    a = ap.parse_args()

    esp = esp_dir()
    if esp is None:
        sys.exit("no rEFInd on the EFI partition: nothing to follow")

    if a.size:
        size = tuple(int(v) for v in a.size.lower().split("x"))
    else:
        size = screen_size()

    wanted, photo = want(esp, size)
    if photo is None:
        sys.exit("the boot menu names no photograph yet: nothing to do")

    if (not a.force) and (have() == wanted):
        print(f"  splash     already the photograph the menu is using "
              f"({wanted['photo']}, {size[0]}x{size[1]})")
        return

    gen = generator()
    if gen is None:
        sys.exit(f"no build.py/plymouth.py here or in /usr/local/share/{NAME}")

    print(f"  photograph {wanted['photo']}")
    print(f"  screen     {size[0]}x{size[1]}")
    if a.dry_run:
        print("  dry run    stopping here")
        return

    with tempfile.TemporaryDirectory() as tmp:
        assets = os.path.join(tmp, "assets")
        theme  = os.path.join(tmp, "theme")
        run([sys.executable, os.path.join(gen, "build.py"),
             "--background", photo, "--darken", wanted["darken"],
             "--tint", wanted["tint"], "--out", assets],
            stdout=subprocess.DEVNULL)
        run([sys.executable, os.path.join(gen, "plymouth.py"),
             "--assets", assets, "--out", theme,
             "--size", f"{size[0]}x{size[1]}"], stdout=subprocess.DEVNULL)

        os.makedirs(THEME, exist_ok=True)
        for f in sorted(os.listdir(theme)):
            shutil.copy2(os.path.join(theme, f), os.path.join(THEME, f))
            os.chmod(os.path.join(THEME, f), 0o644)
        json.dump(wanted, open(STAMP, "w"), indent=1)

    print(f"  theme      {THEME}")
    rebuild_initramfs(a.dry_run)
    print("  splash     now the same photograph the menu is showing")


if __name__ == "__main__":
    main()
