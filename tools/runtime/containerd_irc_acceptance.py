#!/usr/bin/env python3
import socket
import sys
import time


def recv_until(sock, marker, deadline=15):
    end = time.monotonic() + deadline
    data = b""
    while marker not in data:
        if time.monotonic() >= end:
            raise RuntimeError("did not receive %r; got %r" % (marker, data))
        sock.settimeout(max(0.1, end - time.monotonic()))
        data += sock.recv(4096)
    return data


def client(nick):
    sock = socket.create_connection(("127.0.0.1", 6667), timeout=15)
    sock.sendall(("NICK %s\r\nUSER %s 0 * :%s\r\n" % (nick, nick, nick)).encode())
    recv_until(sock, (" 001 %s " % nick).encode())
    sock.sendall(b"JOIN #wasmedge\r\n")
    recv_until(sock, b"JOIN #wasmedge")
    return sock


first = client("alpha")
second = client("beta")
first.sendall(b"PRIVMSG #wasmedge :alpha-to-beta\r\n")
recv_until(second, b"alpha-to-beta")
second.sendall(b"PRIVMSG #wasmedge :beta-to-alpha\r\n")
recv_until(first, b"beta-to-alpha")
for sock in (first, second):
    sock.sendall(b"QUIT :integration-complete\r\n")
    sock.close()
print("two-client IRC registration, join, and bidirectional messaging passed")
