#!/usr/bin/env bash
#
# refind-frosted: install the boot menu, and the splash that carries on from it.
#
# One command. It looks at the machine first and prints everything it is going to
# do; nothing is written until you have seen that list. Every write is recorded,
# before it happens, in a journal on disk, so `--uninstall` can put the machine
# back even if this script is killed halfway through.
#
#   sudo ./setup.sh                 look, show the plan, ask, install
#   sudo ./setup.sh --dry-run       show the plan and stop
#   sudo ./setup.sh --yes           don't ask
#   sudo ./setup.sh --status        what is installed
#   sudo ./setup.sh --uninstall     put everything back
#
# The rules it will not break:
#
#   * It never overwrites another bootloader. Its files go in a directory of
#     their own, and the firmware is given a new entry rather than an edited one.
#   * The first install sets BootNext, not BootOrder -- the machine tries this
#     once and goes back to booting the way it always did if anything is wrong.
#     `--permanent`, or `sudo ./setup.sh --promote` afterwards, makes it stick.
#   * It never writes EFI/BOOT/BOOTX64.EFI on an internal disk. That path is the
#     firmware's own fallback, and taking it from a machine that needs it is how
#     a machine stops booting.
#   * The boot menu and the splash are committed separately. If the splash fails
#     the menu is still installed and working, and the initramfs is put back.
set -uo pipefail

VERSION=1.0
NAME=refind-frosted
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE=/var/lib/$NAME
JOURNAL=$STATE/journal
ARCH_EFI=x64

# ------------------------------------------------------------------ options
DO=install; ASSUME_YES=0; DRY=0; WANT_SPLASH=1; WANT_MENU=1
ESP=""; ESP_DIR=""; PERMANENT=0; BACKGROUND=""; INSTALL_DEPS=0; ENTRY_MADE=0

usage() {
    # Everything from the third line to the first line that is not a comment,
    # rather than a hand-counted range -- which had already drifted and was
    # cutting the last rule off in the middle of a sentence.
    sed -n '3,/^[^#]/p' "$0" | sed '/^[^#]/d; s/^# \{0,1\}//'
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)    DRY=1 ;;
        -y|--yes)     ASSUME_YES=1 ;;
        --uninstall)  DO=uninstall ;;
        --status)     DO=status ;;
        --promote)    DO=promote ;;
        --no-splash)  WANT_SPLASH=0 ;;
        --no-menu)    WANT_MENU=0 ;;
        --permanent)  PERMANENT=1 ;;
        --install-deps) INSTALL_DEPS=1 ;;
        --esp)        ESP="${2:?--esp needs a path}"; shift ;;
        --dir)        ESP_DIR="${2:?--dir needs a name}"; shift ;;
        --background) BACKGROUND="${2:?--background needs a filename}"; shift ;;
        -h|--help)    usage ;;
        *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
    esac
    shift
done

# ------------------------------------------------------------------- output
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    B=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; YEL=$'\033[33m'; GRN=$'\033[32m'; Z=$'\033[0m'
else
    B=""; DIM=""; RED=""; YEL=""; GRN=""; Z=""
fi
say()  { printf '%s\n' "$*"; }
head2() { printf '\n%s%s%s\n' "$B" "$*" "$Z"; }
note() { printf '  %s\n' "$*"; }
warn() { printf '  %s!%s %s\n' "$YEL" "$Z" "$*"; }
bad()  { printf '  %sx%s %s\n' "$RED" "$Z" "$*"; }
good() { printf '  %s+%s %s\n' "$GRN" "$Z" "$*"; }
die()  { printf '\n%serror%s %s\n' "$RED" "$Z" "$*" >&2; exit 1; }

# ------------------------------------------------------------------ journal
#
# Written before the action it describes, and flushed, so that a machine which
# loses power between the journal line and the action itself is left with a
# journal that claims slightly more than was done -- which is the safe direction
# to be wrong in, because undoing something that never happened is harmless and
# failing to undo something that did is not.
record() {
    [ "$DRY" = 1 ] && return 0
    mkdir -p "$STATE"
    printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$JOURNAL"
    sync -f "$JOURNAL" 2>/dev/null || sync
}

# The same, for a batch: one flush at the end rather than one per line. Used for
# the fifty-odd icons and the photographs, which are written in one go -- a
# separate fsync each would be fifty flushes to record fifty copies.
record_batch() {
    [ "$DRY" = 1 ] && return 0
    mkdir -p "$STATE"
    local now; now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local line
    for line in "$@"; do
        printf '%s\t%s\n' "$now" "$line" >> "$JOURNAL"
    done
    sync -f "$JOURNAL" 2>/dev/null || sync
}

# ------------------------------------------------------------------- facts
ESP_CANDIDATES=""; SECUREBOOT=""; FW_BITS=""; DISTRO=""; DISTRO_NAME=""
PKG=""; PKG_INSTALL=""; INITRAMFS=""; SCREEN=""
MISSING_PKGS=""; ESP_FREE=0; BOOT_FREE=0; PLYMOUTH=0

esp_type_guid=C12A7328-F81F-11D2-BA4B-00A0C93EC93B

find_esps() {
    # Every mounted vfat filesystem whose partition really is an ESP, plus the
    # conventional mount points, deduplicated by device. Partition type is what
    # decides -- a vfat filesystem at /boot/efi is not an ESP just because of
    # where somebody mounted it.
    local out="" seen="" src tgt ptype
    while read -r src tgt; do
        [ -n "$src" ] || continue
        # findmnt -r escapes anything awkward in a path as \x20 and friends;
        # printf %b turns those back into the characters they stand for, so a
        # partition mounted at "/boot/EFI System" is still found.
        tgt=$(printf '%b' "$tgt")
        # findmnt has no column for the partition type, so ask lsblk about the
        # device it named. The type is what decides: a vfat filesystem mounted
        # at /boot/efi is not an EFI System Partition just because of where it
        # was mounted, and the one that matters may be mounted somewhere else.
        ptype=$(lsblk -no PARTTYPE "$src" 2>/dev/null | head -1 | tr -d ' ')
        if [ "${ptype^^}" = "$esp_type_guid" ] || [ "$ptype" = "0xef" ]; then
            # One entry per *partition*. The same ESP mounted twice -- a bind
            # mount, or /boot/efi and /efi both pointing at it -- is one EFI
            # partition, and reporting it as two would stop the install for a
            # conflict that does not exist.
            case " $seen " in *" $src "*) continue ;; esac
            seen="$seen $src"
            out="$out
