"""Outbound URL policy for remote targets: no SSRF into private networks by default."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from .errors import TargetError

__all__ = ["GuardedTransport", "UrlPolicy", "check_url", "resolve_host"]

Resolver = Callable[[str], Awaitable[list[str]]]


@dataclass(frozen=True)
class UrlPolicy:
    allow_private: bool = False
    local_hosts: frozenset[str] = field(default_factory=frozenset)


def _blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip.split("%")[0])
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_unspecified
        or addr.is_multicast
    )


def _exempt(host: str, policy: UrlPolicy) -> bool:
    return policy.allow_private or host.lower() in policy.local_hosts


def check_url(url: str, policy: UrlPolicy) -> None:
    """Static checks: scheme, credentials, and IP-literal hosts. Raises TargetError."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise TargetError("blocked_url", f"scheme {parts.scheme!r} is not allowed")
    if parts.username or parts.password:
        raise TargetError("blocked_url", "credentials in URL are not allowed")
    host = parts.hostname
    if not host:
        raise TargetError("blocked_url", "URL has no host")
    if _exempt(host, policy):
        return
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        return  # a name: checked after resolution, at connect time
    if _blocked_ip(str(literal)):
        raise TargetError("blocked_url", f"host {host} is a private or reserved address")


async def resolve_host(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(i[4][0]) for i in infos})


class GuardedTransport(httpx.AsyncBaseTransport):
    """Re-checks the URL and the resolved addresses on every request (DNS rebinding)."""

    def __init__(
        self,
        inner: httpx.AsyncBaseTransport,
        policy: UrlPolicy,
        resolver: Resolver = resolve_host,
    ) -> None:
        self._inner, self._policy, self._resolve = inner, policy, resolver

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        check_url(url, self._policy)
        host = request.url.host
        if not _exempt(host, self._policy):
            try:
                ipaddress.ip_address(host)
            except ValueError:
                for ip in await self._resolve(host):
                    if _blocked_ip(ip):
                        raise TargetError(
                            "blocked_url", f"{host} resolves to private address"
                        ) from None
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()
