#!/usr/bin/env bash
#
# Build rEFInd with real frosted glass.
#
# A translucent panel drawn into an icon cannot blur what is behind it: the icon
# is generated long before anyone knows where rEFInd will place it. But rEFInd
# already crops the background to the exact tile before painting an entry, so
# the blur can be done there, at draw time — correct for any number of entries,
# at any position. patches/frosted-glass.patch adds it, along with a
# `frost_radius` configuration token.
#
# The patch also fixes three things that stop rEFInd 0.14.2 building on a
# current toolchain:
#   * gnu-efi changed the ReallocatePool ABI  -> -DGNU_EFI_USE_REALLOCATEPOOL_ABI=0
#   * gnu-efi now provides AsciiStrLen        -> rEFInd's copy is compiled out
#   * binutils dropped the efi-app-x86_64 target -> objcopy -O pei-x86-64 --subsystem=10
#
# Usage:  ./build-refind.sh            build only, leaves the binary in build/
#         ./build-refind.sh --install  build, back up the current one, install
set -euo pipefail

VER=0.14.2
URL="https://sourceforge.net/projects/refind/files/${VER}/refind-src-${VER}.tar.gz/download"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$HERE/build"
ESP=/boot/efi/EFI/refind

need() { command -v "$1" >/dev/null || { echo "missing: $1"; MISSING=1; }; }
MISSING=0
need gcc; need make; need objcopy; need patch; need curl
[ -f /usr/lib/crt0-efi-x86_64.o ] || { echo "missing: gnu-efi"; MISSING=1; }
if [ "$MISSING" = 1 ]; then
    echo
    echo "Install them with:  sudo apt install build-essential gnu-efi"
    exit 1
fi

mkdir -p "$WORK"; cd "$WORK"
if [ ! -d "refind-${VER}" ]; then
    echo "Fetching rEFInd ${VER}..."
    curl -fsSL --max-time 300 -o src.tar.gz "$URL"
    tar xzf src.tar.gz
    echo "Applying patches/frosted-glass.patch..."
    (cd "refind-${VER}" && patch -p1 < "$HERE/patches/frosted-glass.patch")
fi

cd "refind-${VER}"
make clean >/dev/null 2>&1 || true
echo "Building..."
make gnuefi >/dev/null
[ -f refind/refind_x64.efi ] || { echo "build failed"; exit 1; }
SIZE=$(stat -c%s refind/refind_x64.efi)
echo "Built refind_x64.efi (${SIZE} bytes)"

if [ "${1:-}" != "--install" ]; then
    echo
    echo "Not installed. To install:  sudo $0 --install"
    echo "Binary is at: $PWD/refind/refind_x64.efi"
    exit 0
fi

[ "$(id -u)" -eq 0 ] || { echo "Installing needs root: sudo $0 --install"; exit 1; }
[ -d "$ESP" ] || { echo "rEFInd not found at $ESP"; exit 1; }

# Keep a copy of the unpatched binary to fall back to -- but only if the one
# currently installed really is unpatched. rEFInd's config tokens live in the
# binary as EFI (UTF-16LE) strings, so a patched build is recognisable by
# carrying "frost_radius"; saving that as the fallback would defeat the point.
FROST=$(printf 'frost_radius' | sed 's/./&\\x00/g')
BACKUP=""
for c in "$ESP"/refind_x64.efi.stock "$ESP"/refind_x64.efi.pacchetto; do
    [ -f "$c" ] && { BACKUP="$c"; break; }
done
if [ -z "$BACKUP" ]; then
    if grep -qaP "$FROST" "$ESP/refind_x64.efi"; then
        echo "Note: the installed binary is already patched, and there is no"
        echo "      unpatched copy to fall back to. Get one with:"
        echo "         apt-get download refind && dpkg-deb -x refind_*.deb /tmp/r"
        echo "      then keep /tmp/r/usr/share/refind/refind_x64.efi somewhere safe."
    else
        cp "$ESP/refind_x64.efi" "$ESP/refind_x64.efi.stock"
        BACKUP="$ESP/refind_x64.efi.stock"
        echo "Kept the distribution binary as refind_x64.efi.stock"
    fi
else
    echo "Fallback binary already present: $(basename "$BACKUP")"
fi
install -m 0755 refind/refind_x64.efi "$ESP/refind_x64.efi"
echo "Installed."
echo
echo "Add 'frost_radius 32' to refind.conf to switch the effect on."
[ -n "$BACKUP" ] && echo "To go back:  sudo cp $BACKUP $ESP/refind_x64.efi"
