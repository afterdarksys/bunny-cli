"""Input checks for the CLI.

Threats: rejects malformed URLs, hostnames, record fields, and API keys
before they are sent. Does not prove a hostname is owned by the caller
or that an origin URL is safe to cache.
"""
from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import NoReturn
from urllib.parse import urlsplit, urlunsplit

import click

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_URL_LENGTH = 2048
MAX_HOSTNAME_LENGTH = 253
MAX_DNS_VALUE = 4096
MAX_DNS_NAME = 253
MAX_TAG_LENGTH = 1024
MIN_API_KEY_LENGTH = 16
MAX_API_KEY_LENGTH = 256
MIN_TTL = 15
MAX_TTL = 30 * 24 * 60 * 60
MAX_ZONE_ID = 2**63 - 1

_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_CF_ZONE = re.compile(r"^[a-f0-9]{32}$")


def _fail(message: str) -> NoReturn:
    raise click.ClickException(message)


def require_api_key(api_key: str) -> str:
    """Return a stripped API key or raise."""
    key = api_key.strip()
    if not (MIN_API_KEY_LENGTH <= len(key) <= MAX_API_KEY_LENGTH):
        _fail(
            f"API key must be {MIN_API_KEY_LENGTH}-{MAX_API_KEY_LENGTH} characters"
        )
    if any(ord(char) < 33 or ord(char) > 126 for char in key):
        _fail("API key contains unsupported characters")
    return key


def require_zone_id(zone_id: int, *, label: str = "zone id") -> int:
    """Return a positive zone id or raise."""
    if isinstance(zone_id, bool) or not isinstance(zone_id, int):
        _fail(f"Invalid {label}")
    if zone_id < 1 or zone_id > MAX_ZONE_ID:
        _fail(f"Invalid {label}")
    return zone_id


def require_cf_zone_id(zone_id: str) -> str:
    """Return a Cloudflare zone id or raise."""
    cleaned = zone_id.strip().lower()
    if not _CF_ZONE.fullmatch(cleaned):
        _fail("Cloudflare zone id must be 32 hex characters")
    return cleaned


def require_ttl(ttl: int) -> int:
    """Return a TTL inside Bunny's accepted window or raise."""
    if isinstance(ttl, bool) or not isinstance(ttl, int) or not (MIN_TTL <= ttl <= MAX_TTL):
        _fail(f"TTL must be an integer from {MIN_TTL} to {MAX_TTL} seconds")
    return ttl


def require_http_url(url: str, *, what: str = "URL") -> str:
    """Return an http(s) URL without control characters or raise."""
    cleaned = url.strip()
    if not cleaned or len(cleaned) > MAX_URL_LENGTH:
        _fail(f"{what} length is invalid")
    if any(ord(char) < 33 or ord(char) == 127 for char in cleaned):
        _fail(f"{what} contains unsupported characters")
    parts = urlsplit(cleaned)
    host = parts.hostname
    if parts.scheme not in {"http", "https"} or host is None:
        _fail(f"{what} must be an absolute http or https URL")
    host = host.lower().rstrip(".")
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".localhost"):
        _fail(f"{what} must not target a local or metadata hostname")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or address.is_reserved
    ):
        _fail(f"{what} must not target a local or link-local address")
    return cleaned


def redact_url(url: str) -> str:
    """Hide userinfo passwords when a URL is printed."""
    parts = urlsplit(url)
    if parts.password is None:
        return url
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    user = parts.username or ""
    netloc = f"{user}:***@{host}" if user else f"***@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def require_hostname(hostname: str) -> str:
    """Return a lowercase ASCII hostname or raise.

    A single leading ``*.`` wildcard is allowed. International names must
    already be in punycode.
    """
    cleaned = hostname.strip().rstrip(".").lower()
    candidate = cleaned[2:] if cleaned.startswith("*.") else cleaned
    if (
        not cleaned
        or len(cleaned) > MAX_HOSTNAME_LENGTH
        or not _HOSTNAME.fullmatch(candidate)
        or candidate in {"localhost"}
        or candidate.endswith(".localhost")
    ):
        _fail("Hostname must be a DNS name (use punycode for international names)")
    return cleaned


def require_date(value: str, *, flag: str) -> str:
    """Return a YYYY-MM-DD date or raise."""
    cleaned = value.strip()
    try:
        parsed = datetime.strptime(cleaned, "%Y-%m-%d")
    except ValueError:
        _fail(f"{flag} must be YYYY-MM-DD")
    return parsed.strftime("%Y-%m-%d")


def require_tag(tag: str) -> str:
    """Return a CDN cache tag or raise."""
    cleaned = tag.strip()
    if not cleaned or len(cleaned) > MAX_TAG_LENGTH:
        _fail(f"Cache tag must be 1-{MAX_TAG_LENGTH} characters")
    if any(ord(char) < 33 or ord(char) == 127 for char in cleaned):
        _fail("Cache tag contains unsupported characters")
    return cleaned
