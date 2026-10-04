"""The locks of the local server (D051). Plain functions, tested without a server.

- The token: random per run, required on every /api request. Another site
  open in the same browser can't send it, because it doesn't know it.
- The Host header: only localhost names. A site that makes its own domain
  resolve to 127.0.0.1 ("DNS rebinding") still sends its domain as the Host.
- The Origin header, when a browser sends one: only the page's own origin.
- Response headers that keep the page from loading anything from elsewhere.
"""

import secrets
from urllib.parse import urlsplit

TOKEN_HEADER = "x-devai-token"
LOCAL_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "::1"})
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",  # the first URL carries the token
    "Cache-Control": "no-store",
}


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_matches(given: str | None, expected: str) -> bool:
    return given is not None and secrets.compare_digest(given, expected)


def hostname(host: str) -> str:
    """The host without its port: "127.0.0.1:8765" → "127.0.0.1", "[::1]:80" → "::1"."""
    return (urlsplit(f"//{host}").hostname or "").lower()


def host_allowed(host: str | None) -> bool:
    """True for localhost names, on any port (Docker may map another one)."""
    return host is not None and hostname(host) in LOCAL_HOSTNAMES


def origin_allowed(origin: str | None, host: str | None) -> bool:
    """True with no Origin (not a browser) or the page's own origin."""
    if origin is None:
        return True
    parts = urlsplit(origin)
    return parts.scheme == "http" and parts.netloc == (host or "").lower()
