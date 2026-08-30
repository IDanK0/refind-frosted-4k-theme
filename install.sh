#!/usr/bin/env bash
# Installs the theme into rEFInd's directory on the EFI System Partition.
set -euo pipefail

ESP_REFIND=/boot/efi/EFI/refind
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo $0"; exit 1; }
[ -d "$ESP_REFIND" ] || { echo "rEFInd not found at $ESP_REFIND. Install it first (apt install refind && refind-install)."; exit 1; }
[ -f "$ESP_REFIND/refind_x64.efi" ] || { echo "$ESP_REFIND exists but holds no refind_x64.efi. Aborting."; exit 1; }

STAMP=$(date +%Y%m%d-%H%M%S)
echo "Backing up existing configuration..."
cp -a "$ESP_REFIND/refind.conf" "$ESP_REFIND/refind.conf.bak-$STAMP"
echo "  -> refind.conf.bak-$STAMP"

echo "Installing assets..."
for f in background.png font.png icon_windows.png icon_ubuntu.png \
         selection_big.png selection_small.png; do
    install -m 0755 "$HERE/assets/$f" "$ESP_REFIND/$f"
    echo "  -> $f"
done
mkdir -p "$ESP_REFIND/icons"
for f in "$HERE"/assets/icons/*.png; do
    install -m 0755 "$f" "$ESP_REFIND/icons/$(basename "$f")"
    echo "  -> icons/$(basename "$f")"
done

echo "Installing configuration..."
install -m 0755 "$HERE/refind.conf" "$ESP_REFIND/refind.conf"

cat <<MSG

Done.

  Check the two menuentry blocks in refind.conf point at your own loaders:
    grep -A3 '^menuentry' $ESP_REFIND/refind.conf

  The OS labels are baked into background.png, so the tile geometry in
  refind.conf must match the constants in build.py. Do not change
  big_icon_size or small_icon_size without regenerating the assets.

  Roll back with:
    sudo cp $ESP_REFIND/refind.conf.bak-$STAMP $ESP_REFIND/refind.conf
MSG
