from __future__ import annotations

from ipaddress import ip_address, ip_network
from aiohttp import web

from app.core.settings import get_settings


def _is_trusted(remote: str | None) -> bool:
    if not remote:
        return False
    ip = ip_address(remote)
    return any(ip in net for net in get_settings().trusted_proxy_networks)


def client_ip(request: web.Request) -> str:
    peer = request.remote
    if not _is_trusted(peer):
        return peer or "0.0.0.0"
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf.strip()
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("X-Real-IP", peer or "0.0.0.0")


def subnet24(ip: str) -> str:
    obj = ip_address(ip)
    if obj.version == 4:
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    return str(ip_network(f"{obj}/64", strict=False))
