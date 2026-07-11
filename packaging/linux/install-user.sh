#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
APP_DIR="$PREFIX/opt/companion-ai"

mkdir -p "$APP_DIR" "$PREFIX/bin" "$PREFIX/share/applications"
cp -a "$SCRIPT_DIR/opt/companion-ai/." "$APP_DIR/"
install -m 0755 "$SCRIPT_DIR/usr/bin/companion-ai" "$PREFIX/bin/companion-ai"
install -m 0644 "$SCRIPT_DIR/usr/share/applications/companion-ai.desktop" "$PREFIX/share/applications/companion-ai.desktop"

echo "Companion AI installed to $APP_DIR"
echo "Make sure $PREFIX/bin is in PATH, then run: companion-ai"
