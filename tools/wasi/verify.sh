#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
TOOLS=${TOOLS:-"$ROOT/.wasi-tools"}
BUILD=${BUILD:-"$ROOT/build-wasi"}
SDK=${SDK:-"$TOOLS/wasi-sdk-34.0-x86_64-linux"}
export BUILD TOOLS
mkdir -p "$BUILD"
if sh "$ROOT/tools/wasi/build.sh" > "$BUILD/build.log" 2>&1; then
  cat "$BUILD/build.log"
else
  cat "$BUILD/build.log"
  exit 1
fi
"$TOOLS/bin/wasmedge" --version > "$BUILD/tool-versions.log" 2>&1
"$SDK/bin/clang++" --version >> "$BUILD/tool-versions.log" 2>&1
: > "$BUILD/exception-check.log"
for OPT in 0 s 2; do
  "$SDK/bin/clang++" "-O$OPT" -std=c++20 -fPIC -fvisibility=hidden \
    -fvisibility-inlines-hidden -fno-rtti -fwasm-exceptions \
    -mllvm -wasm-use-legacy-eh=false "$ROOT/tools/wasi/check-exceptions.cpp" \
    -lunwind -o "$BUILD/check-exceptions-O$OPT.wasm"
  timeout 30 "$TOOLS/bin/wasmedge" "$BUILD/check-exceptions-O$OPT.wasm" >> "$BUILD/exception-check.log" 2>&1
done
cat "$BUILD/exception-check.log"
"$SDK/bin/clang++" -Os -std=c++20 -fno-rtti -ffunction-sections -fdata-sections \
  -fwasm-exceptions -mllvm -wasm-use-legacy-eh=false \
  -D_WASI_EMULATED_SIGNAL -D_WASI_EMULATED_PROCESS_CLOCKS -D_WASI_EMULATED_GETPID \
  -I"$ROOT/include" -I"$ROOT/src" -I"$BUILD/include" -I"$ROOT/vendor" \
  "$ROOT/tools/wasi/check-casemap.cpp" -lunwind -Wl,--gc-sections \
  -o "$BUILD/check-casemap.wasm"
timeout 30 "$TOOLS/bin/wasmedge" "$BUILD/check-casemap.wasm" > "$BUILD/casemap-check.log" 2>&1
cat "$BUILD/casemap-check.log"
python3 "$ROOT/tools/wasi/test.py"
python3 "$ROOT/tools/wasi/test-invalid-config.py"
