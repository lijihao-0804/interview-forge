"""Pinned outbound transport for bounded provider probes.

The hostname is resolved and validated once.  The HTTP client keeps the
original hostname for the Host header and TLS SNI, while the TCP backend
connects only to the validated address set.  This avoids a second DNS lookup
between validation and connection without disabling certificate validation.
"""
from __future__ import annotations

import socket
from typing import Any, Iterable

import anyio
import httpcore
import httpx
from httpcore._backends.anyio import AnyIOStream
from httpcore._exceptions import ConnectError, ConnectTimeout
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


class _PinnedAsyncNetworkBackend(httpcore.AsyncNetworkBackend):
    """Async counterpart used by LangChain streaming clients."""

    def __init__(self, hostname: str, endpoints: tuple[tuple[int, tuple[Any, ...]], ...]) -> None:
        self.hostname = hostname.rstrip(".").lower()
        self.endpoints = endpoints

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[tuple[Any, ...]] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if host.rstrip(".").lower() != self.hostname:
            raise ConnectError("连接目标与已验证主机不一致")
        last_error: BaseException | None = None
        for _family, sockaddr in self.endpoints:
            stream = None
            try:
                # The address comes from the validation snapshot.  HTTPX still
                # keeps the original hostname for TLS SNI and certificate
                # verification while the TCP dial uses only this IP.
                stream = await anyio.connect_tcp(
                    remote_host=str(sockaddr[0]),
                    remote_port=int(sockaddr[1]),
                    local_host=local_address,
                )
                last_error = None
                return AnyIOStream(stream)
            except TimeoutError as exc:
                last_error = ConnectTimeout(str(exc))
            except OSError as exc:
                last_error = ConnectError(str(exc))
            except Exception as exc:
                last_error = ConnectError(str(exc))
            finally:
                if stream is not None and last_error is not None:
                    await stream.aclose()
        raise last_error or ConnectError("无法连接已验证的 Provider 地址")

    async def connect_unix_socket(self, path: str, **_: Any) -> httpcore.AsyncNetworkStream:
        raise ConnectError("Provider 请求不允许 Unix socket")

    async def sleep(self, seconds: float) -> None:
        await anyio.sleep(seconds)


class PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """Async HTTPX transport that dials the already validated DNS snapshot."""

    def __init__(self, target: str) -> None:
        hostname, endpoints = resolve_network_target(target)
        super().__init__(trust_env=False, retries=0)
        self._pool._network_backend = _PinnedAsyncNetworkBackend(hostname, endpoints)


def pinned_http_clients(target: str) -> tuple[httpx.Client, httpx.AsyncClient]:
    """Build bounded sync/async clients for SDKs that accept custom HTTPX clients."""
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=0)
    return (
        httpx.Client(
            transport=PinnedHTTPTransport(target),
            follow_redirects=False,
            trust_env=False,
            limits=limits,
        ),
        httpx.AsyncClient(
            transport=PinnedAsyncHTTPTransport(target),
            follow_redirects=False,
            trust_env=False,
            limits=limits,
        ),
    )


__all__ = ["PinnedAsyncHTTPTransport", "PinnedHTTPTransport", "pinned_http_clients"]
