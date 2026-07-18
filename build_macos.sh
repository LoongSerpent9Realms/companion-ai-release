#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
VERSION="$(tr -d '[:space:]' < "$ROOT/version.txt")"
ARCH="$(uname -m)"

case "$ARCH" in
  x86_64|amd64) PACKAGE_ARCH="x86_64" ;;
  arm64|aarch64) PACKAGE_ARCH="arm64" ;;
  *)
    echo "Unsupported macOS architecture: $ARCH" >&2
    exit 1
    ;;
esac

VENV="${BUILD_VENV:-$ROOT/.venv-macos}"
BUILD_ROOT="$ROOT/build/macos"
DIST_ROOT="$ROOT/dist/macos"
APP_NAME="CompanionAI"
PACKAGE_NAME="companion-ai-${VERSION}-macos-${PACKAGE_ARCH}"

if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV"
fi

PY="$VENV/bin/python"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install --upgrade pyinstaller pillow pystray certifi

rm -rf "$BUILD_ROOT" "$DIST_ROOT"
mkdir -p "$BUILD_ROOT/work" "$BUILD_ROOT/spec" "$DIST_ROOT"

DATA_ARGS=()
add_data_if_present() {
  local source="$1"
  local target="$2"
  if [[ -e "$ROOT/$source" ]]; then
    DATA_ARGS+=(--add-data "$ROOT/$source:$target")
  fi
}

add_data_if_present "plugins" "plugins"
add_data_if_present "static" "static"
add_data_if_present "live2d_viewer.html" "."
add_data_if_present "viewer_3d.html" "."
add_data_if_present "official_site.html" "."
add_data_if_present "version.txt" "."
add_data_if_present "dataset_runtime_worker.py" "."
add_data_if_present "face_manager.py" "."
add_data_if_present "sensitive_json.py" "."
add_data_if_present "secure_json.py" "."
add_data_if_present "electron_pet" "electron_pet"

HIDDEN_IMPORTS=(
  hybrid_chat retrieval_chat tiny_llm embedding_retrieval emotion_diary
  dataset_loader plugin_manager rapidocr_runner face_manager neural_companion
  llm_inference llm_trainer operation_learning procedural_rules conversation_audit
  audit_training train_llm code_lab algorithm_curriculum toolchain_manager _paths app desktop_pet pystray PIL certifi
)
EXCLUDED_MODULES=(
  torch torchvision torchaudio torch_directml triton pytorch_triton cv2 edge_tts
  datasets modelscope modelscope_hub huggingface_hub pandas pyarrow fsspec dill
  multiprocess xxhash addict
)

PYINSTALLER_ARGS=(
  --noconfirm --clean --onedir --windowed
  --name "$APP_NAME"
  --distpath "$DIST_ROOT"
  --workpath "$BUILD_ROOT/work"
  --specpath "$BUILD_ROOT/spec"
  "${DATA_ARGS[@]}"
)
for module in "${HIDDEN_IMPORTS[@]}"; do
  PYINSTALLER_ARGS+=(--hidden-import "$module")
done
for module in "${EXCLUDED_MODULES[@]}"; do
  PYINSTALLER_ARGS+=(--exclude-module "$module")
done

echo "[macos-build] Building Companion AI ${VERSION} for ${PACKAGE_ARCH}..."
"$PY" -m PyInstaller "${PYINSTALLER_ARGS[@]}" "$ROOT/companion_launcher.py"

APP_DIR="$DIST_ROOT/$APP_NAME.app"
if [[ ! -x "$APP_DIR/Contents/MacOS/$APP_NAME" ]]; then
  echo "PyInstaller did not produce $APP_DIR" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Optional Developer ID code signing.
