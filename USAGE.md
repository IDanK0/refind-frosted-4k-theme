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
dims until it reaches **30**, which is where the photograph this theme was first
built around happened to sit.
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

## New systems and USB sticks

Nothing to do: `scanfor internal,external,optical,manual` means rEFInd looks at
what is attached every time it starts. A bootable stick shows up while it is
plugged in and disappears when it is not. A system installed on another disk
shows up with the right icon and its own name, because all 47 of rEFInd's stock
OS icons have been themed and labelled in advance.

Five entries fit before rEFInd starts scrolling
(`MaxVisible = 3840/(617+8) - 1`).

## The splash

`sudo ./install-plymouth.sh` replaces Ubuntu's spinner with the boot menu
carried on: the same photograph, the same frosted tile holding the logo and the
name of this system, and a ring of dots turning underneath. Rebuild it after
changing the background with `./build.py && ./plymouth.py`, then install again.

The theme reads `/etc/os-release` to choose its icon, so it labels itself
correctly on whatever it is built on. `--os <stem>` overrides that.

To go back to Ubuntu's own splash:

```bash
sudo update-alternatives --set default.plymouth \
     /usr/share/plymouth/themes/bgrt/bgrt.plymouth
sudo update-initramfs -u
```

The installer keeps the working initramfs as `initrd.img-<version>.before-refind-frosted`
before rebuilding.

## What not to change without regenerating

`big_icon_size` (549) and `small_icon_size` (48) in `refind.conf` decide the
size of the frosted plate baked into every icon. If you change them, run
`./build.py` so the icons, the selection highlight and the glass stencil are
redrawn to match.

The picker's **Match colours to the photo** switch draws the logos, the names,
the glass, the tool glyphs and the spinner in a hue read out of the photograph
itself, worked out from the picture rather than looked up, so a photo of your own
gets its own palette. Turning it off puts Windows back to blue and Ubuntu back to
orange. From the command line it is `--tint 0` to `--tint 100`.

`animations` (true) makes the menu arrive, the selection fade across and the
chosen tile travel to the middle instead of jumping. All of it stops the moment a
keystroke is waiting, so holding an arrow key is as fast as it ever was; `false`
turns it off.

`handoff_splash` (1800) is how many milliseconds the chosen system is shown on
its own before rEFInd hands over — the boot logo of everything this machine
boots, since rEFInd is the only thing that runs before all of them. 1800 is one
full turn of the ring; 0 switches it off and hands over immediately.

`frost_radius` (32) is how far the glass scatters what is behind it; 0 switches
the effect off and the plates go back to plain translucency. `frost_mask_big`
names the stencil that says where the glass is — `build.py` writes it as
`frost_big.png` from the same `PLATE` geometry it draws the panels with, so the
two cannot drift apart. Both tokens exist only in the patched binary that
`./build-refind.sh` produces; a stock rEFInd ignores them and everything else
still works.
