"""Client-address resolution with an explicit trusted-proxy boundary."""
from __future__ import annotations

import ipaddress
import os


def _trusted_proxy_networks() -> tuple[ipaddress._BaseNetwork, ...]:
    networks: list[ipaddress._BaseNetwork] = []
    for raw in os.environ.get("INTERVIEW_FORGE_TRUSTED_PROXIES", "").split(","):
        value = raw.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _peer_address(peer: object) -> ipaddress._BaseAddress | None:
    try:
        return ipaddress.ip_address(str(peer or "").strip())
    except ValueError:
        return None


def _is_trusted(peer: object, networks: tuple[ipaddress._BaseNetwork, ...]) -> bool:
    address = _peer_address(peer)
    if address is None:
        return False
    # The local reverse proxy is the one compatibility trust boundary used by
    # the existing deployment.  Remote peers never gain trust from a header;
    # additional proxies must be listed explicitly.
    if address.is_loopback:
        return True
    return any(address in network for network in networks)


def client_ip(peer: object, headers) -> str:
    """Resolve the client IP without trusting forwarding headers by default.

    Deployments behind nginx/cloudflared must list the immediate proxy address
    or CIDR in ``INTERVIEW_FORGE_TRUSTED_PROXIES``.  Only then is the rightmost
    valid ``X-Forwarded-For`` hop considered; explicit ``X-Real-IP`` and
    ``CF-Connecting-IP`` headers are also accepted from that trusted peer.
    """
    peer_text = str(peer or "").strip()
    networks = _trusted_proxy_networks()
    if not _is_trusted(peer_text, networks):
        return peer_text

    for name in ("x-real-ip", "cf-connecting-ip"):
        candidate = (headers.get(name) or "").strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue

    for candidate in reversed((headers.get("x-forwarded-for") or "").split(",")):
        try:
            return str(ipaddress.ip_address(candidate.strip()))
        except ValueError:
            continue
    return peer_text