$tgt"
        fi
    done < <(findmnt -rn -t vfat -o SOURCE,TARGET 2>/dev/null)
    printf '%s' "${out#
}"
}

detect_distro() {
    # In a subshell. /etc/os-release sets NAME, and NAME here is the name of this
    # project -- sourcing it directly renamed everything the installer writes,
    # from /usr/share/plymouth/themes/refind-frosted to .../Ubuntu.
    local id pretty like
    id=$(     . /etc/os-release 2>/dev/null; printf '%s' "${ID:-unknown}")
    pretty=$( . /etc/os-release 2>/dev/null; printf '%s' "${PRETTY_NAME:-${NAME:-unknown}}")
    like=$(   . /etc/os-release 2>/dev/null; printf '%s' "${ID_LIKE:-}")
    DISTRO="$id"; DISTRO_NAME="$pretty"
    case "$DISTRO $like" in
        *debian*|*ubuntu*) PKG=apt ;;
        *fedora*|*rhel*|*centos*) PKG=dnf ;;
        *suse*)            PKG=zypper ;;
        *arch*)            PKG=pacman ;;
        *alpine*)          PKG=apk ;;
        *void*)            PKG=xbps ;;
        *gentoo*)          PKG=emerge ;;
        *) for p in apt dnf zypper pacman apk xbps-install emerge; do
               command -v $p >/dev/null && { PKG="${p%-install}"; break; }
           done ;;
    esac
    case "$PKG" in
        apt)    PKG_INSTALL="apt-get install -y --no-install-recommends" ;;
        dnf)    PKG_INSTALL="dnf install -y" ;;
        zypper) PKG_INSTALL="zypper --non-interactive install" ;;
        pacman) PKG_INSTALL="pacman -S --needed --noconfirm" ;;
        apk)    PKG_INSTALL="apk add" ;;
        xbps)   PKG_INSTALL="xbps-install -Sy" ;;
        emerge) PKG_INSTALL="emerge --noreplace" ;;
    esac
}

# What each distribution calls the things this needs. Only the names that differ
# are listed; anything not named here is assumed to be spelled the same.
pkg_for() {
    local what="$1"
    case "$PKG:$what" in
        apt:toolchain)    echo "build-essential gnu-efi" ;;
        apt:pillow)       echo "python3-pil" ;;
        apt:fonts)        echo "fonts-dejavu-core" ;;
        apt:efi)          echo "efibootmgr" ;;
        apt:plymouth)     echo "plymouth" ;;
        dnf:toolchain)    echo "gcc make binutils gnu-efi gnu-efi-devel" ;;
        dnf:pillow)       echo "python3-pillow" ;;
        dnf:fonts)        echo "dejavu-sans-fonts dejavu-sans-mono-fonts" ;;
        dnf:efi)          echo "efibootmgr" ;;
        dnf:plymouth)     echo "plymouth plymouth-plugin-script" ;;
        zypper:toolchain) echo "gcc make binutils gnu-efi-devel" ;;
        zypper:pillow)    echo "python3-Pillow" ;;
        zypper:fonts)     echo "dejavu-fonts" ;;
        zypper:efi)       echo "efibootmgr" ;;
        zypper:plymouth)  echo "plymouth plymouth-plugin-script" ;;
        pacman:toolchain) echo "base-devel gnu-efi" ;;
        pacman:pillow)    echo "python-pillow" ;;
        pacman:fonts)     echo "ttf-dejavu" ;;
        pacman:efi)       echo "efibootmgr" ;;
        pacman:plymouth)  echo "plymouth" ;;
        apk:toolchain)    echo "build-base gnu-efi-dev" ;;
        apk:pillow)       echo "py3-pillow" ;;
        apk:fonts)        echo "font-dejavu" ;;
        apk:efi)          echo "efibootmgr" ;;
        apk:plymouth)     echo "plymouth" ;;
        xbps:toolchain)   echo "base-devel gnu-efi-libs" ;;
        xbps:pillow)      echo "python3-Pillow" ;;
        xbps:fonts)       echo "dejavu-fonts-ttf" ;;
        xbps:efi)         echo "efibootmgr" ;;
        xbps:plymouth)    echo "plymouth" ;;
        emerge:toolchain) echo "sys-boot/gnu-efi" ;;
        emerge:pillow)    echo "dev-python/pillow" ;;
        emerge:fonts)     echo "media-fonts/dejavu" ;;
        emerge:efi)       echo "sys-boot/efibootmgr" ;;
        emerge:plymouth)  echo "sys-boot/plymouth" ;;
        *) echo "" ;;
    esac
}

detect_initramfs() {
    if   command -v update-initramfs >/dev/null; then INITRAMFS="initramfs-tools"
    elif command -v dracut           >/dev/null; then INITRAMFS="dracut"
    elif command -v mkinitcpio       >/dev/null; then INITRAMFS="mkinitcpio"
    else INITRAMFS=""
    fi
}

secure_boot_state() {
    local v=/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c
    if [ -r "$v" ]; then
        # four bytes of efivarfs attributes, then the value
        case "$(od -An -tu1 -j4 -N1 "$v" 2>/dev/null | tr -d ' ')" in
            1) echo on ;; 0) echo off ;; *) echo unknown ;;
        esac
    elif command -v mokutil >/dev/null; then
        mokutil --sb-state 2>/dev/null | grep -qi enabled && echo on || echo off
    else
        echo unknown
    fi
}

