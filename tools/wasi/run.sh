#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
TOOLS=${TOOLS:-"$ROOT/.wasi-tools"}
BUILD=${BUILD:-"$ROOT/build-wasi"}
RUNTIME=${RUNTIME:-"$BUILD/runtime"}
VERSION=$("$TOOLS/bin/wasmedge" --version)
VERSION=$(printf '%s\n' "$VERSION" | head -n 1)
case "$VERSION" in
  *" version 0.17.2-rc.1") ;;
  *) echo "Unverified WasmEdge version; bootstrap the pinned runtime (0.17.1 has unsafe exception handling)." >&2; exit 1 ;;
esac
exec "$TOOLS/bin/wasmedge" --dir "/irc:$RUNTIME" "$BUILD/src/inspircd.wasm" --nofork --config /irc/inspircd.conf "$@"
