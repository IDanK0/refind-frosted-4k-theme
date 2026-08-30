#!/usr/bin/env python3
"""Pick the boot menu background — from the library, or any photo of your own.

    ./background.py                     browse the library and choose
    ./background.py 3                   pick library entry 3
    ./background.py desert-skies        pick it by name
    ./background.py ~/holiday.jpg       use your own photo
    ./background.py --darken 60 2       dim it (0 = untouched, 100 = black)
    ./background.py --darken auto 2     let it work out how much is needed
    ./background.py --list              just show what is available
    ./background.py --preview 4         render a preview, install nothing

Your own photos: drop them in library/custom/ and they appear in the list.
Any size or aspect ratio works — they are centre-cropped to 16:9 and scaled
to 3840x2160.

There is a graphical version too: ./background-gui.py
"""
import argparse, glob, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "library")
ESP  = "/boot/efi/EFI/refind"
sys.path.insert(0, HERE)
import build as B


def catalogue():
    """Library entries first, then anything dropped in library/custom/."""
    cfg = json.load(open(os.path.join(LIB, "library.json")))
    entries = [{**b, "path": os.path.join(HERE, b["file"]), "custom": False}
               for b in cfg["backgrounds"]]
    for p in sorted(glob.glob(os.path.join(LIB, "custom", "*"))):
        if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp")):
            entries.append({"slug": os.path.splitext(os.path.basename(p))[0],
                            "name": os.path.basename(p), "path": p, "custom": True,
                            "licence": "yours", "author": "", "source": "",
                            "luminance": None, "suggested_darken": None})
    return cfg, entries


def show(entries, cfg):
    print(f"\n  Library — default darken is {cfg['default_darken']} "
          f"(0 leaves the photo untouched, 100 is black)\n")
    for i, e in enumerate(entries, 1):
        mark = "  [yours]" if e["custom"] else ""
        print(f"  {i:2d}. {e['name']}{mark}")
        line = f"      {e['licence']}"
        if e["luminance"] is not None:
            line += f"   ·   luminance behind the tiles {e['luminance']:.0f}"
            line += (f"   ·   suggested --darken {e['suggested_darken']}"
                     if e["suggested_darken"] else "   ·   dark enough as it is")
        print(line)
    print(f"\n  Drop your own photos in "
          f"{os.path.relpath(os.path.join(LIB, 'custom'), HERE)}/ and they show up here.\n")


def open_file(path):
    for cmd in (["xdg-open", path], ["gio", "open", path]):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            continue
    return False


def resolve(arg, entries):
    if arg is None:
        return None
    if arg.isdigit() and 1 <= int(arg) <= len(entries):
        return entries[int(arg) - 1]
    for e in entries:
        if arg in (e["slug"], e["name"]):
            return e
    path = os.path.expanduser(arg)
    if os.path.exists(path):
        return {"slug": os.path.splitext(os.path.basename(path))[0],
                "name": os.path.basename(path), "path": path, "custom": True,
                "licence": "yours", "luminance": None, "suggested_darken": None}
    sys.exit(f"  Not found: {arg}\n  Run with --list to see what is available.")


def deploy(assets):
    if not os.path.isdir(ESP):
        sys.exit(f"  rEFInd not found at {ESP} — nothing installed.")
    print("  installing (sudo may ask for your password)...")
    files = [(f"{assets}/{n}", f"{ESP}/{n}") for n in
             ("background.png", "font.png", "icon_windows.png", "icon_ubuntu.png",
              "selection_big.png", "selection_small.png")]
    files += [(p, f"{ESP}/icons/{os.path.basename(p)}")
              for p in glob.glob(f"{assets}/icons/*.png")]
    for src, dst in files:
        subprocess.run(["sudo", "install", "-m", "0755", src, dst], check=True)
    print(f"  done — {len(files)} files written to {ESP}")


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("choice", nargs="?")
    ap.add_argument("--darken", default=None, help="0-100 or 'auto'")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--preview", action="store_true", help="render only, install nothing")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()
    if a.help:
        print(__doc__); return

    cfg, entries = catalogue()
    darken = cfg["default_darken"] if a.darken is None else a.darken
    if str(darken).lower() != "auto" and not (str(darken).isdigit() and 0 <= int(darken) <= 100):
        sys.exit("  --darken must be 0-100 or 'auto'")

    if a.list:
        show(entries, cfg); return

    chosen = resolve(a.choice, entries)
    if chosen is None:                                    # interactive
        show(entries, cfg)
        sheet = os.path.join(LIB, "preview-sheet.jpg")
        if os.path.exists(sheet):
            print(f"  opening the contact sheet: {os.path.relpath(sheet, HERE)}")
            open_file(sheet)
        try:
            reply = input("  Which one? (number, name, or a path — Enter to cancel) ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); return
        if not reply:
            print("  cancelled."); return
        chosen = resolve(reply, entries)

    print(f"\n  background {chosen['name']}")
    tmp = tempfile.mkdtemp(prefix="refind-theme-")
    preview = os.path.join(tmp, "preview.png")
    B.build(chosen["path"], darken, tmp, preview)

    if a.preview:
        final = os.path.join(HERE, "preview.png"); shutil.copy(preview, final)
        print(f"\n  preview written to {final} — nothing installed.")
        open_file(final); return

    open_file(preview)
    print()
    try:
        ok = input("  Install this to the boot menu? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(); return
    if ok not in ("y", "yes"):
        print("  cancelled — nothing was changed."); return
    deploy(tmp)
    # keep the repo's assets/ in step with what is actually installed
    for p in glob.glob(f"{tmp}/*.png") + glob.glob(f"{tmp}/icons/*.png"):
        dst = os.path.join(HERE, "assets", os.path.relpath(p, tmp))
        os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy(p, dst)
    print("  assets/ updated to match. Reboot to see it.")


if __name__ == "__main__":
    main()
