# What this project is made of, and under what terms

`refind-frosted-4k-theme` is published under the **GNU General Public License, version 3**
(`LICENSE`). It has to be: the boot menu is rEFInd with a patch applied, and
rEFInd is GPLv3. The generators, the installers and the Plymouth theme are
released under the same licence so that the whole thing is one work with one
answer.

Nothing here is original photography, and none of the logos are ours. What
follows is the complete list of what was borrowed and from whom, because a
licence that asks for credit is a licence that has to be honoured, not a badge.

## The boot menu

* **rEFInd 0.14.2**, by Roderick W. Smith. GPLv3, with the files inherited from
  rEFIt under Christoph Pfisterer's three-clause BSD licence (both texts are in
  the rEFInd source tarball, which `setup.sh` downloads). This project ships a
  patch, `patches/frosted-glass.patch`, not a copy of rEFInd; `setup.sh`
  downloads the tarball, checks it against `patches/refind-src-0.14.2.sha256`,
  and applies the patch to it.
* Support code inside rEFInd is borrowed in turn from the TianoCore EDK2 and
  from the Linux kernel; rEFInd's own `CREDITS.txt` is the authority on that.

## The photographs

Six, all from Wikimedia Commons, all free to redistribute. `library/library.json`
records the licence, the author and the source URL of each one, and that file is
the authority; this table is a copy of it.

| Photograph | Author | Licence |
|---|---|---|
| Mars Over Dunes | Great Sand Dunes National Park and Preserve | Public domain |
| Clear Desert Night Sky | Jared Evans | CC0 |
| Desert Skies | Jared Evans | CC0 |
| Dune 45 at Sunrise | Giles Laurent | CC BY-SA 4.0 |
| Namib Dune Formations | Sonse | CC BY 2.0 |
| Dunes, Crestone Peaks and Stars | Great Sand Dunes National Park and Preserve | CC BY 2.0 |

One of them is **share-alike**: *Dune 45 at Sunrise*, CC BY-SA 4.0. A modified
copy of it carries that licence with it, and the boot menu's `background.png` is
exactly such a copy, darkened, blurred and composited. The other five ask only
for credit, or nothing at all.

No generated artwork is kept in this repository. `background.png`, the icons,
the frosted panel and the Plymouth theme are all built on the machine they are
installed on, from `library/` and `build.py`. That is what lets the theme fit
the screen it finds and the photograph you pick, and which means the question of
what licence a particular generated `background.png` carries is answered by
which photograph you built it from. Build it from *Dune 45 at Sunrise* and it is
CC BY-SA 4.0; build it from the default, *Mars Over Dunes*, and it is public
domain.

Two things are the exception, and both are checked in:

* `screenshots/`, built from *Mars Over Dunes*, which is public domain, except
  `library.png`, which is the whole library side by side and therefore contains
  all six, the share-alike one included. `windows-handoff.png` carries no
  photograph at all: it is the icon on black, and the only thing it takes from a
  picture is the colour it is tinted with.
* `library/preview-sheet.jpg`, a contact sheet of the library, so it too
  contains all six. It is not installed on any machine; it is there so the
  README can show what the library looks like.

## The logos

`stock-icons/SOURCES.md` records, for every icon, whether it came from rEFInd's
own SVG set or from Wikimedia Commons, and for the ones from Commons, under
which licence. The ones from rEFInd's own set are covered by rEFInd's licence.
Seventeen are still rEFInd's 128-pixel bitmaps because no vector of them exists
anywhere.

Distribution logos are trademarks of their projects. They are used here only to
name the system they belong to, which is what a boot menu is for and what every
boot menu does.

## The type

The labels, and every glyph in `font.png`, are rendered from DejaVu Sans:
public domain and Bitstream Vera Fonts Copyright, which permits exactly this.
The Plymouth splash asks for the *Ubuntu* font by name at run time and falls back
to whatever the system has; it bundles no font.

## The splash

**Plymouth** is not bundled or modified. The theme this project generates is a
plain `script` theme in `/usr/share/plymouth/themes`, which is where Plymouth
looks for one.
