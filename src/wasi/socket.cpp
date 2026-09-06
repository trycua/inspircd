// SPDX-License-Identifier: GPL-2.0-only
#include "wasi/compat.h"
#include <arpa/inet.h>
#include <cerrno>
#include <cstdint>
#include <cstring>

#define IMPORT(name) __attribute__((import_module("wasi_snapshot_preview1"), import_name(#name)))
extern "C" {
IMPORT(sock_open_v2) uint32_t sock_open_v2(uint32_t, uint32_t, uint32_t*);
IMPORT(sock_bind_v2) uint32_t sock_bind_v2(int32_t, const void*, uint32_t);
IMPORT(sock_listen_v2) uint32_t sock_listen_v2(int32_t, int32_t);
IMPORT(sock_accept_v2) uint32_t sock_accept_v2(int32_t, uint32_t, uint32_t*);
IMPORT(sock_getlocaladdr_v2) uint32_t sock_getlocaladdr_v2(int32_t, void*, uint32_t*);
IMPORT(sock_getpeeraddr_v2) uint32_t sock_getpeeraddr_v2(int32_t, void*, uint32_t*);
}
namespace {
struct Address { void* data; uint32_t size; };
int result(uint32_t error) { if (!error) return 0; errno = error; return -1; }
int name(int fd, sockaddr* output, socklen_t* length, bool peer)
{
    struct { uint16_t family; uint8_t bytes[126]; } storage{};
    Address address{&storage, sizeof(storage)};
    uint32_t port = 0;
    if (result(peer ? sock_getpeeraddr_v2(fd, &address, &port) : sock_getlocaladdr_v2(fd, &address, &port)))
        return -1;
    sockaddr_storage native{};
    socklen_t size;
    if (storage.family == 1)
    {
        auto* ip = reinterpret_cast<sockaddr_in*>(&native);
        ip->sin_family = AF_INET; ip->sin_port = htons(port);
        memcpy(&ip->sin_addr, storage.bytes, 4); size = sizeof(*ip);
    }
    else if (storage.family == 2)
    {
        auto* ip = reinterpret_cast<sockaddr_in6*>(&native);
        ip->sin6_family = AF_INET6; ip->sin6_port = htons(port);
        memcpy(&ip->sin6_addr, storage.bytes, 16); size = sizeof(*ip);
    }
    else { errno = EAFNOSUPPORT; return -1; }
    memcpy(output, &native, *length < size ? *length : size); *length = size;
    return 0;
}
}
extern "C" int socket(int family, int type, int protocol)
{
    if ((family != AF_INET && family != AF_INET6) || type != SOCK_STREAM || (protocol && protocol != IPPROTO_TCP))
    { errno = EPROTONOSUPPORT; return -1; }
    uint32_t fd;
    if (result(sock_open_v2(family == AF_INET ? 1 : 2, 2, &fd))) return -1;
    return fd;
}
extern "C" int bind(int fd, const sockaddr* addr, socklen_t length)
{
    Address address{}; uint16_t port;
    if (addr->sa_family == AF_INET && length >= sizeof(sockaddr_in))
    {
        auto* ip = reinterpret_cast<const sockaddr_in*>(addr);
        address = {const_cast<in_addr*>(&ip->sin_addr), 4}; port = ntohs(ip->sin_port);
    }
    else if (addr->sa_family == AF_INET6 && length >= sizeof(sockaddr_in6))
    {
        auto* ip = reinterpret_cast<const sockaddr_in6*>(addr);
        address = {const_cast<in6_addr*>(&ip->sin6_addr), 16}; port = ntohs(ip->sin6_port);
    }
    else { errno = EAFNOSUPPORT; return -1; }
    return result(sock_bind_v2(fd, &address, port));
}
extern "C" int listen(int fd, int backlog) { return result(sock_listen_v2(fd, backlog)); }
extern "C" int accept(int fd, sockaddr* addr, socklen_t* length)
{
    uint32_t client;
    if (result(sock_accept_v2(fd, 0, &client))) return -1;
    if (addr && name(client, addr, length, true)) { close(client); return -1; }
    return client;
}
extern "C" int wasi_getsockname(int fd, sockaddr* addr, socklen_t* length) { return name(fd, addr, length, false); }
// Unsupported options and outgoing connections fail explicitly, never pretend success.
extern "C" int setsockopt(int, int, int, const void*, socklen_t) { errno = ENOPROTOOPT; return -1; }
extern "C" int connect(int, const sockaddr*, socklen_t) { errno = ENOTSUP; return -1; }
