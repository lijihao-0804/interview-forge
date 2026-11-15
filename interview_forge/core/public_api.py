"""The single review list of API operations reachable without a session.

Both the authentication middleware and the public-mode acceptance test read
this constant, so adding a public route in one place cannot silently leave the
route list, the static allowlist, or the security test out of sync.  Every API
operation not listed here is private by default.
"""
from __future__ import annotations

PUBLIC_API_OPERATIONS: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/api/health"),
    ("GET", "/api/catalog"),
    ("GET", "/api/search"),
    ("GET", "/api/register/config"),
    ("POST", "/api/login"),
    ("POST", "/api/register"),
    ("POST", "/api/register/send-code"),
    ("POST", "/api/password/forgot/send-code"),
    ("POST", "/api/password/forgot/reset"),
})