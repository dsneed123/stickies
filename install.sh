#!/usr/bin/env bash
# Puts `stickies` on your PATH and in the app grid. Nothing is copied - the
# launcher points back at this directory, so `git pull` is enough to update.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"

command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk" 2>/dev/null || {
  echo "PyGObject (GTK 3) is missing. Install it with:"
  echo "  sudo apt install python3-gi gir1.2-gtk-3.0"
  exit 1
}

mkdir -p "$BIN_DIR" "$APP_DIR"

cat > "$BIN_DIR/stickies" <<EOF
#!/usr/bin/env bash
# Detaches by default so your terminal comes straight back.
#   stickies              start (or raise an already-running instance)
#   stickies --new        start and add a fresh note
#   stickies -f           run in the foreground, logging to the terminal
LOG="\${XDG_DATA_HOME:-\$HOME/.local/share}/stickies/stickies.log"
mkdir -p "\$(dirname "\$LOG")"

if [[ "\${1:-}" == "-f" || "\${1:-}" == "--foreground" ]]; then
  shift
  exec python3 "$HERE/stickies.py" "\$@"
fi

setsid python3 "$HERE/stickies.py" "\$@" >>"\$LOG" 2>&1 </dev/null &
disown 2>/dev/null || true
EOF
chmod +x "$BIN_DIR/stickies"

cat > "$APP_DIR/stickies.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Stickies
GenericName=Sticky Notes
Comment=Post-it notes with an Ollama-powered Claude prompt writer
Exec=$BIN_DIR/stickies
Icon=accessories-text-editor
Terminal=false
Categories=Utility;TextEditor;
Keywords=notes;sticky;postit;todo;claude;ollama;
StartupNotify=false
Actions=NewNote;

[Desktop Action NewNote]
Name=New note
Exec=$BIN_DIR/stickies --new
EOF

update-desktop-database "$APP_DIR" 2>/dev/null || true

echo "Installed:"
echo "  $BIN_DIR/stickies"
echo "  $APP_DIR/stickies.desktop"

read -r -p "Start Stickies automatically at login? [y/N] " reply
if [[ "${reply,,}" == "y" ]]; then
  mkdir -p "$AUTOSTART_DIR"
  cp "$APP_DIR/stickies.desktop" "$AUTOSTART_DIR/stickies.desktop"
  echo "  $AUTOSTART_DIR/stickies.desktop"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo; echo "Note: $BIN_DIR is not on your PATH. Add it to ~/.bashrc:"
     echo "  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

echo
echo "Run it with:  stickies"
