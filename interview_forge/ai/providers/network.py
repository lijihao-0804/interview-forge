"""Pinned outbound transport for bounded provider probes.

The hostname is resolved and validated once.  The HTTP client keeps the
original hostname for the Host header and TLS SNI, while the TCP backend
connects only to the validated address set.  This avoids a second DNS lookup
between validation and connection without disabling certificate validation.
"""
from __future__ import annotations

import socket
from typing import Any, Iterable

import httpcore
import httpx
from httpcore._backends.sync import SyncStream

from interview_forge.ai.config_store import resolve_network_target


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, hostname: str, endpoints: tuple[tuple[int, tuple[Any, ...]], ...]) -> None:
        self.hostname = hostname.rstrip(".").lower()
        self.endpoints = endpoints

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[tuple[Any, ...]] | None = None,
    ) -> httpcore.NetworkStream:
        if host.rstrip(".").lower() != self.hostname:
            raise httpcore.ConnectError("连接目标与已验证主机不一致")
        last_error: BaseException | None = None
        for family, sockaddr in self.endpoints:
            sock = socket.socket(family, socket.SOCK_STREAM)
            connected = False
            try:
                sock.settimeout(timeout)
                if local_address:
                    sock.bind((local_address, 0, 0, 0) if family == socket.AF_INET6 else (local_address, 0))
                for option in socket_options or ():
                    sock.setsockopt(*option)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.connect(sockaddr)
                connected = True
                return SyncStream(sock)
            except socket.timeout as exc:
                last_error = httpcore.ConnectTimeout(str(exc))
            except OSError as exc:
                last_error = httpcore.ConnectError(str(exc))
            finally:
                if not connected:
                    sock.close()
        raise last_error or httpcore.ConnectError("无法连接已验证的 Provider 地址")

    def connect_unix_socket(self, path: str, **_: Any) -> httpcore.NetworkStream:
        raise httpcore.ConnectError("Provider 探测不允许 Unix socket")


class PinnedHTTPTransport(httpx.HTTPTransport):
    """HTTPX transport whose direct TCP connections use one DNS snapshot."""

    def __init__(self, target: str) -> None:
        hostname, endpoints = resolve_network_target(target)
        super().__init__(trust_env=False, retries=0)
        # HTTPTransport exposes a stable httpcore connection pool in the
        # pinned httpx version used by the project.  Only its network backend
        # is replaced; TLS verification and request handling remain HTTPX's.
        self._pool._network_backend = _PinnedNetworkBackend(hostname, endpoints)


__all__ = ["PinnedHTTPTransport"]
