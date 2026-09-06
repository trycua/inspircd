# SPDX-License-Identifier: GPL-2.0-only
# WASI Preview 1, WasmEdge socket extensions, and standardized Wasm exceptions.
set(DISABLE_OWNERSHIP ON CACHE BOOL "" FORCE)
set(SOCKET_ENGINE poll CACHE STRING "" FORCE)
set(CMAKE_SHARED_LIBRARY_SUFFIX ".so")
add_compile_definitions(_WASI_EMULATED_SIGNAL _WASI_EMULATED_PROCESS_CLOCKS _WASI_EMULATED_GETPID)
add_compile_options(-fwasm-exceptions "SHELL:-mllvm -wasm-use-legacy-eh=false")
add_link_options(-fwasm-exceptions -Wl,-z,stack-size=4194304 -Wl,--max-memory=268435456)
link_libraries(unwind wasi-emulated-signal wasi-emulated-process-clocks wasi-emulated-getpid)
include_directories("${PROJECT_SOURCE_DIR}/src")