screen_size() {
    local best="" w h m
    for c in /sys/class/drm/card*-*/; do
        [ -r "$c/status" ] || continue
        [ "$(cat "$c/status")" = connected ] || continue
        m=$(head -1 "$c/modes" 2>/dev/null)
        case "$m" in *x*) ;; *) continue ;; esac
        w=${m%%x*}; h=${m#*x}; h=${h//[!0-9]/}
        [ -n "$w" ] && [ -n "$h" ] || continue
        if [ -z "$best" ] || [ $((w*h)) -gt $((${best%%x*}*${best#*x})) ]; then best="${w}x${h}"; fi
    done
    printf '%s' "${best:-3840x2160}"
}

free_mib() { df -BM --output=avail "$1" 2>/dev/null | tail -1 | tr -dc 0-9; }

look() {
    head2 "Looking at this machine"

    [ "$(id -u)" -eq 0 ] || die "this needs root: sudo $0"

    case "$(uname -m)" in
        x86_64|amd64) ARCH_EFI=x64 ;;
        aarch64|arm64) die "this build is x86-64 only. rEFInd itself supports AArch64, but the
        patch has not been built or tested for it, and the timing code uses rdtsc." ;;
        *) die "unsupported architecture: $(uname -m)" ;;
    esac
    good "architecture   $(uname -m)"

    [ -d /sys/firmware/efi ] || die "this machine did not boot through UEFI (no /sys/firmware/efi).
        A boot manager cannot be installed from a BIOS/CSM boot. Turn CSM off in
        the firmware setup and reinstall your system's bootloader in UEFI mode
        first. If this is a UEFI machine that merely booted in legacy mode, the
        fix is in the firmware, not here."
    FW_BITS=$(cat /sys/firmware/efi/fw_platform_size 2>/dev/null || echo 64)
    if [ "$FW_BITS" = 32 ]; then
        die "this machine has 32-bit UEFI firmware, which needs refind_ia32.efi.
        Only refind_x64.efi is built here. (Bay Trail and Cherry Trail tablets
        are the usual case: a 64-bit CPU with 32-bit firmware.)"
    fi
    good "firmware       ${FW_BITS}-bit UEFI"

    mountpoint -q /sys/firmware/efi/efivars 2>/dev/null || \
        warn "efivarfs is not mounted; the firmware boot entry cannot be created"

    SECUREBOOT=$(secure_boot_state)
    case "$SECUREBOOT" in
        on) bad "Secure Boot   ON"
            say ""
            say "  The boot menu is built here, on this machine, and nothing signs it. With"
            say "  Secure Boot on the firmware will refuse to start it, and you will get a"
            say "  security-violation message instead of a menu."
            say ""
            say "  Three ways forward, in the order most people should try them:"
            say ""
            say "    1. Turn Secure Boot off in the firmware setup. Quickest, and reversible."
            say "       ${B}If this machine runs Windows with BitLocker, suspend BitLocker first${Z}"
            say "       (in Windows: Manage-bde -protectors -disable C: -RebootCount 2), or the"
            say "       next Windows boot will ask for the 48-digit recovery key."
            say "    2. Enrol the binary's own hash, so Secure Boot stays on:"
            say "         sudo mokutil --import-hash <sha256 of refind_x64.efi>"
            say "       then reboot and confirm in the blue MokManager screen."
            say "    3. Sign it with your own key (sbctl, or sbsign with an existing key) and"
            say "       enrol that key."
            say ""
            say "  This installer will not pretend any of that has happened. Run it again"
            say "  once Secure Boot is off, or pass --no-menu to install only the splash,"
            say "  which Secure Boot does not affect."
            [ "$WANT_MENU" = 1 ] && die "refusing to install a boot menu the firmware will not start"
            ;;
        off)     good "Secure Boot    off" ;;
        unknown) warn "Secure Boot    could not be read; if it is on, the menu will not start" ;;
    esac

    # -------- the EFI System Partition
    if [ -n "$ESP" ]; then
        [ -d "$ESP" ] || die "no such directory: $ESP"
        good "EFI partition  $ESP (given with --esp)"
    else
        ESP_CANDIDATES=$(find_esps)
        local n; n=$(printf '%s' "$ESP_CANDIDATES" | grep -c . || true)
        if [ "$n" = 0 ]; then
            die "no mounted EFI System Partition found.

        Mount it and run this again, for example:
            sudo mkdir -p /boot/efi && sudo mount /dev/sdXn /boot/efi
        Find it with:
            lsblk -o NAME,PARTTYPENAME,MOUNTPOINT"
        elif [ "$n" -gt 1 ]; then
            say ""
            bad "more than one EFI System Partition is mounted:"
            while IFS= read -r e; do
                [ -n "$e" ] || continue
                printf '      %-24s %s\n' "$e" "$(findmnt -no SOURCE "$e")"
            done <<< "$ESP_CANDIDATES"
            die "choose one with --esp <path>. On a machine that has been reinstalled it is
        usually the one that already holds EFI/Microsoft or EFI/<your distro>."
        fi
        ESP="$ESP_CANDIDATES"
        good "EFI partition  $ESP  ($(findmnt -no SOURCE "$ESP"))"
    fi
    touch "$ESP/.refind-frosted-write-test" 2>/dev/null && rm -f "$ESP/.refind-frosted-write-test" \
        || die "$ESP is not writable (mounted read-only?)"
    ESP_FREE=$(free_mib "$ESP")
    note "               ${ESP_FREE} MB free"

    # Where our files go. A directory of our own, so nothing that is already
    # there is ever at risk -- unless an earlier run of this put a build of ours
    # in the traditional place, in which case keep using it.
    if [ -z "$ESP_DIR" ]; then
        if [ -d "$ESP/EFI/$NAME" ]; then ESP_DIR="$NAME"
        elif [ -f "$ESP/EFI/refind/refind_${ARCH_EFI}.efi" ] && \
             grep -qa "f.r.o.s.t._.r.a.d.i.u.s" "$ESP/EFI/refind/refind_${ARCH_EFI}.efi" 2>/dev/null; then
            ESP_DIR="refind"
            note "               EFI/refind already holds a build of this; keeping it there"
        else ESP_DIR="$NAME"
        fi
    fi

    if [ -d "$ESP/EFI/refind" ] && [ "$ESP_DIR" != refind ]; then
        note "               EFI/refind exists and belongs to someone else; leaving it alone"
    fi

    # -------- the rest
    detect_distro; detect_initramfs
    good "distribution   $DISTRO_NAME  (${PKG:-no known package manager})"
    if [ -n "$INITRAMFS" ]; then good "initramfs      $INITRAMFS"
    else warn "initramfs      none found; the splash cannot be installed"; fi
    command -v plymouthd >/dev/null && { PLYMOUTH=1; good "plymouth       installed"; } \
        || warn "plymouth       not installed; the splash cannot be installed"
    [ -d /boot ] && BOOT_FREE=$(free_mib /boot)
    note "               /boot has ${BOOT_FREE} MB free"

    SCREEN=$(screen_size)
    good "screen         $SCREEN"

    # -------- what is missing
    local need="" found=0
    command -v gcc >/dev/null && command -v make >/dev/null && command -v objcopy >/dev/null \
        || need="$need $(pkg_for toolchain)"
    # build-refind.sh fetches the rEFInd tarball with it, and a toolchain
    # metapackage does not always bring it
    command -v curl >/dev/null || need="$need curl"
    command -v patch >/dev/null || need="$need patch"
    # The same places build-refind.sh looks. `ls a b` returns non-zero when any
    # one of its arguments is missing, which made this claim gnu-efi was absent
    # on every machine that has it.
    for d in $(pkg-config --variable=libdir gnu-efi 2>/dev/null) \
             /usr/lib /usr/lib64 /usr/lib64/gnuefi /usr/lib/gnuefi \
             /usr/lib/x86_64-linux-gnu /usr/local/lib; do
        [ -f "$d/crt0-efi-x86_64.o" ] && { found=1; break; }
    done
    [ "$found" = 1 ] || need="$need $(pkg_for toolchain)"
    python3 -c 'import PIL' 2>/dev/null || need="$need $(pkg_for pillow)"
    [ -n "$(find /usr/share/fonts /usr/local/share/fonts -name 'DejaVuSans-Bold.ttf' -print -quit 2>/dev/null)" ] \
        || need="$need $(pkg_for fonts)"
    command -v efibootmgr >/dev/null || need="$need $(pkg_for efi)"
    if [ "$WANT_SPLASH" = 1 ] && ! command -v plymouthd >/dev/null; then
        need="$need $(pkg_for plymouth)"
    fi
    MISSING_PKGS=$(printf '%s' "$need" | tr ' ' '\n' | grep -v '^$' | sort -u | tr '\n' ' ')
    if [ -n "$MISSING_PKGS" ]; then
        warn "missing        $MISSING_PKGS"
        [ -n "$PKG_INSTALL" ] && note "               install with: $PKG_INSTALL $MISSING_PKGS"
    else
        good "dependencies   all present"
    fi
}

