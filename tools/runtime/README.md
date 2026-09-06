# Runtime Compatibility Experiments

This directory holds reproducible, isolated compatibility work for the experimental RuntimeClass deployment path. It does not modify a cluster node or enable Flux.

## WasmEdge Rust binding patch

`patches/wasmedge-rust-sdk-0.14.0-wasmedge-0.17.2-rc.1.patch` applies to the official WasmEdge Rust SDK tag `0.14.0` at commit `e7a74ab1837c43f609f26510cf3c456e9b9c2026` (Apache-2.0). It adapts the C binding layer to the checksum-pinned WasmEdge `0.17.2-rc.1` headers selected by `tools/wasi/toolchain.json`.

The patch preserves caller ownership of new `WasmEdge_LimitContext` values, destroys each temporary limit after the C type constructor returns, and uses checked conversions where the Rust SDK remains limited to wasm32 page counts. The CI workflow builds it only with pinned source and runtime inputs, then records its build and dynamic-link evidence.