# Activated when MAC_DEVELOPER_IDENTITY is set (e.g. "Developer ID Application: Name (TEAMID)").
# Without it the build produces an unsigned app, which macOS Gatekeeper will
# warn about. Distributors should set these secrets in CI.
# ---------------------------------------------------------------------------
SIGNED=0
if [[ -n "${MAC_DEVELOPER_IDENTITY:-}" ]]; then
  echo "[macos-build] Signing $APP_DIR with '$MAC_DEVELOPER_IDENTITY'..."
  # Sign embedded frameworks/helpers first (deepest), then the app itself.
  find "$APP_DIR" -type f \( -name "*.dylib" -o -name "*.so" -o -perm +111 \) -print0 | while IFS= read -r -d '' bin; do
    codesign --force --options runtime --sign "$MAC_DEVELOPER_IDENTITY" --timestamp "$bin" 2>/dev/null || true
  done
  codesign --deep --force --options runtime --sign "$MAC_DEVELOPER_IDENTITY" --timestamp "$APP_DIR"
  # Verify the signature.
  if codesign --verify --strict --verbose=2 "$APP_DIR" 2>&1 | grep -q "valid on disk"; then
    SIGNED=1
    echo "[macos-build] Code signature verified."
  else
    echo "[macos-build] WARNING: codesign verification failed; continuing unsigned." >&2
  fi
else
  echo "[macos-build] MAC_DEVELOPER_IDENTITY not set; skipping code signing (unsigned build)."
fi

STAGE="$BUILD_ROOT/$PACKAGE_NAME"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$APP_DIR" "$STAGE/"

DMG_PATH="$DIST_ROOT/$PACKAGE_NAME.dmg"
rm -f "$DMG_PATH"
hdiutil create -volname "Companion AI ${VERSION}" -srcfolder "$STAGE" -ov -format UDZO "$DMG_PATH"

# ---------------------------------------------------------------------------
# Optional notarization + stapling.
# Activated when MAC_APPLE_ID, MAC_APP_SPECIFIC_PASSWORD and MAC_TEAM_ID are
# set. Uses Apple's notarytool to submit the DMG, waits for the result, then
# staples the ticket so offline Gatekeeper checks pass.
# ---------------------------------------------------------------------------
NOTARIZED=0
if [[ "$SIGNED" -eq 1 && -n "${MAC_APPLE_ID:-}" && -n "${MAC_APP_SPECIFIC_PASSWORD:-}" && -n "${MAC_TEAM_ID:-}" ]]; then
  echo "[macos-build] Submitting $DMG_PATH for notarization..."
  SUBMIT_LOG="$BUILD_ROOT/notarize_submit.log"
  if xcrun notarytool submit "$DMG_PATH" \
      --apple-id "$MAC_APPLE_ID" \
      --password "$MAC_APP_SPECIFIC_PASSWORD" \
      --team-id "$MAC_TEAM_ID" \
      --wait --timeout 30m > "$SUBMIT_LOG" 2>&1; then
    if grep -q "status: Accepted" "$SUBMIT_LOG"; then
      echo "[macos-build] Notarization accepted; stapling..."
      if xcrun stapler staple "$DMG_PATH"; then
        NOTARIZED=1
        echo "[macos-build] Stapling complete."
      else
        echo "[macos-build] WARNING: stapler failed; DMG is notarized but not stapled." >&2
      fi
    else
      echo "[macos-build] WARNING: notarization did not return Accepted status." >&2
      cat "$SUBMIT_LOG" >&2
    fi
  else
    echo "[macos-build] WARNING: notarytool submission failed." >&2
    cat "$SUBMIT_LOG" >&2
  fi
else
  echo "[macos-build] Notarization credentials not set; skipping notarization."
fi

echo "[macos-build] Created: $DMG_PATH"
echo "[macos-build] Signed: $SIGNED | Notarized: $NOTARIZED"
if [[ "$SIGNED" -eq 0 ]]; then
  echo "[macos-build] NOTE: This is an UNSIGNED build. macOS Gatekeeper will show a warning."
  echo "[macos-build]       End users can right-click -> Open to bypass, or run:"
  echo "[macos-build]       xattr -dr com.apple.quarantine /Applications/CompanionAI.app"
fi