# -------------------------------------------------------------------- plan
plan() {
    head2 "What this will do"
    say "  ${DIM}Nothing below has happened yet.${Z}"
    say ""
    if [ "$WANT_MENU" = 1 ]; then
        say "  ${B}The boot menu${Z}"
        say "    build      rEFInd $REFIND_VER with patches/frosted-glass.patch"
        if [ -n "$BACKGROUND" ]; then
            say "    render     the artwork at $SCREEN, from $(basename "$BACKGROUND")"
        else
            say "    render     the artwork at $SCREEN, from the photograph in library.json"
        fi
        if [ "$ESP_DIR" = "$NAME" ]; then
            say "    write      $ESP/EFI/$ESP_DIR/   (a new directory; nothing there is touched)"
        else
            say "    write      $ESP/EFI/$ESP_DIR/   (where a build of this already lives)"
        fi
        say "                 refind_${ARCH_EFI}.efi, refind.conf, the artwork, icons/, backgrounds/"
        say "    keep       anything already there, as *.before-$NAME"
        say "    write      $ESP/EFI/$ESP_DIR/RESCUE.TXT, first of all, saying how to undo this"
        if [ "$PERMANENT" = 1 ]; then
            say "    firmware   add a boot entry and put it first in the boot order"
        else
            say "    firmware   add a boot entry and set ${B}BootNext${Z} -- the next boot only"
            say "               ${DIM}if anything is wrong, the boot after that is unchanged.${Z}"
            say "               ${DIM}make it permanent later with: sudo $0 --promote${Z}"
        fi
    fi
    if [ "$WANT_SPLASH" = 1 ]; then
        say ""
        say "  ${B}The splash${Z}"
        if [ "$PLYMOUTH" = 0 ] || [ -z "$INITRAMFS" ]; then
            say "    ${YEL}skipped${Z}    no plymouth or no initramfs tool on this machine"
        else
            say "    write      /usr/share/plymouth/themes/$NAME/"
            say "    write      /usr/local/bin/refind-splash-sync, and a service that runs it"
            say "    set        DeviceScale=1 in /etc/plymouth/plymouthd.conf"
            say "               ${DIM}plymouth halves any screen wider than 2880 for a theme that${Z}"
            say "               ${DIM}cannot ask about it, which is what makes a 4K splash blurry.${Z}"
            say "    rebuild    the initramfs ($INITRAMFS), keeping a copy of each one first"
        fi
    fi
    say ""
    say "  ${B}To undo all of it${Z}    sudo $0 --uninstall"
    say "  ${DIM}Every write is recorded in $JOURNAL before it happens.${Z}"
}

confirm() {
    [ "$ASSUME_YES" = 1 ] && return 0
    say ""
    printf '  Go ahead? [y/N] '
    local a; read -r a </dev/tty || a=n
    case "$a" in y|Y|yes|YES) return 0 ;; *) say "  Nothing was changed."; exit 0 ;; esac
}

# ------------------------------------------------------------------ actions
# Each one records what it is about to do before doing it.

# Did an earlier run of this put that file there?
#
# It matters because a second run must not "keep a copy" of the copy it made
# last time: that is not somebody else's file being preserved, it is ours being
# duplicated, and after three runs the EFI partition holds three of everything.
ours() {
    # Only "remove" counts. A "remove" line means this created the file, so
    # there was nothing of anyone else's at that path. A "restore" line means
    # the opposite -- the file was somebody else's and a copy of it was kept --
    # and matching that too was a bug with teeth: the batch journals before it
    # copies, so by the time the copy ran the journal already said "restore",
    # ours() said yes, and the backup of the real file was skipped. The
    # already-have-a-backup guard in keep_a_copy covers the restore case.
    [ -f "$JOURNAL" ] || return 1
    grep -qF "	remove $1" "$JOURNAL" 2>/dev/null
}

keep_a_copy() {                       # keep_a_copy PATH
    local p="$1"
    [ -e "$p" ] || return 0
    [ -e "$p.before-$NAME" ] && return 0
    if ours "$p"; then
        record "remove $p"            # ours already; nothing of anyone else's to keep
        return 0
    fi
    record "restore $p"
    cp -a "$p" "$p.before-$NAME"
}

put() {                               # put SRC DST MODE
    local src="$1" dst="$2" mode="${3:-0644}"
    if [ -e "$dst" ]; then keep_a_copy "$dst"; else record "remove $dst"; fi
    [ "$DRY" = 1 ] && return 0
    # This script does not run under `set -e`, so a failed copy would otherwise
    # be stepped over and the firmware told to boot something that is not there.
    install -D -m "$mode" "$src" "$dst" || die "could not write $dst.
        The EFI partition may be full or read-only. Nothing else was changed;
        undo what was with: sudo $0 --uninstall"
}

make_dir() {                          # make_dir PATH
    [ -d "$1" ] && return 0
    record "rmdir $1"
    [ "$DRY" = 1 ] || mkdir -p "$1"
}

