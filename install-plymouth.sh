#!/usr/bin/env bash
# Install the splash, and arrange for it to keep itself right.
#
# Two halves. The theme itself is built from whatever photograph the boot menu
# is currently showing, at the resolution this screen actually boots at. And a
# small service is installed that checks, once per boot, whether the menu's
# photograph has changed since -- because it can, at any time, from the menu's
# own settings screen, with no operating system running -- and rebuilds the
# theme when it has.
#
# It does not assume Debian. The initramfs is rebuilt with whichever of
# initramfs-tools and dracut this system has, and the theme is selected through
# update-alternatives where that exists and plymouth-set-default-theme where it
# does not. Which is what makes it installable on the next system as well as
# this one: run it inside Fedora and Fedora gets the same splash, with Fedora's
# own logo and name, following the same photograph.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "needs root: sudo $0"; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME=refind-frosted
DST="/usr/share/plymouth/themes/$NAME"
LIB="/usr/local/share/$NAME"
BIN="/usr/local/bin/refind-splash-sync"

command -v python3 >/dev/null || { echo "needs python3"; exit 1; }
python3 -c "import PIL" 2>/dev/null || {
    echo "needs Pillow: apt install python3-pil, or dnf install python3-pillow"
    exit 1
}
grep -q splash /proc/cmdline || \
    echo "note: the kernel command line has no 'splash'; the splash will not show"

# What the theme is built from, so the machine can rebuild it later without this
# checkout. The photographs are not copied: they are already on the EFI
# partition, which is where the boot menu keeps them and where it reads them
# from, and there is no reason for a second copy of 100 MB of desert.
echo "generator  $LIB"
install -d -m 0755 "$LIB" "$LIB/stock-icons" "$LIB/library"
install -m 0644 "$HERE/build.py" "$HERE/plymouth.py" "$LIB/"
install -m 0644 "$HERE"/stock-icons/*.png "$LIB/stock-icons/"
install -m 0644 "$HERE/library/library.json" "$LIB/library/"
install -m 0755 "$HERE/splash-sync.py" "$BIN"

# The initramfs carries a copy of the theme, so it has to be rebuilt. Keep the
# working one: a half-written initramfs is the one failure here that costs a
# boot, and copying 41 MB is cheaper than finding out.
for img in "/boot/initrd.img-$(uname -r)" "/boot/initramfs-$(uname -r).img"; do
    if [ -f "$img" ]; then
        cp -a "$img" "$img.before-$NAME"
        echo "kept       $img.before-$NAME"
    fi
done

# Build and install it, at this screen's size, from the menu's own photograph.
"$BIN" --force

# Make it the theme that shows.
if command -v update-alternatives >/dev/null; then
    update-alternatives --install /usr/share/plymouth/themes/default.plymouth \
                        default.plymouth "$DST/$NAME.plymouth" 200 >/dev/null
    update-alternatives --set default.plymouth "$DST/$NAME.plymouth" >/dev/null
elif command -v plymouth-set-default-theme >/dev/null; then
    plymouth-set-default-theme "$NAME"
else
    echo "could not select the theme: no update-alternatives, no plymouth-set-default-theme"
    exit 1
fi
echo "theme      $(basename "$(readlink -f /usr/share/plymouth/themes/default.plymouth 2>/dev/null || echo "$NAME")")"

# And keep it following the menu from now on.
if command -v systemctl >/dev/null && [ -d /etc/systemd/system ]; then
    install -m 0644 "$HERE/$NAME-sync.service" "/etc/systemd/system/$NAME-sync.service"
    systemctl daemon-reload
    systemctl enable "$NAME-sync.service" >/dev/null
    echo "service    $NAME-sync.service enabled: follows the menu from now on"
else
    echo "service    no systemd here; run $BIN yourself after changing the photograph"
fi

echo
echo "Done. To go back:"
echo "  sudo systemctl disable $NAME-sync.service"
echo "  sudo update-alternatives --set default.plymouth /usr/share/plymouth/themes/bgrt/bgrt.plymouth"
echo "  sudo update-initramfs -u   # or: sudo dracut --force --regenerate-all"
