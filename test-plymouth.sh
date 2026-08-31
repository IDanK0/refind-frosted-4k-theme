#!/usr/bin/env bash
# Boot this machine's kernel and initramfs in a virtual machine and photograph
# the splash. No disk, no root filesystem: the kernel starts, the initramfs runs
# plymouthd, and it waits for a root that will never appear -- which is all the
# time needed to see whether the splash draws.
#
# Written after the splash quietly stopped appearing. The cause was a Description
# wrapped onto a second line in the .plymouth file: Plymouth's key-file reader
# has no continuations, so the group stopped being read there and ModuleName --
# the next line -- was never seen. It loaded "(null).so", fell back to the text
# theme, and said nothing about any of it on the console.
#
#   ./test-plymouth.sh        -> vm/plymouth.png
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VM="$HERE/vm"; K="/boot/vmlinuz-$(uname -r)"; I="/boot/initrd.img-$(uname -r)"
CODE=/usr/share/OVMF/OVMF_CODE_4M.fd; VARS=/usr/share/OVMF/OVMF_VARS_4M.fd
command -v qemu-system-x86_64 >/dev/null || { echo "install qemu-system-x86"; exit 1; }
[ -f "$CODE" ] || { echo "install ovmf"; exit 1; }
[ -f "$K" ] && [ -f "$I" ] || { echo "no kernel or initramfs for $(uname -r)"; exit 1; }
mkdir -p "$VM"
SUDO=(sudo); [ -n "${SUDO_ASKPASS:-}" ] && SUDO=(sudo -A)

# /boot/vmlinuz is not readable by you; copy it where qemu can reach it
"${SUDO[@]}" install -m 0644 -o "$(id -u)" -g "$(id -g)" "$K" "$VM/vmlinuz"
"${SUDO[@]}" install -m 0644 -o "$(id -u)" -g "$(id -g)" "$I" "$VM/initrd"
cp -f "$VARS" "$VM/vars.fd"
rm -f "$VM/mon.sock" "$VM/plymouth.ppm"

# Booted under OVMF so the kernel gets an EFI framebuffer; without one Plymouth
# has no pixel display and falls back to text however good the theme is.
setsid qemu-system-x86_64 -machine q35 -m 3072 -smp 2 \
    -drive if=pflash,format=raw,unit=0,readonly=on,file="$CODE" \
    -drive if=pflash,format=raw,unit=1,file="$VM/vars.fd" \
    -kernel "$VM/vmlinuz" -initrd "$VM/initrd" \
    -append "quiet splash root=/dev/vda1 rootwait" \
    -device VGA,xres=1920,yres=1080,vgamem_mb=64 \
    -display none -monitor unix:"$VM/mon.sock",server,nowait >"$VM/plymouth-qemu.log" 2>&1 &
QPID=$!
sleep 30
printf 'screendump %s/plymouth.ppm\nquit\n' "$VM" | timeout 40 nc -U "$VM/mon.sock" >/dev/null 2>&1 || true
sleep 2; kill $QPID 2>/dev/null || true

python3 - "$VM" <<'PY'
import sys, os
from PIL import Image, ImageStat
vm = sys.argv[1]; src = os.path.join(vm, "plymouth.ppm")
if not os.path.exists(src):
    sys.exit("the virtual machine drew nothing")
im = Image.open(src).convert("RGB"); im.save(os.path.join(vm, "plymouth.png"))
sd = ImageStat.Stat(im.convert("L")).stddev[0]
print(f"  vm/plymouth.png   {im.size[0]}x{im.size[1]}")
if im.size[0] < 1000:
    print("  still in text mode -- no framebuffer, so this proves nothing")
else:
    print(f"  content: {sd:.1f}", "-- the splash drew" if sd > 12 else "-- BLANK")
PY