rescue_card() {
    # Written before anything is at risk, in a form a firmware shell, a Windows
    # machine and a live USB can all read: plain ASCII, CRLF, an 8.3 name.
    local card="$ESP/EFI/$ESP_DIR/RESCUE.TXT"
    make_dir "$ESP/EFI/$ESP_DIR"
    record "remove $card"
    [ "$DRY" = 1 ] && return 0
    {
        printf 'refind-frosted -- how to get this machine back\r\n'
        printf '=============================================\r\n\r\n'
        printf 'Installed %s on %s\r\n\r\n' "$VERSION" "$(date -u +%Y-%m-%d)"
        printf 'THE BOOT MENU DID NOT APPEAR, OR THE MACHINE WILL NOT START\r\n\r\n'
        printf '  Nothing that was here before was overwritten. Every other boot\r\n'
        printf '  entry on this machine is untouched, so choosing any of them from\r\n'
        printf '  the firmware boot menu (usually F12, F11, Esc or Option at power\r\n'
        printf '  on) will start the system the way it always did.\r\n\r\n'
        printf 'TO REMOVE IT COMPLETELY, from that system:\r\n\r\n'
        printf '    sudo %s/setup.sh --uninstall\r\n\r\n' "$HERE"
        printf '  or by hand:\r\n\r\n'
        printf '    sudo efibootmgr -v            # find the "refind-frosted" entry\r\n'
        printf '    sudo efibootmgr -b XXXX -B    # delete it by its number\r\n'
        printf '    sudo rm -rf %s/EFI/%s\r\n\r\n' "$ESP" "$ESP_DIR"
        printf '  If the splash was installed too:\r\n\r\n'
        printf '    sudo systemctl disable %s-sync.service\r\n' "$NAME"
        printf '    sudo rm -rf /usr/share/plymouth/themes/%s\r\n' "$NAME"
        printf '    sudo update-initramfs -u -k all   # or: dracut --force --regenerate-all\r\n'
        printf '                                     # or: mkinitcpio -P\r\n\r\n'
        printf '  A copy of every initramfs from before the install is kept beside\r\n'
        printf '  it, named *.before-%s.\r\n' "$NAME"
    } > "$card"
    good "rescue card    EFI/$ESP_DIR/RESCUE.TXT"
}

# ------------------------------------------------------------- the boot menu
REFIND_VER=0.14.2

install_menu() {
    head2 "The boot menu"

    say "  building rEFInd $REFIND_VER..."
    if [ "$DRY" = 0 ]; then
        mkdir -p "$STATE"
        if ! "$HERE/build-refind.sh" >"$STATE/build.log" 2>&1; then
            tail -20 "$STATE/build.log" >&2
            die "the build failed; the whole log is in $STATE/build.log"
        fi
    fi
    local built="$HERE/build/refind-$REFIND_VER/refind/refind_${ARCH_EFI}.efi"
    [ "$DRY" = 1 ] || [ -f "$built" ] || die "the build produced no $built"
    good "built          refind_${ARCH_EFI}.efi"

    say "  rendering the artwork at $SCREEN..."
    if [ "$DRY" = 0 ]; then
        local args=(--out "$HERE/assets" --size "$SCREEN")
        [ -n "$BACKGROUND" ] && args+=(--background "$BACKGROUND")
        if ! python3 "$HERE/build.py" "${args[@]}" >"$STATE/render.log" 2>&1; then
            tail -20 "$STATE/render.log" >&2
            die "the artwork could not be rendered; the whole log is in $STATE/render.log"
        fi
    fi
    good "rendered       assets/"

    local D="$ESP/EFI/$ESP_DIR"
    make_dir "$D"; make_dir "$D/icons"; make_dir "$D/backgrounds"

    [ "$DRY" = 1 ] || put "$built" "$D/refind_${ARCH_EFI}.efi" 0644
    for f in background.png font.png selection_big.png selection_small.png frost_big.png dot.png; do
        [ -f "$HERE/assets/$f" ] && put "$HERE/assets/$f" "$D/$f"
    done
    if [ "$DRY" = 0 ]; then
        # Record every one of these, so that uninstalling removes exactly what
        # was installed -- and only that. backgrounds/ is the directory people
        # are told to drop their own photographs into, so it must never be
        # deleted wholesale: what goes is what came from here, and if anything
        # of theirs is left the directory stays with it.
        # Work out the whole list, journal it in one go, and only then copy.
        # Journalling afterwards is the wrong way round: a machine that loses
        # power between the copy and the record wakes up with files on its EFI
        # partition that nothing knows how to remove.
        local sources=() targets=() lines=()
        for f in "$HERE"/assets/icons/*.png; do
            [ -e "$f" ] || continue
            sources+=("$f"); targets+=("$D/icons/$(basename "$f")")
        done
        for f in "$HERE"/library/*.jpg "$HERE"/library/*.png; do
            [ -e "$f" ] || continue
            case "$(basename "$f")" in preview-sheet.jpg) continue ;; esac
            sources+=("$f"); targets+=("$D/backgrounds/$(basename "$f")")
        done
        local i
        for i in "${!targets[@]}"; do
            if [ -e "${targets[$i]}" ] && ! ours "${targets[$i]}"; then
                lines+=("restore ${targets[$i]}")
            else
                lines+=("remove ${targets[$i]}")
            fi
        done
        [ ${#lines[@]} -gt 0 ] && record_batch "${lines[@]}"
        for i in "${!targets[@]}"; do
            # keep whatever was there -- installing over an existing rEFInd with
            # --dir refind would otherwise replace its icons with no way back
            if [ -e "${targets[$i]}" ] && [ ! -e "${targets[$i]}.before-$NAME" ] \
               && ! ours "${targets[$i]}"; then
                cp -a "${targets[$i]}" "${targets[$i]}.before-$NAME" || true
            fi
            install -m 0644 "${sources[$i]}" "${targets[$i]}" \
                || die "could not write ${targets[$i]} -- is the EFI partition full?
        Nothing else was changed. Run: sudo $0 --uninstall"
        done
    fi
    good "artwork        $(find "$D/icons" -name '*.png' 2>/dev/null | wc -l) icons, $(find "$D/backgrounds" -type f ! -name "*.before-$NAME" 2>/dev/null | wc -l) photographs"

    # refind.conf has to agree with the artwork about three numbers, and the
    # artwork was just drawn for this screen rather than for a 4K one. build.py
    # writes what it used; put those into the copy that gets installed, leaving
    # the one in the repository at its 4K defaults.
    local conf="$HERE/assets/refind.conf.installed"
    cp "$HERE/refind.conf" "$conf"
    if [ -f "$HERE/assets/geometry.json" ]; then
        local big small frost
        big=$(  sed -n 's/.*"big_icon_size":[ ]*\([0-9]*\).*/\1/p'   "$HERE/assets/geometry.json")
        small=$(sed -n 's/.*"small_icon_size":[ ]*\([0-9]*\).*/\1/p' "$HERE/assets/geometry.json")
        frost=$(sed -n 's/.*"frost_radius":[ ]*\([0-9]*\).*/\1/p'    "$HERE/assets/geometry.json")
        if [ -n "$big" ] && [ -n "$small" ] && [ -n "$frost" ]; then
            sed -i "s/^big_icon_size .*/big_icon_size   $big/;
                    s/^small_icon_size .*/small_icon_size $small/;
                    s/^frost_radius .*/frost_radius $frost/" "$conf"
            good "geometry       big_icon_size $big, small_icon_size $small, frost_radius $frost"
        fi
    fi
    put "$conf" "$D/refind.conf"
    # Never overwrite choices made from the boot menu's own settings screen.
    local theme_note="theme.conf kept as you left it"
    if [ ! -f "$D/theme.conf" ]; then
        if [ -f "$HERE/assets/theme.conf" ]; then
            put "$HERE/assets/theme.conf" "$D/theme.conf"
            theme_note="theme.conf written"
        else
            theme_note="no theme.conf"
        fi
    fi
    good "configuration  refind.conf, $theme_note"

    register_with_firmware "$D"
}

