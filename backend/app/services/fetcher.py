"""Outbound URL fetcher for content import.

A small Protocol + factory (mirrors ``get_storage()`` / ``get_embedder()``) so the
endpoint depends on an interface, the real implementation uses httpx, and tests inject a
``FakeFetcher`` via :func:`set_fetcher` — no network. The real fetcher applies a timeout,
a byte cap, a content-type allowlist, and a best-effort SSRF guard (rejects non-HTTP(S)
schemes and hosts that resolve into private/loopback/link-local ranges).
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from app.core.config import settings


class FetchError(Exception):
    """A URL could not be safely fetched (bad scheme/host, too large, wrong type, network)."""


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    content: bytes
    content_type: str


class Fetcher(Protocol):
    async def fetch(self, url: str) -> FetchResult: ...


class FakeFetcher:
    """Deterministic, offline fetcher for tests — returns canned responses by URL."""

    def __init__(self, responses: dict[str, FetchResult]) -> None:
        self._responses = responses

    async def fetch(self, url: str) -> FetchResult:
        if url not in self._responses:
            raise FetchError(f"FakeFetcher has no canned response for {url!r}.")
        return self._responses[url]


_ALLOWED_CONTENT_PREFIXES = ("text/html", "text/plain", "application/xhtml")


def _assert_safe_url(url: str) -> str:
    """Reject non-HTTP(S) URLs and hosts that resolve to private/loopback/link-local IPs.

    Best-effort SSRF defense (note: residual TOCTOU / DNS-rebinding risk between this
    check and the actual request — acceptable for v1; a fetch proxy would close it)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("Only http/https URLs may be imported.")
    host = parsed.hostname
    if not host:
        raise FetchError("URL has no host.")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve host: {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError("Refusing to fetch a private/loopback/link-local address.")
    return host


class HttpxFetcher:
    async def fetch(self, url: str) -> FetchResult:
        _assert_safe_url(url)
        import httpx

        cap = settings.URL_IMPORT_MAX_BYTES
        try:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True, max_redirects=3
            ) as client, client.stream("GET", url) as resp:
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "").lower()
                if not ctype.startswith(_ALLOWED_CONTENT_PREFIXES):
                    raise FetchError(f"Unsupported content type for import: {ctype!r}.")
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > cap:
                        raise FetchError("Imported page exceeds the size limit.")
                    chunks.append(chunk)
                return FetchResult(
                    url=url,
                    final_url=str(resp.url),
                    content=b"".join(chunks),
                    content_type=ctype,
                )
        except httpx.HTTPError as exc:
            raise FetchError(f"Failed to fetch URL: {exc}") from exc


# Test-injectable override (lru_cache makes monkeypatching brittle, so use an explicit hook).
_override: Fetcher | None = None


def set_fetcher(fetcher: Fetcher | None) -> None:
    """Install (or clear, with ``None``) a fetcher — used by tests to inject a fake."""
    global _override
    _override = fetcher


def get_fetcher() -> Fetcher:
    return _override if _override is not None else HttpxFetcher()
