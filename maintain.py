#!/usr/bin/env python3
"""Keep the machine the way it was installed, once per boot.

Four things drift, and all four are somebody else doing their job properly:

  * The photograph changes. The boot menu can be re-themed from its own settings
    screen with no operating system running, and the splash lives in an
    initramfs built weeks earlier, so it cannot be told. It is asked instead.
  * A plymouth package upgrade resets the default theme through
    update-alternatives, and the splash silently goes back to the distribution's.
  * A refind package upgrade writes its own refind_x64.efi over the EFI
    partition, and the menu loses the frost, the settings screen and the boot
    logo handover while still booting perfectly well, so nothing complains.
  * Firmware clears its boot entries. A CMOS reset, a firmware update, some
    laptops after a battery change, and the entry pointing at the menu is
    gone.

None of them is an error. All of them are quiet. So this checks, repairs what it
can repair, and says plainly what it cannot.

    maintain                    check, and put right what has drifted
    maintain --check            check and report, change nothing
    maintain --force            rebuild the splash regardless
    maintain --dry-run          say what would happen
"""
import argparse, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile

HERE  = os.path.dirname(os.path.abspath(__file__))
NAME  = "refind-frosted-4k-theme"
THEME = f"/usr/share/plymouth/themes/{NAME}"
LIB   = f"/usr/local/share/{NAME}"      # the generator, and a copy of the binary
STATE = f"/var/lib/{NAME}"              # the installer's journal
STAMP = os.path.join(THEME, "built-from.json")
CONF  = "/etc/plymouth/plymouthd.conf"
MARK  = f"# {NAME}: draw the splash at the screen's real resolution."


