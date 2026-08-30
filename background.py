#!/usr/bin/env python3
"""Pick the boot menu background — from the library, or any photo of your own.

    ./background.py                     browse the library and choose
    ./background.py 3                   pick library entry 3
    ./background.py desert-skies        pick it by name
    ./background.py ~/holiday.jpg       use your own photo
    ./background.py --darken 60 2       darken it (0 = untouched, 100 = black)
    ./background.py --darken auto 2     let it work out how much is needed
    ./background.py --list              just show what is available
    ./background.py --preview 4         render a preview, install nothing

Your own photos: drop them in library/custom/ and they appear in the list.
Any size or aspect ratio works — they are centre-cropped to 16:9 and scaled
to 3840x2160.
"""
import argparse, glob, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LIB  = os.path.join(HERE, "library")
ESP  = "/boot/efi/EFI/refind"
sys.path.insert(0, HERE)
import build as B


def catalogue():
    cfg = json.load(open(os.path.join(LIB, "library.json")))
    voci = []
    for s in cfg["sfondi"]:
        voci.append({**s, "path": os.path.join(HERE, s["file"]), "custom": False})
    for p in sorted(glob.glob(os.path.join(LIB, "custom", "*"))):
        if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp")):
            voci.append({"slug": os.path.splitext(os.path.basename(p))[0],
                         "nome": os.path.basename(p), "path": p, "custom": True,
                         "licenza": "yours", "autore": "", "origine": "",
                         "luminosita": None, "darken_consigliato": None})
    return cfg, voci


def elenco(voci, cfg):
    print(f"\n  Library — default darken is {cfg['darken_predefinito']} "
          f"(0 leaves the photo untouched, 100 is black)\n")
    for i, v in enumerate(voci, 1):
        marca = "  [yours]" if v["custom"] else ""
        print(f"  {i:2d}. {v['nome']}{marca}")
        det = f"      {v['licenza']}"
        if v["luminosita"] is not None:
            det += f"   ·   luminance behind the tiles {v['luminosita']:.0f}"
            if v["darken_consigliato"]:
                det += f"   ·   suggested --darken {v['darken_consigliato']}"
            else:
                det += "   ·   dark enough as it is"
        print(det)
    print(f"\n  Drop your own photos in {os.path.relpath(os.path.join(LIB,'custom'), HERE)}/ "
          "and they show up here.\n")


def apri(p):
    for cmd in (["xdg-open", p], ["gio", "open", p]):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            continue
    return False


def risolvi(arg, voci):
    if arg is None:
        return None
    if arg.isdigit() and 1 <= int(arg) <= len(voci):
        return voci[int(arg) - 1]
    for v in voci:
        if arg == v["slug"] or arg == v["nome"]:
            return v
    if os.path.exists(os.path.expanduser(arg)):
        p = os.path.expanduser(arg)
        return {"slug": os.path.splitext(os.path.basename(p))[0], "nome": os.path.basename(p),
                "path": p, "custom": True, "licenza": "yours", "luminosita": None,
                "darken_consigliato": None}
    sys.exit(f"  Not found: {arg}\n  Run with --list to see what is available.")


def installa(assets):
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
    ap.add_argument("scelta", nargs="?")
    ap.add_argument("--darken", default=None, help="0-100 or 'auto'")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--preview", action="store_true", help="render only, install nothing")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()
    if a.help:
        print(__doc__); return

    cfg, voci = catalogue()
    darken = cfg["darken_predefinito"] if a.darken is None else a.darken
    if str(darken).lower() != "auto" and not (str(darken).isdigit() and 0 <= int(darken) <= 100):
        sys.exit("  --darken must be 0-100 or 'auto'")

    if a.list:
        elenco(voci, cfg); return

    scelto = risolvi(a.scelta, voci)
    if scelto is None:                                    # interactive
        elenco(voci, cfg)
        sheet = os.path.join(LIB, "preview-sheet.jpg")
        if os.path.exists(sheet):
            print(f"  opening the contact sheet: {os.path.relpath(sheet, HERE)}")
            apri(sheet)
        try:
            r = input("  Which one? (number, name, or a path — Enter to cancel) ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); return
        if not r:
            print("  cancelled."); return
        scelto = risolvi(r, voci)

    print(f"\n  background {scelto['nome']}")
    tmp = tempfile.mkdtemp(prefix="refind-theme-")
    prev = os.path.join(tmp, "preview.png")
    B.build(scelto["path"], darken, tmp, prev)

    if a.preview:
        finale = os.path.join(HERE, "preview.png"); shutil.copy(prev, finale)
        print(f"\n  preview written to {finale} — nothing installed.")
        apri(finale); return

    apri(prev)
    print()
    try:
        ok = input("  Install this to the boot menu? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(); return
    if ok not in ("y", "yes", "s", "si", "sì"):
        print("  cancelled — nothing was changed."); return
    installa(tmp)
    # keep the repo's assets/ in step with what is actually installed
    for p in glob.glob(f"{tmp}/*.png") + glob.glob(f"{tmp}/icons/*.png"):
        rel = os.path.relpath(p, tmp)
        dst = os.path.join(HERE, "assets", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy(p, dst)
    print("  assets/ updated to match. Reboot to see it.")


if __name__ == "__main__":
    main()