register_with_firmware() {
    local D="$1"
    ENTRY_MADE=0
    command -v efibootmgr >/dev/null || { warn "no efibootmgr: no boot entry was created"; return 0; }
    mountpoint -q /sys/firmware/efi/efivars 2>/dev/null || { warn "efivarfs not mounted: no boot entry was created"; return 0; }

    local disk part src existing num
    src=$(findmnt -no SOURCE "$ESP")
    disk=$(lsblk -no PKNAME "$src" 2>/dev/null | head -1)
    part=$(lsblk -no PARTN "$src" 2>/dev/null | head -1)
    [ -n "$disk" ] && [ -n "$part" ] || { warn "could not work out which disk $ESP is on; no boot entry was created"; return 0; }

    # Never make a second entry for the same thing.
    existing=$(efibootmgr -v 2>/dev/null | grep -i "refind-frosted" | head -1 | sed 's/^Boot\([0-9A-Fa-f]*\).*/\1/')
    if [ -n "$existing" ]; then
        good "firmware       entry Boot$existing already exists; left alone"
        num="$existing"
        ENTRY_MADE=1
    else
        if [ "$DRY" = 1 ]; then
            good "firmware       would add a boot entry on /dev/$disk partition $part"
            return 0
        fi
        record "nvram-del refind-frosted"
        # -C, not -c. `efibootmgr -c` creates the entry AND puts it at the front
        # of BootOrder, which is exactly what this is trying not to do: the whole
        # point of trying it with BootNext is that the boot order is left alone,
        # so a machine that does not like the new loader goes back to normal by
        # itself. --create-only creates the entry and nothing else.
        local err
        if ! err=$(efibootmgr -C -d "/dev/$disk" -p "$part" \
                   -L "refind-frosted" -l "\\EFI\\$ESP_DIR\\refind_${ARCH_EFI}.efi" 2>&1 >/dev/null); then
            warn "efibootmgr refused to create the entry:"
            printf '%s\n' "$err" | sed 's/^/                 /'
            return 0
        fi
        num=$(efibootmgr -v | grep -i "refind-frosted" | head -1 | sed 's/^Boot\([0-9A-Fa-f]*\).*/\1/')
        if [ -z "$num" ]; then
            warn "efibootmgr reported success but no entry appeared"
            return 0
        fi
        good "firmware       added boot entry Boot$num, boot order untouched"
        ENTRY_MADE=1
    fi

    [ "$DRY" = 1 ] && return 0
    if [ "$PERMANENT" = 1 ]; then
        local order; order=$(efibootmgr | sed -n 's/^BootOrder: //p')
        record "nvram-order $order"
        if err=$(efibootmgr -o "$num,$(printf '%s' "$order" | sed "s/\b$num,\?//g; s/,$//")" 2>&1 >/dev/null); then
            good "firmware       first in the boot order"
        else
            warn "could not set the boot order:"
            printf '%s\n' "$err" | sed 's/^/                 /'
        fi
    else
        # Record whatever BootNext was, so undoing puts that back rather than
        # deleting a setting somebody else had made.
        local was; was=$(efibootmgr | sed -n 's/^BootNext: //p')
        record "nvram-bootnext ${was:-none}"
        if err=$(efibootmgr -n "$num" 2>&1 >/dev/null); then
            good "firmware       BootNext=$num -- the next boot only"
        else
            warn "could not set BootNext:"
            printf '%s\n' "$err" | sed 's/^/                 /'
            ENTRY_MADE=0
        fi
    fi
}

# ---------------------------------------------------------------- the splash
install_splash() {
    head2 "The splash"
    if [ "$PLYMOUTH" = 0 ]; then warn "plymouth is not installed; skipping"; return 0; fi
    if [ -z "$INITRAMFS" ]; then warn "no initramfs tool found; skipping"; return 0; fi
    if ! python3 -c 'import PIL' 2>/dev/null; then
        warn "python3 Pillow is missing; skipping the splash"
        note "install it with: $PKG_INSTALL $(pkg_for pillow)"
        return 0
    fi

    # The most likely way to make a machine unbootable is to run out of room in
    # /boot while writing an initramfs. Each themed image is about 42 MB and a
    # copy of the old one is kept beside it, so ask for both before starting.
    local kernels images want
    images=""
    for f in /boot/initrd.img-* /boot/initramfs-*.img; do
        [ -e "$f" ] || continue
        case "$f" in *before-$NAME) continue ;; esac
        images="$images $f"
    done
    images="${images# }"
    kernels=$(printf '%s\n' $images | grep -c . || true)
    want=$(( (kernels + 1) * 50 ))
    if [ "$BOOT_FREE" -gt 0 ] && [ "$BOOT_FREE" -lt "$want" ]; then
        bad "/boot has ${BOOT_FREE} MB free and rebuilding $kernels initramfs images with a"
        bad "backup of each needs about ${want} MB. Refusing: running out of room"
        bad "halfway through writing an initramfs is how a machine stops booting."
        note "free some space (sudo apt autoremove, or remove an old kernel) and run this again"
        return 1
    fi
    good "room           ${BOOT_FREE} MB free in /boot, about ${want} MB wanted"

    # Keep a copy of every initramfs before anything touches them.
    local img
    for img in $images; do keep_a_copy "$img"; done
    [ -n "$images" ] && good "kept           a copy of each initramfs as *.before-$NAME"

    if [ "$DRY" = 1 ]; then
        good "would install  the theme, the sync service, and rebuild the initramfs"
        return 0
    fi

    record "remove /usr/local/share/$NAME"
    install -d -m 0755 "/usr/local/share/$NAME" "/usr/local/share/$NAME/stock-icons" \
                       "/usr/local/share/$NAME/library"
    install -m 0644 "$HERE/build.py" "$HERE/plymouth.py" "/usr/local/share/$NAME/"
    install -m 0644 "$HERE"/stock-icons/*.png "/usr/local/share/$NAME/stock-icons/"
    install -m 0644 "$HERE/library/library.json" "/usr/local/share/$NAME/library/"
    put "$HERE/splash-sync.py" /usr/local/bin/refind-splash-sync 0755
    good "generator      /usr/local/share/$NAME, /usr/local/bin/refind-splash-sync"

    keep_a_copy /etc/plymouth/plymouthd.conf

    # Build and install the theme, at this screen's size, from the menu's own
    # photograph. This also sets DeviceScale and rebuilds the initramfs.
    record "remove /usr/share/plymouth/themes/$NAME"
    if ! /usr/local/bin/refind-splash-sync --force; then
        bad "the splash could not be built"
        restore_initramfs
        return 1
    fi

    # Select it only after it has been built, or the initramfs is rebuilt around
    # a theme that is not yet the one being used.
    if command -v update-alternatives >/dev/null; then
        record "alternatives-restore"
        update-alternatives --install /usr/share/plymouth/themes/default.plymouth \
                            default.plymouth "/usr/share/plymouth/themes/$NAME/$NAME.plymouth" 200 >/dev/null
        update-alternatives --set default.plymouth "/usr/share/plymouth/themes/$NAME/$NAME.plymouth" >/dev/null
    elif command -v plymouth-set-default-theme >/dev/null; then
        record "theme-restore $(plymouth-set-default-theme 2>/dev/null || echo details)"
        plymouth-set-default-theme "$NAME" >/dev/null
    else
        warn "could not select the theme: no update-alternatives, no plymouth-set-default-theme"
    fi
    good "theme          selected"

    # mkinitcpio needs the plymouth hook in its HOOKS line; nothing else does.
    if [ "$INITRAMFS" = mkinitcpio ] && ! grep -qE '^HOOKS=.*\bplymouth\b' /etc/mkinitcpio.conf 2>/dev/null; then
        warn "mkinitcpio.conf has no plymouth hook, so the splash will not show."
        note "add it to HOOKS in /etc/mkinitcpio.conf, right after 'base udev':"
        note "    HOOKS=(base udev plymouth autodetect ...)"
        note "then: sudo mkinitcpio -P"
    fi

    # Selecting the theme changed what the initramfs should contain, so build it
    # once more now that everything is in place.
    rebuild_initramfs || { restore_initramfs; return 1; }
    good "initramfs      rebuilt ($INITRAMFS)"

    if command -v systemctl >/dev/null && [ -d /etc/systemd/system ]; then
        put "$HERE/$NAME-sync.service" "/etc/systemd/system/$NAME-sync.service"
        systemctl daemon-reload
        record "service-disable $NAME-sync.service"
        systemctl enable "$NAME-sync.service" >/dev/null 2>&1
        good "service        $NAME-sync.service -- follows the menu's photograph from now on"
    else
        warn "no systemd here; run refind-splash-sync yourself after changing the photograph"
    fi
    return 0
}

rebuild_initramfs() {
    case "$INITRAMFS" in
        initramfs-tools) update-initramfs -u -k all >/dev/null 2>&1 ;;
        dracut)          dracut --force --regenerate-all >/dev/null 2>&1 ;;
        mkinitcpio)      mkinitcpio -P >/dev/null 2>&1 ;;
        *) return 1 ;;
    esac
}

restore_initramfs() {
    local img n=0
    for img in /boot/initrd.img-*.before-$NAME /boot/initramfs-*.img.before-$NAME; do
        [ -e "$img" ] || continue
        cp -a "$img" "${img%.before-$NAME}"; n=$((n+1))
    done
    [ "$n" -gt 0 ] && warn "put back $n initramfs image(s) from before the install"
    return 0
}

# ------------------------------------------------------------------- verbs
do_status() {
    head2 "refind-frosted $VERSION"
    [ -f "$JOURNAL" ] || { note "not installed (no $JOURNAL)"; exit 0; }
    note "journal        $JOURNAL ($(wc -l < "$JOURNAL") actions)"
    local d
    for d in /boot/efi /efi /boot; do
        [ -d "$d/EFI/$NAME" ] && note "boot menu      $d/EFI/$NAME"
        [ -d "$d/EFI/refind" ] && [ -f "$d/EFI/refind/refind_${ARCH_EFI}.efi" ] && \
            grep -qa "f.r.o.s.t._.r.a.d.i.u.s" "$d/EFI/refind/refind_${ARCH_EFI}.efi" 2>/dev/null && \
            note "boot menu      $d/EFI/refind (ours)"
    done
    [ -d "/usr/share/plymouth/themes/$NAME" ] && note "splash         /usr/share/plymouth/themes/$NAME"
    command -v efibootmgr >/dev/null && efibootmgr 2>/dev/null | grep -i refind-frosted | sed 's/^/  firmware       /'
    systemctl is-enabled "$NAME-sync.service" >/dev/null 2>&1 && note "service        enabled"
    exit 0
}

do_promote() {
    command -v efibootmgr >/dev/null || die "efibootmgr is not installed"
    local num order
    num=$(efibootmgr -v | grep -i refind-frosted | head -1 | sed 's/^Boot\([0-9A-Fa-f]*\).*/\1/')
    [ -n "$num" ] || die "no refind-frosted boot entry found. Install it first."
    order=$(efibootmgr | sed -n 's/^BootOrder: //p')
    record "nvram-order $order"
    efibootmgr -q -o "$num,$(printf '%s' "$order" | sed "s/\b$num,\?//g; s/,$//")"
    good "refind-frosted is now first in the boot order"
    note "to put it back: sudo efibootmgr -o $order"
    exit 0
}

