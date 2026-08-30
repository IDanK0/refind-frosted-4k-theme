#!/usr/bin/env bash
# Install the Plymouth theme and rebuild the initramfs that carries it.
#
# Ubuntu 26.04 no longer ships plymouth-set-default-theme, so the theme is
# selected through update-alternatives, which is what that script did anyway.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "needs root: sudo $0"; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME=refind-frosted
SRC="$HERE/plymouth/$NAME"
DST="/usr/share/plymouth/themes/$NAME"

[ -f "$SRC/$NAME.script" ] || { echo "no theme in $SRC -- run ./plymouth.py first"; exit 1; }
grep -q splash /proc/cmdline || echo "note: the kernel command line has no 'splash'; the splash will not show"

install -d -m 0755 "$DST"
for f in "$SRC"/*; do
    install -m 0644 "$f" "$DST/$(basename "$f")"
done
echo "theme installed to $DST"

update-alternatives --install /usr/share/plymouth/themes/default.plymouth \
                    default.plymouth "$DST/$NAME.plymouth" 200 >/dev/null
update-alternatives --set default.plymouth "$DST/$NAME.plymouth" >/dev/null
echo "default theme is now $(basename "$(readlink -f /usr/share/plymouth/themes/default.plymouth)")"

# The initramfs carries a copy of the theme, so it has to be rebuilt. Keep the
# working one: a half-written initramfs is the one failure here that costs a
# boot, and copying 41 MB is cheaper than finding out.
KVER="$(uname -r)"
IMG="/boot/initrd.img-$KVER"
if [ -f "$IMG" ]; then
    cp -a "$IMG" "$IMG.before-$NAME"
    echo "kept $IMG.before-$NAME"
fi
update-initramfs -u -k "$KVER"
echo
echo "Done. To go back:"
echo "  sudo update-alternatives --set default.plymouth /usr/share/plymouth/themes/bgrt/bgrt.plymouth"
echo "  sudo update-initramfs -u"
