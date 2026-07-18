#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
VERSION="$(tr -d '[:space:]' < "$ROOT/version.txt")"
ARCH="$(uname -m)"

case "$ARCH" in
  x86_64|amd64) DEB_ARCH="amd64"; PACKAGE_ARCH="x86_64" ;;
  aarch64|arm64) DEB_ARCH="arm64"; PACKAGE_ARCH="arm64" ;;
  *)
    echo "Unsupported Linux architecture: $ARCH" >&2
    exit 1
    ;;
esac

VENV="${BUILD_VENV:-$ROOT/.venv-linux}"
BUILD_ROOT="$ROOT/build/linux"
DIST_ROOT="$ROOT/dist/linux"
APP_NAME="CompanionAI"
PACKAGE_NAME="companion-ai-${VERSION}-linux-${PACKAGE_ARCH}"

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

echo "[linux-build] Building Companion AI ${VERSION} for ${PACKAGE_ARCH}..."
"$PY" -m PyInstaller "${PYINSTALLER_ARGS[@]}" "$ROOT/companion_launcher.py"

APP_DIR="$DIST_ROOT/$APP_NAME"
if [[ ! -x "$APP_DIR/$APP_NAME" ]]; then
  echo "PyInstaller did not produce $APP_DIR/$APP_NAME" >&2
  exit 1
fi

STAGE="$BUILD_ROOT/$PACKAGE_NAME"
rm -rf "$STAGE"
mkdir -p "$STAGE/opt/companion-ai" "$STAGE/usr/bin" "$STAGE/usr/share/applications"
cp -a "$APP_DIR/." "$STAGE/opt/companion-ai/"
install -m 0755 "$ROOT/packaging/linux/companion-ai" "$STAGE/usr/bin/companion-ai"
install -m 0644 "$ROOT/packaging/linux/companion-ai.desktop" "$STAGE/usr/share/applications/companion-ai.desktop"
install -m 0755 "$ROOT/packaging/linux/install-user.sh" "$STAGE/install-user.sh"

tar -C "$BUILD_ROOT" -czf "$DIST_ROOT/$PACKAGE_NAME.tar.gz" "$PACKAGE_NAME"

DEB_ROOT="$BUILD_ROOT/deb"
mkdir -p "$DEB_ROOT/DEBIAN" "$DEB_ROOT/opt/companion-ai" "$DEB_ROOT/usr/bin" "$DEB_ROOT/usr/share/applications"
cp -a "$APP_DIR/." "$DEB_ROOT/opt/companion-ai/"
install -m 0755 "$ROOT/packaging/linux/companion-ai" "$DEB_ROOT/usr/bin/companion-ai"
install -m 0644 "$ROOT/packaging/linux/companion-ai.desktop" "$DEB_ROOT/usr/share/applications/companion-ai.desktop"
cat > "$DEB_ROOT/DEBIAN/control" <<EOF
Package: companion-ai
Version: $VERSION
Section: utils
Priority: optional
Architecture: $DEB_ARCH
Maintainer: LoongSerpent9Realms
Description: Local-first AI companion desktop pet
 Companion AI provides local chat, memory, training, and desktop pet features.
EOF
dpkg-deb --build --root-owner-group "$DEB_ROOT" "$DIST_ROOT/$PACKAGE_NAME.deb" >/dev/null

echo "[linux-build] Created:"
echo "  $DIST_ROOT/$PACKAGE_NAME.tar.gz"
echo "  $DIST_ROOT/$PACKAGE_NAME.deb"
