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
  audit_training train_llm _paths app desktop_pet pystray PIL certifi
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

STAGE="$BUILD_ROOT/$PACKAGE_NAME"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$APP_DIR" "$STAGE/"

DMG_PATH="$DIST_ROOT/$PACKAGE_NAME.dmg"
rm -f "$DMG_PATH"
hdiutil create -volname "Companion AI ${VERSION}" -srcfolder "$STAGE" -ov -format UDZO "$DMG_PATH"

echo "[macos-build] Created: $DMG_PATH"
