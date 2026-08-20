#!/usr/bin/env bash
# Removes the launcher and desktop entries. Your notes are left alone.
set -euo pipefail
rm -f "$HOME/.local/bin/stickies" \
      "$HOME/.local/share/applications/stickies.desktop" \
      "$HOME/.config/autostart/stickies.desktop"
echo "Removed launcher and desktop entries."
echo "Your notes are still at ~/.local/share/stickies/notes.json - delete that yourself if you want them gone."
