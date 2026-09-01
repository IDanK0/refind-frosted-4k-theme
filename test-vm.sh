#!/usr/bin/env bash
# Boot this bootloader in a virtual machine and photograph the screen.
#
# Written after shipping a build that hung before it drew the menu. The fault
# was a loop that never ended on a negative number, and it took one run of this
# to find -- against a reboot, a guess, and a broken machine to find nothing.
#
#   ./test-vm.sh              boot and screenshot        -> vm/shot.png
#   ./test-vm.sh --settings   also open the settings screen
#
# Needs qemu-system-x86 and ovmf. Root is asked for once, to loop-mount the
# image being built; the virtual machine itself runs as you.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VM="$HERE/vm"

# Where the menu is installed. setup.sh puts it in EFI/refind-frosted-4k-theme unless a
# build of this was already in EFI/refind; hard-coding the second meant this
# harness refused to run on any machine installed the ordinary way.
ESP=""
for root in /boot/efi /efi /boot; do
    for name in refind-frosted-4k-theme refind; do
        [ -f "$root/EFI/$name/refind_x64.efi" ] && { ESP="$root/EFI/$name"; break 2; }
    done
done
CODE=/usr/share/OVMF/OVMF_CODE_4M.fd
VARS=/usr/share/OVMF/OVMF_VARS_4M.fd

command -v qemu-system-x86_64 >/dev/null || { echo "install qemu-system-x86"; exit 1; }
[ -f "$CODE" ] || { echo "install ovmf"; exit 1; }
[ -d "$ESP" ] || { echo "no rEFInd at $ESP"; exit 1; }
mkdir -p "$VM"

# Plain sudo prompts, which is right; honour an askpass helper if one is set.
SUDO=(sudo)
[ -n "${SUDO_ASKPASS:-}" ] && SUDO=(sudo -A)

# A disk holding what is on the real EFI partition, with rEFInd as the default
# loader so the firmware starts it without a boot entry, and two loaders copied
# in so the menu has something to draw.
"${SUDO[@]}" bash -c '
set -euo pipefail
IMG="'"$VM"'/esp.img"; rm -f "$IMG"; truncate -s 240M "$IMG"
mkfs.vfat -F 32 -n TESTESP "$IMG" >/dev/null
M=$(mktemp -d); mount -o loop "$IMG" "$M"
mkdir -p "$M/EFI/BOOT"
cp -a '"$ESP"'/. "$M/EFI/BOOT/"
mv "$M/EFI/BOOT/refind_x64.efi" "$M/EFI/BOOT/BOOTX64.EFI"
rm -f "$M/EFI/BOOT"/refind_x64.efi.* "$M/EFI/BOOT/refind.log"
for pair in "ubuntu grubx64.efi" "Microsoft/Boot bootmgfw.efi"; do
    set -- $pair
    if [ -f "/boot/efi/EFI/$1/$2" ]; then
        mkdir -p "$M/EFI/$1"; cp "/boot/efi/EFI/$1/$2" "$M/EFI/$1/$2"
    fi
done
# the virtual display tops out below 4K, and the log is the point of the exercise
sed -i "s/^resolution .*/resolution 3840 2160/;s/^timeout .*/timeout 120/;s/^log_level .*/log_level 3/" \
    "$M/EFI/BOOT/refind.conf"
grep -q "^log_level" "$M/EFI/BOOT/refind.conf" || echo "log_level 3" >> "$M/EFI/BOOT/refind.conf"
sync; umount "$M"; rmdir "$M"
chown '"$(id -u):$(id -g)"' "$IMG"'

# virtio-vga will not offer 3840x2160; the plain VGA device will, given the
# memory for it. The theme allocates three screen-sized images, so testing at
# the resolution the machine actually runs at is the point.
# Either flag, in either order. This used to read --1080 out of $2 only, so
# `./test-vm.sh --1080` -- the form the documentation gave -- silently ran at 4K.
VIDEO="VGA,xres=3840,yres=2160,vgamem_mb=64"
WANT_SETTINGS=0
for arg in "$@"; do
    case "$arg" in
        --1080)     VIDEO="virtio-vga,xres=1920,yres=1080" ;;
        --settings) WANT_SETTINGS=1 ;;
        *) echo "unknown option: $arg (try --settings, --1080)"; exit 2 ;;
    esac
done

cp -f "$VARS" "$VM/vars.fd"
rm -f "$VM/mon.sock" "$VM"/shot*.ppm
setsid qemu-system-x86_64 -machine q35 -m 2048 -smp 2 \
    -drive if=pflash,format=raw,unit=0,readonly=on,file="$CODE" \
    -drive if=pflash,format=raw,unit=1,file="$VM/vars.fd" \
    -drive format=raw,file="$VM/esp.img" \
    -device "$VIDEO" \
    -display none -monitor unix:"$VM/mon.sock",server,nowait >"$VM/qemu.log" 2>&1 &
QPID=$!
sleep 16
{
    if [ "$WANT_SETTINGS" = 1 ]; then
        echo "sendkey down"; sleep 1; echo "sendkey right"; sleep 1
        echo "sendkey ret";  sleep 3
    fi
    echo "screendump $VM/shot.ppm"; sleep 2
    echo "quit"
} | timeout 90 nc -U "$VM/mon.sock" >/dev/null 2>&1 || true
sleep 2; kill $QPID 2>/dev/null || true

python3 - "$VM" <<'PY'
import sys, os
from PIL import Image, ImageStat
vm = sys.argv[1]
src = os.path.join(vm, "shot.ppm")
if not os.path.exists(src):
    sys.exit("the virtual machine drew nothing")
im = Image.open(src).convert("RGB")
im.save(os.path.join(vm, "shot.png"))
band = im.crop((0, int(im.height * .33), im.width, int(im.height * .75)))
sd = ImageStat.Stat(band.convert("L")).stddev[0]
print(f"  vm/shot.png   {im.size[0]}x{im.size[1]}")
print(f"  content in the tile band: {sd:.1f}", end="  ")
print("-- the menu drew" if sd > 20 else "-- EMPTY: the menu did not draw")
PY

"${SUDO[@]}" bash -c 'M=$(mktemp -d); mount -o loop "'"$VM"'/esp.img" "$M"
if [ -f "$M/EFI/BOOT/refind.log" ]; then
    iconv -f UTF-16LE -t UTF-8 "$M/EFI/BOOT/refind.log" > "'"$VM"'/refind.log" 2>/dev/null || true
    chown '"$(id -u):$(id -g)"' "'"$VM"'/refind.log"
fi
umount "$M"; rmdir "$M"'
[ -f "$VM/refind.log" ] && echo "  vm/refind.log  $(wc -l < "$VM/refind.log") lines"
