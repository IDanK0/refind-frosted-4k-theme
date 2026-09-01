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

# Where this distribution keeps gnu-efi.
#
# rEFInd's Make.common assumes /usr/lib for all four of these, which is right on
# Debian, Ubuntu, Arch, Void, Alpine and Fedora, and wrong on openSUSE, Gentoo
# and Solus (/usr/lib64) and on RHEL and its rebuilds (/usr/lib64/gnuefi). They
# are plain `=` assignments, so they can simply be overridden, but only if we
# know what to override them with. pkg-config knows, where gnu-efi installs a
# .pc file; RHEL 9 does not ship one, so there is a list to fall back on.
#
# EFICRT0 must hold both crt0-efi-x86_64.o and elf_x86_64_efi.lds; EFILIB must
# hold libgnuefi.a. They are not always the same directory.
find_dir() {
    for c in "$@"; do
        [ -n "$c" ] || continue
        [ -f "$c/crt0-efi-x86_64.o" ] && [ -f "$c/elf_x86_64_efi.lds" ] && { echo "$c"; return 0; }
    done
    return 1
}
find_lib() {
    for c in "$@"; do
        [ -n "$c" ] || continue
        [ -f "$c/libgnuefi.a" ] && { echo "$c"; return 0; }
    done
    return 1
}

PCLIB=$(pkg-config --variable=libdir gnu-efi 2>/dev/null || true)
PCINC=$(pkg-config --variable=includedir gnu-efi 2>/dev/null || true)
SEARCH="$PCLIB /usr/lib /usr/lib64 /usr/lib64/gnuefi /usr/lib/gnuefi /usr/lib/x86_64-linux-gnu /usr/local/lib"
# shellcheck disable=SC2086
EFICRT0=$(find_dir $SEARCH || true)
# shellcheck disable=SC2086
EFILIB=$(find_lib $SEARCH || true)
EFIINC=""
for c in "$PCINC/efi" "$PCINC" /usr/include/efi /usr/local/include/efi; do
    [ -n "$c" ] && [ -f "$c/efilib.h" ] && { EFIINC="$c"; break; }
done

if [ -z "$EFICRT0" ] || [ -z "$EFILIB" ] || [ -z "$EFIINC" ]; then
    echo "missing: gnu-efi (no crt0-efi-x86_64.o + elf_x86_64_efi.lds, libgnuefi.a and efilib.h)"
    MISSING=1
fi

if [ "$MISSING" = 1 ]; then
    cat <<'DEPS'

Install what is missing:
  Debian, Ubuntu, Mint, Pop!_OS   sudo apt install build-essential gnu-efi
  Fedora                          sudo dnf install gcc make binutils gnu-efi gnu-efi-devel
  RHEL, Rocky, Alma 9             sudo dnf install gcc make binutils gnu-efi gnu-efi-devel gnu-efi-compat
                                  (gnu-efi-devel and gnu-efi-compat are in CRB)
  openSUSE                        sudo zypper install gcc make binutils gnu-efi-devel
  Arch, Manjaro, EndeavourOS      sudo pacman -S base-devel gnu-efi
  Void                            sudo xbps-install -S base-devel gnu-efi-libs
  Alpine                          sudo apk add build-base gnu-efi-dev
  Gentoo                          sudo emerge sys-boot/gnu-efi
DEPS
    exit 1
fi
echo "gnu-efi    headers $EFIINC, crt0 $EFICRT0, library $EFILIB"

mkdir -p "$WORK"; cd "$WORK"

# Unpack and patch from scratch every time.
#
# This used to skip everything when build/refind-VER already existed, which is
# fine until that directory is half-patched; an interrupted run, an edited
# file, a patch that was updated since. Then it silently built something nobody
# had described. Downloading again costs one tarball; not knowing what was built
# costs more than that.
if [ ! -f src.tar.gz ]; then
    echo "Fetching rEFInd ${VER}..."
    curl -fsSL --max-time 300 -o src.tar.gz.part "$URL" || { echo "download failed"; exit 1; }
    mv src.tar.gz.part src.tar.gz
fi

# Check it is the tarball this patch was made against, before compiling it into
# the program that starts the machine.
SUMFILE="$HERE/patches/refind-src-${VER}.sha256"
if [ -f "$SUMFILE" ]; then
    WANT=$(grep -v '^#' "$SUMFILE" | awk 'NF{print $1; exit}')
    GOT=$(sha256sum src.tar.gz | awk '{print $1}')
    if [ "$WANT" != "$GOT" ]; then
        echo "The rEFInd tarball is not the one this patch was made against."
        echo "  expected  $WANT"
        echo "  got       $GOT"
        echo
        echo "Refusing to build. Delete $WORK/src.tar.gz and try again; if it keeps"
        echo "happening, upstream has replaced the file and the patch needs checking"
        echo "against the new one before it can be trusted."
        exit 1
    fi
    echo "checksum   ok"
else
    echo "warning: no $SUMFILE; the download was not checked"
fi

rm -rf "refind-${VER}"
tar xzf src.tar.gz
echo "Applying patches/frosted-glass.patch..."
(cd "refind-${VER}" && patch -p1 --forward < "$HERE/patches/frosted-glass.patch") \
    || { echo "the patch did not apply"; exit 1; }

cd "refind-${VER}"
make clean >/dev/null 2>&1 || true
echo "Building..."
make gnuefi EFIINC="$EFIINC" EFICRT0="$EFICRT0" EFILIB="$EFILIB" GNUEFILIB="$EFILIB" >/dev/null
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

# Nothing signs this binary. Replacing a working loader with it on a machine
# whose firmware checks signatures is how a machine stops booting.
SB=unknown
SBVAR=/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c
if [ -r "$SBVAR" ]; then
    case "$(od -An -tu1 -j4 -N1 "$SBVAR" | tr -d ' ')" in 1) SB=on ;; 0) SB=off ;; esac
elif command -v mokutil >/dev/null; then
    mokutil --sb-state 2>/dev/null | grep -qi enabled && SB=on || SB=off
fi
if [ "$SB" = on ]; then
    echo "Secure Boot is ON, and this binary is not signed."
    echo "The firmware will refuse to start it. Refusing to install over a loader"
    echo "that currently works. Turn Secure Boot off, or enrol this binary's hash:"
    echo "    sudo mokutil --import-hash $(sha256sum refind/refind_x64.efi | awk '{print $1}')"
    exit 1
fi
[ "$SB" = unknown ] && echo "warning: could not read the Secure Boot state"

# ./setup.sh is the supported way in: it installs into a directory of its own,
# adds a boot entry rather than replacing one, and can undo itself.
echo "note: ./setup.sh installs this without overwriting anything. This --install"
echo "      replaces the binary in $ESP, which is only right if that is already ours."

# Keep a copy of the unpatched binary to fall back to, but only if the one
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
