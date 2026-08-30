#!/usr/bin/env bash
# Copies freshly built assets to rEFInd's directory on the ESP.
# Called with pkexec by the GUI, so the password is asked once.
set -euo pipefail
SRC="${1:?usage: install-assets.sh <asset-dir>}"
ESP=/boot/efi/EFI/refind
[ -d "$ESP" ] || { echo "rEFInd not found at $ESP"; exit 1; }
[ -f "$SRC/background.png" ] || { echo "no assets in $SRC"; exit 1; }
for f in background.png font.png selection_big.png selection_small.png frost_big.png dot.png; do
    install -m 0755 "$SRC/$f" "$ESP/$f"
done
# entries used to be manual stanzas pointing at these; they are gone now
rm -f "$ESP/icon_windows.png" "$ESP/icon_ubuntu.png"
mkdir -p "$ESP/icons"
for f in "$SRC"/icons/*.png; do
    install -m 0755 "$f" "$ESP/icons/$(basename "$f")"
done
# The photographs the settings screen offers. Anyone can add to this from any
# system: it is a plain directory on the EFI partition.
install -d -m 0755 "$ESP/backgrounds"
for f in "$SRC"/../library/*.jpg "$SRC"/../library/*.png; do
    [ -e "$f" ] || continue
    case "$(basename "$f")" in preview-sheet.jpg) continue ;; esac
    install -m 0755 "$f" "$ESP/backgrounds/$(basename "$f")"
done

# Never overwrite choices made from the boot menu itself.
if [ -f "$SRC/theme.conf" ] && [ ! -f "$ESP/theme.conf" ]; then
    install -m 0755 "$SRC/theme.conf" "$ESP/theme.conf"
    echo "wrote a starting theme.conf"
fi

echo "installed to $ESP"
