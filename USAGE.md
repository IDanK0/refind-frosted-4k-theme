# Usage

Everything lives in the directory you cloned. The graphical way needs no
terminal at all; the command line is there if you prefer it.

---

## The easy way

Run `./install-launcher.sh` once. **Boot Menu Background** then appears in the
applications menu — search for it and click.

The window shows every option as a thumbnail, already composited into the theme
so you see what it will actually look like:

- the **+** button in the header brings in a photo of your own
- **Automatic dimming** is on by default; turn it off to use the slider
- **Preview** renders a full-screen image and opens it, touching nothing
- **Apply** installs, asking for your password once through the system dialog

The interface follows your system language. English and Italian ship with it;
adding another is a matter of copying `po/it.po` and translating 21 strings.

---

## From the command line

```bash
./background.py                   # browse the library and choose
./background.py 3                 # by number
./background.py desert-skies      # by name
./background.py --list            # just list, open nothing
```

### Your own photo

```bash
./background.py ~/Pictures/holiday.jpg
```

Or add it to the library so it stays there and shows up in the list:

```bash
cp ~/Pictures/holiday.jpg library/custom/
./background.py
```

Any size, any aspect ratio: it is centre-cropped to 16:9 and scaled to
3840x2160. Accepts jpg, png, webp, bmp.

### Dimming

The frosted tiles and the white labels need a reasonably dark backdrop, so the
photo is dimmed before they are composited on top.

```bash
./background.py 3                 # automatic — the default
./background.py --darken 0 3      # exactly as shot, no dimming
./background.py --darken 45 3     # dim by 45%
./background.py --darken 100 3    # black
```

**Automatic** measures the mean luminance of the strip the tiles sit on and
dims until it reaches **30** — the level the original Mojave photograph sat at.
Below 5% it does nothing, because a few percent changes nothing and is not
worth touching the photo for.

`--list` reports what each photo measures and what automatic would choose:

```
1. Mars Over Dunes
   Public domain  ·  luminance behind the tiles 31  ·  dark enough as it is
3. Desert Skies
   CC0  ·  luminance behind the tiles 107  ·  suggested --darken 72
```

To change the default, edit `library/library.json`:

```json
"default_darken": "auto"          →  a number from 0 to 100 if you prefer
```

### Preview without installing

```bash
./background.py --preview 5
```

Writes `preview.png` and opens it. Nothing is installed.

---

## If something goes wrong

Installing always keeps a copy of the previous configuration on the ESP:

```bash
ls /boot/efi/EFI/refind/refind.conf.bak-*
sudo cp /boot/efi/EFI/refind/refind.conf.bak-XXXXXX /boot/efi/EFI/refind/refind.conf
```

And whatever happens, **F12** at power-on opens the firmware's own boot menu and
lets you start Windows, bypassing everything.

---

## What not to change without regenerating

The frosted tiles and the "Windows"/"Ubuntu" labels are **baked into
`background.png`** at fixed coordinates derived from rEFInd's layout
arithmetic. So:

- `big_icon_size` and `small_icon_size` in `refind.conf` **must stay** 549 and 48
- if you change them, regenerate with `./build.py`, which recomputes the
  coordinates and stops with an assertion if the spacing no longer works out

Why those two numbers: see *Geometry* in the [README](README.md).
