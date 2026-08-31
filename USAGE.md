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
