#!/usr/bin/env bash
# Copies freshly built assets to rEFInd's directory on the ESP.
# Called with pkexec by the GUI, so the password is asked once.
set -euo pipefail
SRC="${1:?usage: install-assets.sh <asset-dir>}"
ESP=/boot/efi/EFI/refind
[ -d "$ESP" ] || { echo "rEFInd not found at $ESP"; exit 1; }
[ -f "$SRC/background.png" ] || { echo "no assets in $SRC"; exit 1; }
for f in background.png font.png selection_big.png selection_small.png; do
    install -m 0755 "$SRC/$f" "$ESP/$f"
done
# entries used to be manual stanzas pointing at these; they are gone now
rm -f "$ESP/icon_windows.png" "$ESP/icon_ubuntu.png"
mkdir -p "$ESP/icons"
for f in "$SRC"/icons/*.png; do
    install -m 0755 "$f" "$ESP/icons/$(basename "$f")"
done
echo "installed to $ESP"
