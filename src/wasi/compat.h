// SPDX-License-Identifier: GPL-2.0-only
#pragma once
#include <sys/socket.h>
#include <unistd.h>

#ifndef SOMAXCONN
#define SOMAXCONN 128
#endif

// Bridge only the POSIX calls not provided by wasi-libc to WasmEdge's ABI.
extern "C" {
int socket(int, int, int);
int bind(int, const sockaddr*, socklen_t);
int listen(int, int);
int connect(int, const sockaddr*, socklen_t);
int accept(int, sockaddr*, socklen_t*);
int setsockopt(int, int, int, const void*, socklen_t);
int wasi_getsockname(int, sockaddr*, socklen_t*);
}
#define getsockname wasi_getsockname