def esp_dir():
    """Where the boot menu lives, if it lives anywhere.

    setup.sh installs into a directory of its own, EFI/refind-frosted-4k-theme, and
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
    reaches the DPI calculation; it goes on pixel count alone, and calls
    anything from 2880x1620 up a HiDPI screen. Worse, having guessed once it
    keeps guessing, so the real monitor's real dimensions never get a say.

    A scale of 2 halves the screen as the theme sees it. Plymouth's script
    plugin has no notion of device scale at all: there is not one mention of
    it in the whole plugin, so a theme cannot compensate: it asks how wide the
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
    before any theme loads, which is the only place this can be fixed, because
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
    a virtual one, or one whose driver arrives later: gets the master size,
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
    # background of "../../../../etc/shadow" should name no file at all, so
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
    not know about at all; it found neither of the other two, printed a line
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



# --------------------------------------------------------------- self-repair
#
# Each check answers one question and, where it can, puts the answer right. They
# report through this, so a boot where nothing has drifted prints nothing at all
# and a boot where something has says exactly what and what was done about it.

class Report:
    def __init__(self, dry):
        self.dry = dry
        self.fixed = []
        self.broken = []

    def ok(self, what):
        pass                                   # silence is the normal case

    def repaired(self, what, how):
        # In --check nothing has been done, so nothing may be reported as done.
        self.fixed.append(what)
        if self.dry:
            print(f"  would fix  {what}: {how}")
        else:
            print(f"  repaired   {what}: {how}")

    def cannot(self, what, why):
        self.broken.append(what)
        print(f"  drifted    {what}: {why}")


def theme_is_selected():
    """Which theme plymouth will actually draw."""
    link = "/usr/share/plymouth/themes/default.plymouth"
    try:
        return os.path.basename(os.path.dirname(os.path.realpath(link)))
    except OSError:
        return None


def select_theme(dry):
    """Make ours the default again, whichever mechanism this distribution uses."""
    plymouth = f"{THEME}/{NAME}.plymouth"
    if not os.path.isfile(plymouth):
        return False
    if dry:
        return True
    if shutil.which("update-alternatives"):
        subprocess.run(["update-alternatives", "--install",
                        "/usr/share/plymouth/themes/default.plymouth",
                        "default.plymouth", plymouth, "200"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return subprocess.run(["update-alternatives", "--set", "default.plymouth", plymouth],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    if shutil.which("plymouth-set-default-theme"):
        return subprocess.run(["plymouth-set-default-theme", NAME],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    return False


def check_theme_selected(rep):
    """A plymouth upgrade re-runs update-alternatives and can take the default
    back. The theme is still installed; it is simply no longer the one drawn."""
    if not os.path.isdir(THEME):
        return False                            # the splash half is not installed
    now = theme_is_selected()
    if now == NAME:
        rep.ok("theme selected")
        return False
    if select_theme(rep.dry):
        rep.repaired("plymouth theme", f"was '{now or 'none'}', selected again")
        return True                             # the initramfs now needs rebuilding
    rep.cannot("plymouth theme", f"'{now or 'none'}' is selected and it could not be changed")
    return False


def theme_in_initramfs():
    """Is the theme actually inside the image the machine will boot?

    Rebuilding the initramfs is the expensive repair here, so it is worth being
    sure before doing it. lsinitramfs lists without extracting.
    """
    try:
        rel = os.uname().release
    except OSError:
        return None
    for img in (f"/boot/initrd.img-{rel}", f"/boot/initramfs-{rel}.img"):
        if not os.path.isfile(img):
            continue
        for lister in (["lsinitramfs", img], ["lsinitrd", img]):
            if not shutil.which(lister[0]):
                continue
            try:
                out = subprocess.run(lister, capture_output=True, text=True, timeout=120)
            except (OSError, subprocess.SubprocessError):
                continue
            if out.returncode == 0:
                return f"themes/{NAME}/" in out.stdout or f"themes/{NAME}\n" in out.stdout
        return None                             # no lister: cannot tell, do not guess
    return None


def check_theme_in_initramfs(rep):
    if not os.path.isdir(THEME):
        return
    present = theme_in_initramfs()
    if present is None:
        return                                  # nothing to say if we cannot look
    if present:
        rep.ok("theme in the initramfs")
        return
    if rep.dry:
        rep.cannot("initramfs", "the theme is missing from it")
        return
    try:
        rebuild_initramfs(False)
        rep.repaired("initramfs", "the theme was missing from it; rebuilt")
    except Exception as e:                       # noqa: BLE001
        rep.cannot("initramfs", f"the theme is missing and the rebuild failed: {e}")


PATCHED_MARK = b"f\x00r\x00o\x00s\x00t\x00_\x00r\x00a\x00d\x00i\x00u\x00s\x00"


def is_ours(binary):
    """rEFInd keeps its configuration tokens in the binary as UTF-16 strings, so
    a build carrying frost_radius is one of ours and a stock one is not."""
    try:
        with open(binary, "rb") as fh:
            return PATCHED_MARK in fh.read()
    except OSError:
        return False


def check_boot_menu(rep, esp):
    """A distribution's refind package writes its own binary over this one on
    upgrade. The machine still boots, and the menu still works, so nothing
    complains: it has simply lost the frost, the settings screen and the boot
    logo handover."""
    binary = os.path.join(esp, "refind_x64.efi")
    if not os.path.isfile(binary):
        rep.cannot("boot menu", f"{binary} is gone")
        return
    if is_ours(binary):
        rep.ok("boot menu")
        return
    kept = os.path.join(LIB, "refind_x64.efi")
    if not os.path.isfile(kept):
        rep.cannot("boot menu", "it has been replaced by another build and no copy was kept")
        return
    if rep.dry:
        rep.cannot("boot menu", "it has been replaced by another build")
        return
    try:
        shutil.copy2(binary, binary + ".replaced-" + NAME)
        shutil.copy2(kept, binary)
        rep.repaired("boot menu", "another build had replaced it; put back")
    except OSError as e:
        rep.cannot("boot menu", f"another build replaced it and it could not be put back: {e}")


def firmware_entry(esp_dir_name):
    """A Boot#### entry that actually points at this menu, if there is one.

    Not one whose label mentions the project: the entry on a machine where
    rEFInd was installed before this was may be called anything, and a label is
    the one part of a boot entry nobody has to keep accurate. What decides is
    the path in the device path, \\EFI\\<dir>\\refind_x64.efi, which is
    where the firmware will actually go looking.

    Returns the entry number, "" if the firmware has none, or None if the
    question could not be asked at all.
    """
    if not shutil.which("efibootmgr") or not os.path.isdir("/sys/firmware/efi/efivars"):
        return None
    try:
        out = subprocess.run(["efibootmgr", "-v"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    want = ("\\EFI\\" + esp_dir_name + "\\").lower()
    for line in out.stdout.splitlines():
        if not line.startswith("Boot") or "*" not in line.split("\t")[0]:
            continue
        low = line.lower()
        if want in low and "refind_x64.efi" in low:
            return line.split()[0].rstrip("*")[4:]
    return ""


def check_firmware_entry(rep, esp_dir_name):
    """Firmware forgets. A CMOS reset, a firmware update, a flat coin cell, and
    the entry is gone: usually along with every other entry, which is why this
    reports rather than quietly writing to NVRAM on a machine that has just lost
    its boot configuration and may be mid-recovery."""
    if not os.path.isfile(os.path.join(STATE, "journal")):
        return                                  # the menu half was never installed
    num = firmware_entry(esp_dir_name)
    if num is None:
        return                                  # no efibootmgr, or no efivarfs
    if num:
        rep.ok("firmware entry")
        return
    rep.cannot("firmware entry",
               "no boot entry points at the menu any more. Other entries have "
               "probably gone too, so check them before adding one back; "
               f"re-running  sudo {os.path.join(HERE, 'setup.sh')}  creates it")




# ------------------------------------------------------------------- updates
#
# Deliberately not part of the per-boot check. That runs before the network is
# up, from a oneshot unit that the boot waits on, and a git fetch there is a
# thing that can hang a machine at "Starting ..." for ninety seconds. The check
# lives on a daily timer of its own instead, ordered after the network.

def installed_state():
    try:
        return json.load(open(os.path.join(STATE, "installed.json")))
    except (OSError, ValueError):
        return {}


def version_of(checkout):
    try:
        return open(os.path.join(checkout, "VERSION")).read().strip()
    except OSError:
        return None


def newer(a, b):
    """Is a newer than b? Both are dotted numbers; anything unparseable loses."""
    def parts(v):
        try:
            return [int(x) for x in str(v).split(".")]
        except ValueError:
            return None
    pa, pb = parts(a), parts(b)
    if pa is None or pb is None:
        return False
    return pa > pb


def check_for_update(apply_it, dry):
    """Ask the checkout's remote whether there is a newer version.

    It only looks at the git checkout this was installed from. There is no
    download server, no update endpoint and no code fetched from anywhere this
    machine was not already pointed at. An updater for a bootloader should be
    the least imaginative program in the project.
    """
    state = installed_state()
    checkout = state.get("checkout")
    if not checkout or not os.path.isdir(os.path.join(checkout, ".git")):
        print("  update     installed from somewhere that is no longer a git checkout; "
              "nothing to check")
        return
    here = version_of(checkout)

    # This is meant to run as the person who owns the checkout, from their own
    # user timer. A public remote needs no credentials, but a private one is
    # reached only from the keyring of whoever cloned it, and root has no keyring
    # to ask. Run as anyone else against a private remote it fails to
    # authenticate, and says so rather than failing quietly.
    def git(*args, timeout=120):
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"          # never sit waiting for a password
        return subprocess.run(["git", "-C", checkout, *args],
                              capture_output=True, text=True, timeout=timeout, env=env)

    try:
        fetched = git("fetch", "--quiet", "origin")
        if fetched.returncode != 0:
            why = fetched.stderr.strip().splitlines()[-1] if fetched.stderr.strip() else "no reason given"
            print(f"  update     could not reach the remote: {why}")
            if "could not read Username" in why or "Authentication failed" in why:
                print(f"  update     that is a credentials problem, not a network one. This has to "
                      f"run as whoever cloned {checkout}; as root it has no keyring to ask.")
            return
        branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"
        behind = git("rev-list", "--count", f"HEAD..origin/{branch}").stdout.strip()
        remote_version = git("show", f"origin/{branch}:VERSION").stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  update     could not ask the remote: {e}")
        return

    if behind in ("", "0"):
        return                                   # up to date; say nothing
    print(f"  update     {behind} commit(s) behind origin/{branch}"
          + (f", version {here} -> {remote_version}" if newer(remote_version, here) else ""))

    if not apply_it:
        print(f"  update     not applying automatically. To take it:")
        print(f"                 cd {checkout} && git pull && sudo ./setup.sh")
        # A line in the journal is a line nobody reads. Say it where it will be
        # seen, if there is a desktop to say it to.
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", "-a", NAME, "-u", "low",
                            "A newer boot theme is available",
                            f"version {here} -> {remote_version}\n"
                            f"cd {checkout} && git pull && sudo ./setup.sh"],
                           check=False)
        return
    if dry:
        print("  update     would pull and re-run the installer")
        return

    # Refuse on a dirty tree. Pulling over somebody's edits to the thing that
    # boots the machine is not an update, it is a surprise.
    if git("status", "--porcelain").stdout.strip():
        print("  update     the checkout has local changes; not touching it")
        return
    if git("pull", "--ff-only", "--quiet").returncode != 0:
        print("  update     the pull did not fast-forward; leaving it alone")
        return
    print(f"  update     pulled. Running the installer.")
    subprocess.run(["sudo", "-n", os.path.join(checkout, "setup.sh"), "--yes"],
                   check=False)


def other_systems(esp):
    """Linux installs on this machine that do not have the splash.

    The boot menu needs nothing done for them: rEFInd finds them, and each gets
    its own tile, its own logo and the handover picture. The Plymouth splash is
    different; it lives inside an initramfs, so it can only be installed from
    inside the system it belongs to. This says which those are rather than
    pretending it can reach them.
    """
    root = os.path.dirname(os.path.dirname(esp))          # .../EFI/<us> -> ...
    efi = os.path.join(root, "EFI")
    ours = os.path.basename(esp).lower()
    skip = {ours, "boot", "microsoft", "tools", "refind-frosted-4k-theme"}
    found = []
    try:
        for d in sorted(os.listdir(efi)):
            if d.lower() in skip or not os.path.isdir(os.path.join(efi, d)):
                continue
            found.append(d)
    except OSError:
        return []
    return found


def finish(rep, reselected, rebuilt):
    """The initramfs check goes last, because the work above may already have
    rebuilt it and there is no sense reading a 40 MB index twice."""
    if reselected and not rebuilt and not rep.dry:
        try:
            rebuild_initramfs(False)
            rep.repaired("initramfs", "rebuilt around the theme that was put back")
            rebuilt = True
        except Exception as e:                    # noqa: BLE001
            rep.cannot("initramfs", f"could not rebuild: {e}")
    if not rebuilt:
        check_theme_in_initramfs(rep)
    if rep.broken:
        print(f"  {len(rep.broken)} thing(s) drifted that could not be put right")



def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true", help="rebuild even if nothing changed")
    ap.add_argument("--dry-run", action="store_true", help="say what would happen")
    ap.add_argument("--size", default=None, metavar="WxH",
                    help="compose at this size instead of the screen's own")
    ap.add_argument("--check", action="store_true",
                    help="report what has drifted, repair nothing")
    ap.add_argument("--update", action="store_true",
                    help="ask the remote whether there is a newer version")
    ap.add_argument("--apply-update", action="store_true",
                    help="with --update, pull it and re-run the installer")
    a = ap.parse_args()
    if a.check:
        a.dry_run = True

    if a.update:
        check_for_update(a.apply_update, a.dry_run)
        return

    esp = esp_dir()
    if esp is None:
        # Not an error. A machine with no rEFInd has nothing to follow, and
        # exiting non-zero here aborted the installer that called it, under
        # `set -e`, halfway through.
        print("  splash     no rEFInd on the EFI partition: nothing to follow")
        return

    # Everything that is not the photograph. These are cheap: a few stats and
    # one read of the initramfs index, and on a boot where nothing has drifted
    # they print nothing, which is the point: a maintenance program that talks
    # every morning is one nobody reads.
    rep = Report(a.dry_run)
    reselected = check_theme_selected(rep)
    check_boot_menu(rep, esp)
    check_firmware_entry(rep, os.path.basename(esp))

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

    rebuilt = False
    if (not a.force) and (scaling != "set") and (have() == wanted):
        if not (rep.fixed or rep.broken):
            print(f"  splash     already the photograph the menu is using "
                  f"({wanted['photo']}, {size[0]}x{size[1]})")
        finish(rep, reselected, rebuilt)
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
    # after it agreed there was nothing to do, so the splash silently stayed
    # whatever it had been, for ever.
    rebuild_initramfs(a.dry_run)
    if not a.dry_run:
        json.dump(wanted, open(STAMP, "w"), indent=1)
    print("  splash     now the same photograph the menu is showing")
    finish(rep, reselected, True)


def only_one():
    """Take a lock for as long as this process runs.

    Two of these at once would both rebuild the initramfs, into the same file,
    from two different sets of contents. That can happen: the boot service runs
    it and somebody runs it by hand at the same moment. Returns the open file
    while the lock is held, the string "busy" if another copy has it, or
    "unlocked" if there is nowhere writable to put a lock, which is not a
    reason to refuse to run, only a reason not to promise anything.
    """
    import errno, fcntl, tempfile
    for path in ("/run/refind-frosted-4k-theme-maintain.lock",
                 os.path.join(tempfile.gettempdir(), "refind-frosted-4k-theme-maintain.lock")):
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
    # chosen is not a broken machine. It just has nothing to do.
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