do_uninstall() {
    head2 "Putting everything back"
    [ "$(id -u)" -eq 0 ] || die "this needs root: sudo $0 --uninstall"
    [ -f "$JOURNAL" ] || die "no journal at $JOURNAL -- nothing recorded to undo.
        RESCUE.TXT on the EFI partition lists the manual steps."

    detect_initramfs
    local line what arg touched_initramfs=0 touched_theme=0
    # In reverse: the last thing done is the first thing undone.
    while IFS= read -r line; do
        what=$(printf '%s' "$line" | cut -f2- | cut -d' ' -f1)
        arg=$(printf '%s' "$line" | cut -f2- | cut -d' ' -f2-)
        case "$what" in
            restore)
                if [ -e "$arg.before-$NAME" ]; then
                    cp -a "$arg.before-$NAME" "$arg" && rm -f "$arg.before-$NAME"
                    note "put back       $arg"
                    case "$arg" in */initrd.img-*|*/initramfs-*) touched_initramfs=1 ;; esac
                fi ;;
            remove)
                if [ -e "$arg" ]; then
                    rm -rf "$arg"; note "removed        $arg"
                    case "$arg" in */plymouth/themes/*) touched_theme=1 ;; esac
                fi ;;
            rmdir)
                [ -d "$arg" ] && rmdir "$arg" 2>/dev/null && note "removed        $arg" ;;
            nvram-del)
                local n
                n=$(efibootmgr -v 2>/dev/null | grep -i "$arg" | head -1 | sed 's/^Boot\([0-9A-Fa-f]*\).*/\1/')
                [ -n "$n" ] && { efibootmgr -q -b "$n" -B; note "removed        firmware entry Boot$n"; } ;;
            nvram-order)
                [ -n "$arg" ] && { efibootmgr -q -o "$arg"; note "restored       boot order $arg"; } ;;
            nvram-bootnext)
                if [ -n "$arg" ] && [ "$arg" != none ]; then
                    efibootmgr -q -n "$arg" 2>/dev/null; note "restored       BootNext=$arg"
                else
                    efibootmgr -q -N 2>/dev/null; note "cleared        BootNext"
                fi ;;
            alternatives-restore)
                update-alternatives --remove default.plymouth \
                    "/usr/share/plymouth/themes/$NAME/$NAME.plymouth" >/dev/null 2>&1
                note "restored       the previous plymouth theme" ;;
            theme-restore)
                [ -n "$arg" ] && plymouth-set-default-theme "$arg" >/dev/null 2>&1
                note "restored       plymouth theme $arg" ;;
            service-disable)
                systemctl disable "$arg" >/dev/null 2>&1
                rm -f "/etc/systemd/system/$arg"
                systemctl daemon-reload 2>/dev/null
                note "disabled       $arg" ;;
        esac
    done < <(tac "$JOURNAL")

    # Only what the journal recorded. An earlier version deleted the Plymouth
    # theme here whether or not this install had ever put one there -- so
    # undoing a boot-menu-only install would have taken somebody else's splash
    # with it.
    if [ "$touched_theme" = 1 ] || [ "$touched_initramfs" = 1 ]; then
        say "  rebuilding the initramfs..."
        rebuild_initramfs && note "rebuilt        the initramfs without the theme"
    fi

    # Anything still standing in a directory this install made is something it
    # did not put there -- a photograph of your own, most likely. Say so rather
    # than deleting it, and only look at the directories the journal names.
    local keep
    while IFS= read -r keep; do
        [ -d "$keep" ] || continue
        if [ -n "$(ls -A "$keep" 2>/dev/null)" ]; then
            warn "$keep was left in place: it holds files this did not install"
            ls -A "$keep" | sed 's/^/                 /'
        else
            rmdir "$keep" 2>/dev/null && note "removed        $keep"
        fi
    done < <(awk -F'\t' '$2 ~ /^rmdir /{ sub(/^rmdir /,"",$2); print $2 }' "$JOURNAL" | sort -ru)

    mv "$JOURNAL" "$JOURNAL.done-$(date -u +%Y%m%d-%H%M%S)"
    head2 "Done"
    note "the journal is kept as $JOURNAL.done-*"
    note "check the firmware boot order with: efibootmgr -v"
    exit 0
}

