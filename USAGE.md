# Usage

Everything the look depends on can be changed from the boot menu itself. The
scripts in this directory regenerate the artwork; nothing about choosing a
background needs an operating system to be running.

---

## From the boot menu

Pick **Settings** in the tool row.

| | |
|---|---|
| **Background** | every picture in `EFI/refind/backgrounds`, in turn |
| **Dimming** | automatic, or 0–80% by hand |
| **Frosted glass** | 0–32, how far the glass scatters what is behind it |
| **Colour from photo** | 0–100%, how far the logos and labels move towards the picture's own colour |
| **Animations** | on or off |
| **Save these for next time** | writes `EFI/refind/theme.conf` |

The panel is drawn as a pane of the same glass the tiles are made of, and so is
every other sub-menu — about, hidden tags, boot options.

Every change takes effect the moment you make it — press Esc and the menu is
already wearing it. Only *Save* makes it survive a reboot.

`theme.conf` is read last by `refind.conf`, so it overrides everything;
**deleting it brings the machine back to exactly what was installed.**

## Adding a photograph of your own

Copy it into `EFI/refind/backgrounds` on the EFI partition. PNG, JPEG or BMP.
That is the whole procedure, and it works from anything that can see the
partition — Linux, Windows, a live USB, some firmware file managers.

It will be themed like the ones that shipped: rEFInd reads the colours off the
picture at boot, so there is nothing to generate and nothing to install.

```bash
sudo mount /dev/nvme0n1p1 /mnt          # if it is not mounted already
sudo cp ~/Pictures/mine.jpg /mnt/EFI/refind/backgrounds/
```

---

## From the command line, to change the shapes

The artwork — the glass, the plates, the forty-seven themed logos, the font, the
spinner's dot — is drawn ahead of time. Its *colours* are not: those come off the
photograph at boot. So these regenerate shapes, not palettes.

```bash
./build.py                                   # redraw everything
./build.py --background ~/Pictures/mine.jpg  # preview against a photo of yours
./build.py --tint 0                          # preview with the original colours
sudo ./install-assets.sh assets              # copy to the EFI partition
```

`install-assets.sh` also copies the library into `EFI/refind/backgrounds`, and
writes a starting `theme.conf` — but only if there is not one there already, so
choices made from the boot menu are never overwritten by a reinstall.

---

## Rebuilding the logos

```bash
./fetch-icons.py            # needs librsvg2-bin and network
```

Rewrites `stock-icons/` from vector sources: the SVGs rEFInd ships, and the
official logo on Wikimedia Commons for the rest. It prints what it could not
find and writes the provenance to `stock-icons/SOURCES.md`. Only needed if you
want to change which logo a system gets.

---

## Before adding a photograph

```bash
./check-photos.py '~/Pictures/*.jpg'
```

Four thousand pixels across is not the same as four thousand pixels of picture.
This measures noise, colour noise, mottling and where the detail actually stops,
on the image as it will be used — cropped to 16:9 and resampled to 3840×2160.

A good photograph reads roughly: noise under 2, chroma under 0.6, mottling under
4, sharpness near 75%. Anything with noise above 3 or sharpness far below 70% has
less picture in it than its pixel count suggests.

---

## Before trusting a build

```bash
./test-vm.sh              # boot it in a virtual machine, photograph the screen
./test-vm.sh --settings   # and open the settings screen while you are there
```

It builds a disk from what is on the real EFI partition, boots it under OVMF,
takes a screenshot and pulls the boot log back out — `vm/shot.png` and
`vm/refind.log`. It says plainly whether the menu drew.

It runs at 3840×2160, which matters: the theme allocates three screen-sized
images at boot, and a test at 1080p asks a quarter of the memory the machine
will. (`--1080` forces the smaller one; `virtio-vga` cannot offer 4K, so the
plain `VGA` device is used with the memory for it.)

The virtual machine holds nothing but the EFI partition — no Linux, no Python,
nothing installed. That it boots, draws the menu and opens the settings screen
is the demonstration that none of those are needed.

Needs `qemu-system-x86` and `ovmf`.

---

## The splash

### The splash follows the menu

`sudo ./install-plymouth.sh` installs two things: the splash itself, built from
whatever photograph the boot menu is showing *now* and at the resolution this
screen actually boots at, and a service that keeps it that way.

The menu can change its photograph at any time, from its own settings screen,
with no operating system running — and the splash lives in an initramfs built
weeks earlier, so it cannot be told. Instead it asks: `refind-splash-sync` reads
`theme.conf` off the EFI partition once per boot, compares it with what the
installed theme was built from, and rebuilds only when they differ. Almost every
boot it finds nothing to do and stops. When you do change the photograph, the
splash matches it from the boot after.

Run `sudo refind-splash-sync` yourself to have it now rather than next time, and
`--force` to rebuild regardless.

**On another system.** Nothing here assumes Debian. The initramfs is rebuilt with
whichever of initramfs-tools and dracut is present, the theme is selected through
`update-alternatives` or `plymouth-set-default-theme`, and the fonts are looked
for rather than assumed. Install a second system tomorrow, run the same script
inside it, and it gets the same splash carrying *its* logo and *its* name, over
the same photograph — because the logo and name come from that system's
`os-release` and the photograph comes from the EFI partition both of them share.

The boot menu's own splash needs none of this: it already shows the right icon,
name and ring for anything it can boot, including a system installed next year,
because it draws them itself. What `install-plymouth.sh` buys is the seconds
*after* the handover, which belong to the system being booted and can only be
arranged from inside it.

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

`log_level` (0) turns on rEFInd's log, written to `EFI\refind\refind.log` on
the EFI partition. At 1 it also records how long each step took after the key
that asked for it — the screen painted, the photograph decoded, the handoff
ready to draw — which is how to find out where a machine that feels slow is
actually spending its time, rather than guessing at it. It costs a file write
per line, so leave it at 0 unless you are measuring.

`fade` (false) cross-fades the whole screen when the menu appears and when it
goes away. It is off because at 3840x2160 one screen is 33 MB and the fade is
eight of them, pushed through the framebuffer before anything is on it: on a real
machine that is the slow wipe from top to bottom. The menu's own entrance, which
is the part you actually watch, is unaffected either way.

`entrance_delay` (0) is how many milliseconds to wait, after the photograph is
up, before the menu arrives. A monitor takes a second or two to lock onto a
signal and shows nothing at all until it has, while the firmware has been
drawing the whole time — so on a slow display the menu's arrival happens
entirely inside that darkness and the first thing you see is a finished menu,
which looks exactly like an animation nobody wrote. This is the beat of
wallpaper before the menu lands on it. A keypress ends the wait immediately.

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
