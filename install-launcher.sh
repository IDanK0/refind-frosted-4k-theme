#!/usr/bin/env bash
# Adds the graphical picker to the applications menu. No root needed.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"
mkdir -p "$APPS" "$ICONS"
sed "s|^Exec=.*|Exec=$HERE/background-gui.py|" "$HERE/refind-background.desktop" \
    > "$APPS/refind-background.desktop"
install -m 0644 "$HERE/icon.png" "$ICONS/refind-background.png"
update-desktop-database "$APPS" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
echo "Added to the applications menu — search for \"Boot Menu Background\"."
