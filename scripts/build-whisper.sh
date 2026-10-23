#!/usr/bin/env bash
# Build whisper.cpp's whisper-server into ~/.claude-phone/whisper/bin (Linux and WSL; a Mac uses `brew install whisper-cpp`).
# Needs: sudo apt install build-essential cmake git
# NVIDIA GPU under WSL with the CUDA toolkit installed: GGML_CUDA=1 scripts/build-whisper.sh
set -euo pipefail

VER=v1.9.5
ROOT="${CLAUDE_PHONE_HOME:-$HOME/.claude-phone}"
SRC="$ROOT/src/whisper.cpp"

if [ ! -d "$SRC" ]; then
  git clone --depth 1 --branch "$VER" https://github.com/ggml-org/whisper.cpp "$SRC"
fi
cd "$SRC"
# Static, so the binary runs without the build tree next to it.
cmake -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DWHISPER_BUILD_TESTS=OFF \
  -DGGML_CUDA="${GGML_CUDA:-0}"
cmake --build build -j"$(nproc)" --target whisper-server
mkdir -p "$ROOT/whisper/bin"
cp build/bin/whisper-server "$ROOT/whisper/bin/"
echo "BUILD OK: $ROOT/whisper/bin/whisper-server"
