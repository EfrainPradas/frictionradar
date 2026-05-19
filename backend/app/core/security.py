"""
Security utilities for FrictionRadar backend.

Provides:
  - SSRF URL validation (block private IPs, file://, metadata endpoints)
  - Timing-safe token comparison (hmac.compare_digest)
  - API key middleware for data endpoints
  - CORS configuration (environment-specific)
  - SSL verification configuration
  - Global exception handler (removes stack traces from responses)
"""

import hmac
import ipaddress
import logging
import os
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("friction_radar.security")


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def is_production() -> bool:
    """Return True when ENVIRONMENT == 'production'."""
    return os.getenv("ENVIRONMENT", "development").lower() == "production"


# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------

def get_allowed_origins() -> list[str]:
    """Return CORS allowed origins.

    Development: ["*"]  (open, but credentials=False)
    Production: parsed from ALLOWED_ORIGINS env var (comma-separated)
    """
    if not is_production():
        return ["*"]

    raw = os.getenv("ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if not origins:
        logger.warning(
            "ALLOWED_ORIGINS is empty in production; "
            "CORS will deny all cross-origin requests"
        )
    return origins


def get_allow_credentials() -> bool:
    """Whether to send Access-Control-Allow-Credentials.

    Browsers reject allow_origins=["*"] + allow_credentials=True,
    so this must be False when origins include "*".
    """
    origins = get_allowed_origins()
    if "*" in origins:
        return False
    return os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------

_PRIVATE_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv4Network("100.64.0.0/10"),   # Carrier-grade NAT
    ipaddress.IPv4Network("198.18.0.0/15"),    # Benchmark testing
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fe80::/10"),
    ipaddress.IPv6Network("fd00::/8"),
    ipaddress.IPv6Network("fc00::/7"),         # Unique-local
]

_ALLOWED_SCHEMES = {"http", "https"}


class SSRFError(ValueError):
    """Raised when a URL fails SSRF validation."""


def validate_url(url: str, *, allow_private: bool = False) -> str:
    """Validate a URL against SSRF rules.

    Blocks: file://, data://, ftp://, and other non-http/https schemes.
    Blocks: localhost, 127.x.x.x, 10.x, 172.16-31.x, 192.168.x,
            169.254.x (cloud metadata), IPv6 equivalents.

    Args:
        url: The URL to validate (must include scheme).
        allow_private: If True, skip private-IP checks (dev/testing only).

    Returns:
        The validated URL string (unchanged).

    Raises:
        SSRFError: If the URL is blocked.
    """
    parsed = urlparse(url)

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise SSRFError(
            f"Scheme '{parsed.scheme}' is not allowed. Only http/https permitted."
        )

    if not parsed.hostname:
        raise SSRFError("URL must contain a hostname.")

    if allow_private:
        return url

    # Block obvious localhost patterns before DNS resolution
    hostname_lower = parsed.hostname.lower()
    if hostname_lower in ("localhost", "localhost.localdomain"):
        raise SSRFError(f"Hostname '{hostname_lower}' is not allowed.")

    # Resolve hostname to IP and check against private ranges
    import socket
    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise SSRFError(f"Cannot resolve hostname: {parsed.hostname}")

    for family, _type, _proto, _canon, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        for network in _PRIVATE_NETWORKS:
            if ip in network:
                raise SSRFError(
                    f"Hostname '{parsed.hostname}' resolves to "
                    f"private/reserved IP {ip}."
                )

    return url


# ---------------------------------------------------------------------------
# Timing-safe token comparison
# ---------------------------------------------------------------------------

def verify_token_constant_time(provided: Optional[str], expected: str) -> bool:
    """Compare a provided token against an expected value in constant time.

    Uses hmac.compare_digest to prevent timing attacks.
    Returns True if they match, False otherwise.
    """
    if not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


# ---------------------------------------------------------------------------
# API key middleware
# ---------------------------------------------------------------------------

_EXEMPT_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/health")
_EXEMPT_EXACT = {"/", "/heatmap"}


def _is_exempt_path(path: str) -> bool:
    """Return True for paths that do not require API key auth."""
    if path in _EXEMPT_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Enforces X-API-Key on data endpoints.

    - Skips health, docs, and static paths.
    - In development with no FRICTIONRADAR_API_KEY set, passes through.
    - In production, FRICTIONRADAR_API_KEY is required.
    """

    async def dispatch(self, request: Request, call_next):
        # CORS preflight must pass without auth
        if request.method == "OPTIONS":
            return await call_next(request)

        if _is_exempt_path(request.url.path):
            return await call_next(request)

        expected_key = os.getenv("FRICTIONRADAR_API_KEY", "")

        # Development mode: no key configured → pass through
        if not is_production() and not expected_key:
            return await call_next(request)

        # Production or key configured: validate
        if is_production() and not expected_key:
            logger.error("FRICTIONRADAR_API_KEY not configured in production")
            return JSONResponse(
                status_code=503,
                content={"detail": "API key not configured on server."},
            )

        provided = request.headers.get("X-API-Key")
        if not verify_token_constant_time(provided, expected_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# SSL verification
# ---------------------------------------------------------------------------

def get_ssl_verify() -> bool:
    """Return whether SSL certificate verification should be enabled.

    Default: True (secure).
    Set FRICTIONRADAR_VERIFY_SSL=false to disable (development only).
    """
    val = os.getenv("FRICTIONRADAR_VERIFY_SSL", "true").lower()
    return val != "false"


# Conditionally suppress urllib3 warnings when SSL verify is off
if not get_ssl_verify():
    import urllib3
    urllib3.disable_warnings()


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

def install_exception_handler(app: FastAPI) -> None:
    """Install a global exception handler that never leaks stack traces."""

    @app.exception_handler(Exception)
    async def _unhandled_exception(request: Request, exc: Exception):
        logger.exception(
            "Unhandled exception on %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error."},
        )