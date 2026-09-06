#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
TOOLS=${TOOLS:-"$ROOT/.wasi-tools"}
BUILD=${BUILD:-"$ROOT/build-wasi"}
SDK=${SDK:-"$TOOLS/wasi-sdk-34.0-x86_64-linux"}
CMAKE=${CMAKE:-"$TOOLS/cmake-4.4.3-linux-x86_64/bin/cmake"}
mkdir -p "$BUILD"
# Discard cached compiler paths so an old spike toolchain cannot be reused.
"$CMAKE" --fresh -S "$ROOT" -B "$BUILD" -G Ninja \
  -DCMAKE_MAKE_PROGRAM="$TOOLS/ninja/ninja" \
  -DCMAKE_TOOLCHAIN_FILE="$SDK/share/cmake/wasi-sdk-p1.cmake" \
  -DCMAKE_BUILD_TYPE=MinSizeRel -DPORTABLE=ON -DDISABLE_OWNERSHIP=ON
"$CMAKE" --build "$BUILD" --target inspircd -j "${JOBS:-2}"