# -------------------------------------------------------------------- main
case "$DO" in
    status)    do_status ;;
    promote)   [ "$(id -u)" -eq 0 ] || die "this needs root"; do_promote ;;
    uninstall) do_uninstall ;;
esac

look
if [ -n "$MISSING_PKGS" ] && [ "$INSTALL_DEPS" = 1 ] && [ -n "$PKG_INSTALL" ]; then
    head2 "Installing what is missing"
    # shellcheck disable=SC2086
    $PKG_INSTALL $MISSING_PKGS || die "the package manager refused"
    look
fi
if [ -n "$MISSING_PKGS" ]; then
    say ""
    die "install the missing packages first, or run this again with --install-deps:
        $PKG_INSTALL $MISSING_PKGS"
fi

plan
[ "$DRY" = 1 ] && { say ""; note "--dry-run: nothing was changed."; exit 0; }
confirm

[ "$WANT_MENU" = 1 ] && rescue_card
MENU_OK=1; SPLASH_OK=1
[ "$WANT_MENU"   = 1 ] && { install_menu   || MENU_OK=0; }
[ "$WANT_SPLASH" = 1 ] && { install_splash || SPLASH_OK=0; }

head2 "Done"
if [ "$WANT_MENU" = 1 ] && [ "$MENU_OK" = 1 ]; then
    if [ "$ENTRY_MADE" = 0 ]; then
        warn "the files are installed, but the firmware has no entry pointing at them,"
        warn "so rebooting will not reach the menu. Add one by hand:"
        note "    sudo efibootmgr -c -d /dev/<disk> -p <partition> \\"
        note "        -L refind-frosted -l '\\EFI\\$ESP_DIR\\refind_${ARCH_EFI}.efi'"
    elif [ "$PERMANENT" = 1 ]; then
        good "reboot and the boot menu is there, and stays there."
    else
        good "reboot and the boot menu is there ${B}for that one boot${Z}."
        note "if it looks right:   sudo $0 --promote"
        note "if it does not:      do nothing. The boot after it is unchanged."
    fi
fi
if [ "$WANT_SPLASH" = 1 ]; then
    if [ "$SPLASH_OK" = 1 ] && [ -d "/usr/share/plymouth/themes/$NAME" ]; then
        good "the splash follows the menu's photograph from now on, by itself."
    else
        warn "the splash was not installed; the boot menu above is unaffected."
    fi
fi
say ""
note "to undo everything:  sudo $0 --uninstall"
note "what is installed:   sudo $0 --status"
