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
import argparse, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile

HERE  = os.path.dirname(os.path.abspath(__file__))
NAME  = "refind-frosted-4k-theme"
THEME = f"/usr/share/plymouth/themes/{NAME}"
STAMP = os.path.join(THEME, "built-from.json")
CONF  = "/etc/plymouth/plymouthd.conf"
MARK  = f"# {NAME}: draw the splash at the screen's real resolution."


def esp_dir():
    """Where the boot menu lives, if it lives anywhere.

    setup.sh installs into a directory of its own -- EFI/refind-frosted-4k-theme -- and
    only uses EFI/refind when a build of this was already there. Looking only in
    EFI/refind meant that on a machine installed the ordinary way this found
    nothing, said there was nothing to follow, and the splash never followed the
    photograph at all: the one thing it exists to do.

    A directory counts only if it holds a theme.conf or a refind.conf, so an
    empty EFI/refind left behind by something else is not mistaken for ours.
    """
    for root in ("/boot/efi", "/efi", "/boot"):
        for name in ("refind-frosted-4k-theme", "refind"):
            d = os.path.join(root, "EFI", name)
            if os.path.isfile(os.path.join(d, "theme.conf")) or \
               os.path.isfile(os.path.join(d, "refind.conf")):
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
    # Decide by the byte-order mark, not by trying decoders in turn. "Try UTF-16
    # and fall back to UTF-8" reads sensibly and never reaches the fallback:
    # UTF-16 decodes almost any even-length string of bytes into something, so a
    # file somebody edited in a text editor came out as a page of CJK and the
    # program concluded, quietly, that nothing had changed.
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        enc = "utf-16"
    elif raw[:3] == b"\xef\xbb\xbf":
        enc = "utf-8-sig"
    elif len(raw) >= 2 and raw[1] == 0 and raw[0] != 0:
        enc = "utf-16-le"                       # UTF-16 with the mark stripped off
    else:
        enc = "utf-8"
    try:
        text = raw.decode(enc)
    except (UnicodeDecodeError, UnicodeError):
        try:
            text = raw.decode("utf-8", "replace")
        except Exception:
            return out
    for line in text.replace("\r", "\n").split("\n"):
        line = line.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            value = parts[1].strip()
            # The boot menu quotes a filename that has a space in it, and
            # doubles any quote inside. Undo both.
            if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                value = value[1:-1].replace('""', '"')
            out[parts[0].lower()] = value
    return out


def plymouth_device_scale(width, height):
    """What Plymouth will decide the device scale is, on this screen.

    Verbatim from plymouth's get_device_scale_guess(). It matters because the
    guess is what gets used: the splash is drawn while simpledrm owns the
    display, simpledrm reports no physical size, and plymouth therefore never
    reaches the DPI calculation -- it goes on pixel count alone, and calls
    anything from 2880x1620 up a HiDPI screen. Worse, having guessed once it
    keeps guessing, so the real monitor's real dimensions never get a say.

    A scale of 2 halves the screen as the theme sees it. Plymouth's script
    plugin has no notion of device scale at all -- there is not one mention of
    it in the whole plugin -- so a theme cannot compensate: it asks how wide the
    screen is, is told 1920, and hands over a 1920-wide picture, which plymouth
    then blows back up to 3840. On a 4K screen that is the difference between
    the splash and a photograph of the splash.
    """
    if height > width:
        width, height = height, width
    if width == height * 1.5:                       # 3:2, only ever a tablet
        return 2 if (width >= 1800 and height >= 1200) else 1
    return 2 if (width >= 2880 and height >= 1620) else 1


