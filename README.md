# rEFInd Mojave — DESKTOP

A native-4K boot menu for a Windows 11 / Ubuntu dual-boot machine, built on
[rEFInd](https://www.rodsbooks.com/refind/). Frosted-glass tiles over the Mojave
dune, crisp text at 3840×2160, and no input lag.

![Boot menu](screenshots/menu.png)

> The images in this README are **renders**, not photographs: they are produced by
> `build.py` from the exact same asset files and rEFInd's own layout arithmetic, so
> they are pixel-faithful to what the firmware draws. Photographing a boot screen
> gives a worse picture than the maths does.

---

## Why not GRUB

This theme started as a GRUB theme and had to be abandoned. The reason is
worth recording, because it is not obvious.

GRUB's `gfxmenu` is **entirely software-rendered**. Every repaint is written by
the CPU into the firmware's framebuffer across the PCIe bus, with no
acceleration. At 3840×2160 that is 8.3 million pixels — 31.6 MB — per full
repaint, four times the cost of 1080p.

The visible symptom was not just sluggishness. While GRUB is busy repainting it
is **not reading the keyboard**, so the firmware's key auto-repeat keeps firing
and the events queue up. One press of the arrow key moved the selection *two*
entries. Lowering the resolution fixed it, which is what proved the cause.

rEFInd does not have this problem because of a single architectural difference,
visible in `refind/menu.c`:

```c
static VOID DrawMainMenuEntry(REFIT_MENU_ENTRY *Entry, BOOLEAN selected,
                              UINTN XPos, UINTN YPos) {
    Background = egCropImage(GlobalConfig.ScreenBackground, XPos, YPos, ...);
```

On a selection change it **crops and repaints only the affected tile**, not the
screen. That is why it stays responsive at native 4K where GRUB cannot.

---

## Design notes

**The frosted glass is baked, not live.** A real frosted panel samples and blurs
what is behind it every frame; a UEFI application has no compositor, no shader
and no frame loop, so that is impossible. But the background is a fixed image and
the tiles sit at fixed coordinates, so the blur is computed *once* in `build.py`
— a real Gaussian blur of the dune, brightened, with a cool veil, a raking-light
gradient and a soft drop shadow — and composited into `background.png`. At
runtime it costs nothing: it is just a PNG.

**The `Windows` / `Ubuntu` labels are baked too.** rEFInd's own label mechanism
cannot be used for them (see *Gotchas* below), so they live in the background
image at coordinates derived from rEFInd's layout formulas. This works because
`DrawTextWithTransparency()` restores that band *from the background image*, so
anything baked there survives every repaint.

**Nothing is ever upscaled.** Every asset is drawn larger than it is used and let
rEFInd shrink it. Downscaling stays sharp; upscaling does not.

---

## Geometry

Every number below is derived, not chosen. `build.py` recomputes them and
**asserts** the spacing is symmetric before it writes a single file.

| Quantity | Formula (`refind/menu.c`) | Value |
|---|---|---|
| `TileSizes[0]` | `big_icon_size * 9 / 8` | 617 |
| `TileSizes[1]` | `small_icon_size * 4 / 3` | 64 |
| `row0PosY` | `UGAHeight/2 - TileSizes[0]/2` | 772 |
| `row0PosX` | `(W + 8 - (TileSizes[0]+8)*2) / 2` | 1299 |
| `row1PosY` | `row0PosY + TileSizes[0] + 16` | 1405 |
| `textPosY` | `row1PosY + TileSizes[1] + 16` | 1485 |
| Tile centres | — | 1607, 2232 |

`big_icon_size = 549` is **not an aesthetic choice**. The OS row is always
centred vertically and the tool row hangs off it, so the only way to place the
tool row *below* the baked labels — instead of on top of them — is to inflate the
OS tile. 549 is the value that yields exactly **52 px above and 52 px below** the
labels. The logos stay 218 px because they are drawn inside mostly-transparent
1098 px canvases: the tile is a bounding box, not the artwork.

Two hard limits constrain it:

- `MaxVisible = UGAWidth / (TileSizes[0] + 8) - 1` must stay ≥ 2, otherwise
  rEFInd shows one OS icon at a time with scrolling. That caps
  `big_icon_size` at 1130.
- `TILE_XSPACING` is `#define`d to 8 px. Tiles always touch; visual separation
  has to come from transparent margins inside the artwork.

---

## Requirements

- rEFInd **0.14.x** (`apt install refind`)
- Python 3 with Pillow (`python3-pil`) — only to regenerate assets
- A display running at 3840×2160 in firmware (check with `videoinfo` at the
  rEFInd shell if unsure)
- **Secure Boot disabled**, unless you sign rEFInd yourself
- DejaVu fonts (`fonts-dejavu-core`) for regeneration

---

## Install

```bash
git clone <this repo> && cd refind-mojave-desktop
sudo ./install.sh
```

`install.sh` backs up your current `refind.conf` and drops the assets into
`/boot/efi/EFI/refind/`. It refuses to run if rEFInd is not installed there.

Edit the two `menuentry` blocks in `refind.conf` to match your own loader paths
before installing.

---

## Customising

All constants live at the top of `build.py`:

```python
BIG=549    # big_icon_size
SMALL=48   # small_icon_size
PLATE=340  # frosted tile, px
LOGO_VIS=218
F_OS=66    # label font size
```

Change one, run `python3 build.py`, and every asset plus the preview render is
rebuilt. If the spacing no longer works out, the script stops with an assertion
rather than producing something subtly wrong.

**If you change `big_icon_size` or `small_icon_size` you must regenerate**, because
the glass tiles and the labels are baked into `background.png` at fixed
coordinates that depend on both.

---

## Gotchas

Everything here was found by reading rEFInd's source after the obvious
explanation turned out to be wrong.

**1. The font is inverted on dark backgrounds.** `libeg/text.c`:

```c
if (BGBrightness < 128) {
   LightFontImage->PixelData[i].r = 255 - LightFontImage->PixelData[i].r;
```

rEFInd expects **black** glyphs and inverts them itself. Supply white glyphs and
you get black, unreadable text. `build.py` draws them at 95 so they render at 160
— a soft grey.

**2. Menu entry titles are hardcoded.** `config.c:964`:

```c
Entry->me.Title = PoolPrint(L"Boot %s from %s", Title, CurrentVolume->VolName);
```

A manual stanza titled `Windows` displays as *"Boot Windows from &lt;volume&gt;"*.
No configuration option changes this. The volume name is the **GPT partition
name** of the ESP, so the only lever is renaming that partition:
`sgdisk -c 1:"NAME" /dev/nvme0n1` (cosmetic and safe — partitions are identified
by GUID, never by name; back the table up with `sgdisk --backup` first).

**3. `hideui label` also hides the countdown.** Both live behind the same guard,
so hiding the long titles also removes *"Booting in N seconds"*. Raise `timeout`
to compensate.

**4. `showtools` does not do what it says on this build.** The branch runs — it
sets `HiddenTags = FALSE`, observably removing the *Manage Hidden Tags* entry —
but the `SetMem()` that should zero the tool table has no effect, so the default
tools appear regardless of the argument. Unresolved. Work with the five default
tools rather than against them.

**5. Icons are upscaled without warning.** `big_icon_size 256` against a 128 px
icon file silently doubles it and it looks soft. Always ship art at or above the
configured size.

**6. On Ubuntu, `recordfail` overrides `GRUB_TIMEOUT`.** If GRUB is chainloaded as
a silent pass-through, an interrupted boot leaves `recordfail=1` in `grubenv`
and `/etc/grub.d/00_header` then forces a 30-second visible menu. Set
`GRUB_RECORDFAIL_TIMEOUT=0`.

**7. Config paths have two different bases.** `banner`, `font` and `selection_*`
are relative to the directory holding `refind_x64.efi`; `icon` inside a
`menuentry` is absolute from the ESP root. Mixing them up fails **silently** —
the file is simply never loaded.

---

## Uninstall

```bash
sudo cp /boot/efi/EFI/refind/refind.conf.bak-* /boot/efi/EFI/refind/refind.conf
```

To remove rEFInd entirely and return to GRUB:

```bash
sudo efibootmgr -o <ubuntu>,<windows>   # reorder, see efibootmgr -v
sudo apt purge refind
```

---

## Credits & licensing

- [rEFInd](https://www.rodsbooks.com/refind/) by Roderick W. Smith — GPLv3
- The dune photograph is Apple's *Mojave* wallpaper, taken from
  [Elegant-grub2-themes](https://github.com/vinceliuice/Elegant-grub2-themes)
  (GPLv3). **It is not freely licensed.** Replace `dune-src.jpeg` before
  publishing this repository or distributing the built assets.
- Icons, fonts, glass and layout in this repository are generated by `build.py`.