def force_device_scale(dry):
    """Tell Plymouth not to guess.

    Returns "already" if the setting was there, "set" if this call put it there,
    "overridden:N" if the administrator has asked for a scale of N, "failed" if
    the file could not be written.

    plymouthd.conf is the file the distribution ships for exactly this, it is
    copied into the initramfs by both initramfs-tools and dracut, and it is read
    before any theme loads -- which is the only place this can be fixed, because
    by the time the theme runs the screen has already been halved.
    """
    try:
        lines = open(CONF).read().splitlines()
    except FileNotFoundError:
        lines = []
    except OSError as e:
        print(f"  scale      cannot read {CONF}: {e}")
        return "failed"

    # Already set, by us or by the administrator: leave it alone either way.
    section = None
    for line in lines:
        bare = line.strip()
        if bare.startswith("[") and bare.endswith("]"):
            section = bare[1:-1].strip().lower()
        elif section == "daemon" and "=" in bare and not bare.startswith("#"):
            key, _, value = bare.partition("=")
            if key.strip().lower() == "devicescale":
                return "already" if value.strip() == "1" else ("overridden:" + value.strip())

    if dry:
        print(f"  scale      would set DeviceScale=1 in {CONF}")
        return "set"

    out, done = [], False
    for line in lines:
        out.append(line)
        if not done and line.strip().lower() == "[daemon]":
            out += [MARK, "DeviceScale=1"]
            done = True
    if not done:
        if out and out[-1].strip():
            out.append("")
        out += ["[Daemon]", MARK, "DeviceScale=1"]

    try:
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        if os.path.exists(CONF) and not os.path.exists(CONF + ".before-" + NAME):
            shutil.copy2(CONF, CONF + ".before-" + NAME)
        tmp = CONF + ".new"
        with open(tmp, "w") as fh:
            fh.write("\n".join(out) + "\n")
        os.replace(tmp, CONF)
    except OSError as e:
        print(f"  scale      cannot write {CONF}: {e}")
        return "failed"
    print(f"  scale      DeviceScale=1 in {CONF}")
    return "set"


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
    # theme.conf is on a FAT partition that anything can write to, including a
    # Windows install and anyone with a live USB, and this runs as root. A
    # background of "../../../../etc/shadow" should name no file at all -- so
    # take the last component and nothing else, and require it to still be
    # inside the backgrounds directory when the path is put back together.
    if photo:
        photo = os.path.basename(photo.replace("\\", "/"))
    if photo in (None, "", ".", ".."):
        photo = None
    root = os.path.join(esp, "backgrounds")
    path = os.path.join(root, photo) if photo else None
    if path and os.path.dirname(os.path.abspath(path)) != os.path.abspath(root):
        path = None
    if path and not os.path.isfile(path):
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
    """Whichever of the three this system has.

    Debian and Ubuntu build an initramfs with initramfs-tools; Fedora, RHEL and
    openSUSE use dracut; Arch and its derivatives use mkinitcpio, which this did
    not know about at all -- it found neither of the other two, printed a line
    about it, and then went on to write the stamp saying the work was done, so
    every subsequent boot agreed there was nothing to do and the splash never
    appeared. All three are asked to rebuild every kernel they know about,
    because the splash has to be there whichever one is chosen.

    mkinitcpio also needs the plymouth hook in its HOOKS line to include a theme
    at all. Adding it means editing a file this program does not own, on the one
    distribution whose users are least likely to want that done for them, so it
    is reported rather than done.
    """
    if shutil.which("update-initramfs"):
        cmd = ["update-initramfs", "-u", "-k", "all"]
    elif shutil.which("dracut"):
        cmd = ["dracut", "--force", "--regenerate-all"]
    elif shutil.which("mkinitcpio"):
        cmd = ["mkinitcpio", "-P"]
        try:
            hooks = open("/etc/mkinitcpio.conf").read()
            if not re.search(r"^HOOKS=.*\bsd-plymouth\b|^HOOKS=.*\bplymouth\b",
                             hooks, re.M):
                print("  initramfs  /etc/mkinitcpio.conf has no plymouth hook, so the "
                      "splash will not show.")
                print("             add it to HOOKS, after 'base udev' (or after "
                      "'systemd' as sd-plymouth).")
        except OSError:
            pass
    else:
        raise RuntimeError(
            "no update-initramfs, no dracut and no mkinitcpio: the theme is "
            "installed but nothing can put it in an initramfs, so it will not show")
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
        # Not an error. A machine with no rEFInd has nothing to follow, and
        # exiting non-zero here aborted the installer that called it, under
        # `set -e`, halfway through.
        print("  splash     no rEFInd on the EFI partition: nothing to follow")
        return

    # Before anything else, because the answer decides what size to build at,
    # and because the file has to be right before the initramfs is rebuilt with
    # a copy of it inside.
    scaling = force_device_scale(a.dry_run)

    if a.size:
        size = tuple(int(v) for v in a.size.lower().split("x"))
    else:
        panel = screen_size()
        if scaling in ("already", "set"):
            scale = 1
        elif scaling.startswith("overridden:"):
            # Somebody set DeviceScale themselves. Believe their number rather
            # than guessing what plymouth would have guessed, which is only
            # right by accident when their number happens to be 2.
            try:
                scale = max(1, int(scaling.split(":", 1)[1]))
            except ValueError:
                scale = plymouth_device_scale(*panel)
        else:
            scale = plymouth_device_scale(*panel)
        size  = (panel[0] // scale, panel[1] // scale)
        if scale != 1:
            print(f"  scale      plymouth will halve this {panel[0]}x{panel[1]} screen; "
                  f"composing at {size[0]}x{size[1]} so at least nothing is thrown away twice")

    wanted, photo = want(esp, size)
    if photo is None:
        print("  splash     the boot menu names no photograph yet: nothing to do")
        return

    if (not a.force) and (scaling != "set") and (have() == wanted):
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

        # Build the finished directory beside the real one and move it into
        # place, rather than copying five files over the theme that is
        # currently in use. A power cut halfway through a copy leaves a theme
        # whose background is the new photograph and whose script still expects
        # the old geometry; a power cut halfway through a rename leaves either
        # the old theme or the new one.
        for f in sorted(os.listdir(theme)):
            os.chmod(os.path.join(theme, f), 0o644)
        staged = THEME + ".new"
        shutil.rmtree(staged, ignore_errors=True)
        shutil.copytree(theme, staged)
        os.chmod(staged, 0o755)
        old = THEME + ".old"
        shutil.rmtree(old, ignore_errors=True)
        if os.path.isdir(THEME):
            os.rename(THEME, old)
        os.rename(staged, THEME)
        shutil.rmtree(old, ignore_errors=True)

    print(f"  theme      {THEME}")

    # The stamp says "the installed theme was built from this". It has to be
    # written after the initramfs contains that theme, not before: written first,
    # a failed rebuild left a stamp claiming the work was done, and every boot
    # after it agreed there was nothing to do -- so the splash silently stayed
    # whatever it had been, for ever.
    rebuild_initramfs(a.dry_run)
    if not a.dry_run:
        json.dump(wanted, open(STAMP, "w"), indent=1)
    print("  splash     now the same photograph the menu is showing")


def only_one():
    """Take a lock for as long as this process runs.

    Two of these at once would both rebuild the initramfs, into the same file,
    from two different sets of contents. That can happen: the boot service runs
    it and somebody runs it by hand at the same moment. Returns the open file
    while the lock is held, the string "busy" if another copy has it, or
    "unlocked" if there is nowhere writable to put a lock -- which is not a
    reason to refuse to run, only a reason not to promise anything.
    """
    import errno, fcntl, tempfile
    for path in ("/run/refind-frosted-4k-theme-splash-sync.lock",
                 os.path.join(tempfile.gettempdir(), "refind-frosted-4k-theme-splash-sync.lock")):
        try:
            fh = open(path, "w")
        except OSError:
            continue                       # not writable here; try the next one
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            fh.close()
            if e.errno in (errno.EACCES, errno.EAGAIN):
                return "busy"
            continue
        return fh
    return "unlocked"


if __name__ == "__main__":
    # Nothing here is worth a traceback in the boot log. This runs unattended,
    # as root, once per boot, and a machine with no rEFInd or no photograph
    # chosen is not a broken machine -- it just has nothing to do.
    try:
        held = only_one()
        if held == "busy":
            print("  splash     another copy is already running; leaving it to that one")
            sys.exit(0)
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit:
        raise
    except subprocess.CalledProcessError as e:
        sys.exit(f"  splash     {' '.join(str(a) for a in e.cmd)} failed ({e.returncode})")
    except Exception as e:                                   # noqa: BLE001
        sys.exit(f"  splash     {type(e).__name__}: {e}")
