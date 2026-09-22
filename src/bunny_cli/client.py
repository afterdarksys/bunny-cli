"""Bunny.net API client.

Threats: sends the account API key only to https://api.bunny.net and refuses
redirects that would carry AccessKey elsewhere. Response bodies are capped.
Does not rotate keys or detect a stolen key already present on the machine.
"""
from __future__ import annotations

import contextvars
import json
from typing import Any

import httpx

from bunny_cli.config import get_api_key
from bunny_cli.dnsutil import int_to_type, normalize_record_value, record_payload, type_to_int
from bunny_cli.validate import (
    MAX_RESPONSE_BYTES,
    require_api_key,
    require_hostname,
    require_http_url,
    require_tag,
    require_ttl,
    require_zone_id,
)

_command_api_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "bunny_command_api_key",
    default=None,
)
_transport_override: contextvars.ContextVar[httpx.BaseTransport | None] = contextvars.ContextVar(
    "bunny_transport_override",
    default=None,
)

_REDIRECTS = {301, 302, 303, 307, 308}
_MAX_PAGES = 200


class BunnyAPIError(Exception):
    """Bunny API error."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def set_command_api_key(api_key: str | None) -> None:
    """Remember an API key passed on the command line for this invocation."""
    _command_api_key.set(api_key)


def command_api_key() -> str | None:
    """Return the command-line API key for this invocation, if one was passed."""
    return _command_api_key.get()


def install_transport(transport: httpx.BaseTransport | None) -> None:
    """Install an HTTP transport. Tests use this; production leaves it unset."""
    _transport_override.set(transport)


def _read_body(response: httpx.Response) -> bytes:
    if response.status_code in _REDIRECTS:
        raise BunnyAPIError(
            f"Refusing to follow redirect (HTTP {response.status_code})",
            response.status_code,
        )
    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            size = int(declared)
        except ValueError as exc:
            raise BunnyAPIError("Invalid Content-Length from API") from exc
        if size < 0 or size > MAX_RESPONSE_BYTES:
            raise BunnyAPIError("Response exceeded size limit", response.status_code)
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise BunnyAPIError("Response exceeded size limit", response.status_code)
        chunks.append(chunk)
    return b"".join(chunks)


def exchange(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    """Perform one request and decode JSON. Redirects are refused."""
    try:
        with client.stream(method, path, params=params, json=json_body) as response:
            body = _read_body(response)
            status = response.status_code
    except BunnyAPIError:
        raise
    except httpx.TimeoutException as exc:
        raise BunnyAPIError("Request timed out") from exc
    except httpx.HTTPError as exc:
        raise BunnyAPIError("Network request failed") from exc

    if status == 204 or not body:
        if status >= 400:
            raise BunnyAPIError("request failed", status)
        return None

    text = body.decode("utf-8", errors="replace")
    parsed: Any
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None

    if status >= 400:
        message = text
        if isinstance(parsed, dict):
            message = str(
                parsed.get("Message") or parsed.get("message") or parsed.get("errors") or text
            )
            if isinstance(parsed.get("errors"), list) and parsed["errors"]:
                first = parsed["errors"][0]
                if isinstance(first, dict) and first.get("message"):
                    message = str(first["message"])
        raise BunnyAPIError(_short_error(str(message)), status)

    if parsed is None:
        raise BunnyAPIError("API returned invalid JSON", status)
    return parsed


def _short_error(text: str) -> str:
    cleaned = "".join(char if char.isprintable() else " " for char in text)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > 300:
        return cleaned[:300] + "..."
    return cleaned or "request failed"


class BunnyClient:
    """Client for bunny.net API."""

    BASE_URL = "https://api.bunny.net"

    def __init__(self, api_key: str | None = None, *, transport: httpx.BaseTransport | None = None):
        resolved = api_key or _command_api_key.get() or get_api_key()
        if not resolved:
            raise BunnyAPIError(
                "No API key configured. Run 'bunny config set-key' or set BUNNY_API_KEY"
            )
        self.api_key = require_api_key(resolved)
        chosen = transport or _transport_override.get()
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "AccessKey": self.api_key,
                "Accept": "application/json",
                "User-Agent": "bunny-cli",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=False,
            transport=chosen,
        )

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Make an API request."""
        return exchange(self._client, method, path, params=params, json_body=json)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET request."""
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """POST request."""
        return self._request("POST", path, json=json, params=params)

    def put(self, path: str, json: dict[str, Any] | None = None) -> Any:
        """PUT request."""
        return self._request("PUT", path, json=json)

    def delete(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """DELETE request."""
        return self._request("DELETE", path, params=params)

    def get_all(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Collect a list endpoint, following Bunny's page wrapper when present."""
        query = dict(params or {})
        page = 1
        items: list[dict[str, Any]] = []
        while page <= _MAX_PAGES:
            query["page"] = page
            query["perPage"] = 1000
            result = self.get(path, params=query)
            if isinstance(result, list):
                if page != 1:
                    raise BunnyAPIError("Unexpected list response")
                return [row for row in result if isinstance(row, dict)]
            if not isinstance(result, dict) or not isinstance(result.get("Items"), list):
                raise BunnyAPIError("Unexpected list response")
            items.extend(row for row in result["Items"] if isinstance(row, dict))
            if not result.get("HasMoreItems"):
                return items
            page += 1
        raise BunnyAPIError("Pagination limit exceeded")

    def close(self) -> None:
        """Close the client."""
        self._client.close()

    def __enter__(self) -> BunnyClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class PullZoneAPI:
    """Pull Zone API operations."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def list(self, include_certificate: bool = False) -> list[dict[str, Any]]:
        """List all pull zones."""
        params = {"includeCertificate": str(include_certificate).lower()}
        return self.client.get_all("/pullzone", params=params)

    def get(self, zone_id: int) -> dict[str, Any]:
        """Get a pull zone by ID."""
        zone_id = require_zone_id(zone_id)
        result = self.client.get(f"/pullzone/{zone_id}")
        if not isinstance(result, dict):
            raise BunnyAPIError("Unexpected pull zone response")
        return result

    def create(self, name: str, origin_url: str, **kwargs: Any) -> dict[str, Any]:
        """Create a new pull zone."""
        cleaned_name = name.strip()
        too_long = len(cleaned_name) > 100
        unprintable = any(ord(char) < 33 for char in cleaned_name)
        if not cleaned_name or too_long or unprintable:
            raise BunnyAPIError("Pull zone name is invalid")
        data = {
            "Name": cleaned_name,
            "OriginUrl": require_http_url(origin_url, what="Origin URL"),
            **kwargs,
        }
        result = self.client.post("/pullzone", json=data)
        if not isinstance(result, dict):
            raise BunnyAPIError("Unexpected pull zone response")
        return result

    def update(self, zone_id: int, **kwargs: Any) -> dict[str, Any]:
        """Update a pull zone."""
        zone_id = require_zone_id(zone_id)
        if "OriginUrl" in kwargs:
            kwargs["OriginUrl"] = require_http_url(str(kwargs["OriginUrl"]), what="Origin URL")
        result = self.client.post(f"/pullzone/{zone_id}", json=kwargs)
        return result if isinstance(result, dict) else {}

    def delete(self, zone_id: int) -> None:
        """Delete a pull zone."""
        self.client.delete(f"/pullzone/{require_zone_id(zone_id)}")

    def purge_cache(self, zone_id: int, cache_tag: str | None = None) -> None:
        """Purge cache for a pull zone, optionally limited to a CDN tag."""
        zone_id = require_zone_id(zone_id)
        body = {"CacheTag": require_tag(cache_tag)} if cache_tag else None
        self.client.post(f"/pullzone/{zone_id}/purgeCache", json=body)

    def add_hostname(self, zone_id: int, hostname: str) -> None:
        """Add a custom hostname to a pull zone."""
        self.client.post(
            f"/pullzone/{require_zone_id(zone_id)}/addHostname",
            json={"Hostname": require_hostname(hostname)},
        )

    def remove_hostname(self, zone_id: int, hostname: str) -> None:
        """Remove a custom hostname from a pull zone."""
        self.client.delete(
            f"/pullzone/{require_zone_id(zone_id)}/removeHostname",
            params={"hostname": require_hostname(hostname)},
        )

    def load_free_certificate(self, zone_id: int, hostname: str) -> None:
        """Load a free SSL certificate for a hostname."""
        self.client.get(
            f"/pullzone/{require_zone_id(zone_id)}/loadFreeCertificate",
            params={"hostname": require_hostname(hostname)},
        )


class DNSZoneAPI:
    """DNS Zone API operations."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def list(self) -> list[dict[str, Any]]:
        """List all DNS zones."""
        return self.client.get_all("/dnszone")

    def get(self, zone_id: int) -> dict[str, Any]:
        """Get a DNS zone by ID."""
        result = self.client.get(f"/dnszone/{require_zone_id(zone_id)}")
        if not isinstance(result, dict):
            raise BunnyAPIError("Unexpected DNS zone response")
        return result

    def create(self, domain: str) -> dict[str, Any]:
        """Create a new DNS zone."""
        result = self.client.post("/dnszone", json={"Domain": require_hostname(domain)})
        if not isinstance(result, dict):
            raise BunnyAPIError("Unexpected DNS zone response")
        return result

    def delete(self, zone_id: int) -> None:
        """Delete a DNS zone."""
        self.client.delete(f"/dnszone/{require_zone_id(zone_id)}")

    def statistics(
        self,
        zone_id: int,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        """Get DNS query statistics for a zone."""
        params: dict[str, Any] = {}
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        result = self.client.get(f"/dnszone/{require_zone_id(zone_id)}/statistics", params=params)
        if not isinstance(result, dict):
            raise BunnyAPIError("Unexpected statistics response")
        return result

    def add_record(
        self,
        zone_id: int,
        record_type: str,
        name: str,
        value: str,
        ttl: int = 300,
        **kwargs: Any,
    ) -> Any:
        """Add a DNS record."""
        data = record_payload(
            record_type,
            name,
            value,
            ttl,
            priority=kwargs.get("Priority"),
            weight=kwargs.get("Weight"),
            port=kwargs.get("Port"),
            disabled=kwargs.get("Disabled"),
        )
        return self.client.put(f"/dnszone/{require_zone_id(zone_id)}/records", json=data)

    def update_record(self, zone_id: int, record_id: int, **kwargs: Any) -> None:
        """Update a DNS record."""
        zone_id = require_zone_id(zone_id)
        record_id = require_zone_id(record_id, label="record id")
        if "Ttl" in kwargs and kwargs["Ttl"] is not None:
            kwargs["Ttl"] = require_ttl(kwargs["Ttl"])
        if "Value" in kwargs and kwargs["Value"] is not None:
            kwargs["Value"] = normalize_record_value(str(kwargs["Value"]))
        self.client.post(f"/dnszone/{zone_id}/records/{record_id}", json=kwargs)

    def delete_record(self, zone_id: int, record_id: int) -> None:
        """Delete a DNS record."""
        zone = require_zone_id(zone_id)
        record = require_zone_id(record_id, label="record id")
        self.client.delete(f"/dnszone/{zone}/records/{record}")

    @staticmethod
    def _record_type_to_int(record_type: str) -> int:
        """Convert record type string to API integer."""
        return type_to_int(record_type)

    @staticmethod
    def _int_to_record_type(type_int: int) -> str:
        """Convert API integer to record type string."""
        return int_to_type(type_int)


class StorageZoneAPI:
    """Storage Zone API operations."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def list(self, include_deleted: bool = False) -> list[dict[str, Any]]:
        """List all storage zones."""
        params = {"includeDeleted": str(include_deleted).lower()}
        return self.client.get_all("/storagezone", params=params)

    def get(self, zone_id: int) -> dict[str, Any]:
        """Get a storage zone by ID."""
        result = self.client.get(f"/storagezone/{require_zone_id(zone_id)}")
        if not isinstance(result, dict):
            raise BunnyAPIError("Unexpected storage zone response")
        return result

    def create(self, name: str, region: str = "DE", **kwargs: Any) -> dict[str, Any]:
        """Create a new storage zone."""
        cleaned = name.strip()
        if not cleaned or len(cleaned) > 100:
            raise BunnyAPIError("Storage zone name is invalid")
        data = {"Name": cleaned, "Region": region, **kwargs}
        result = self.client.post("/storagezone", json=data)
        if not isinstance(result, dict):
            raise BunnyAPIError("Unexpected storage zone response")
        return result

    def update(self, zone_id: int, **kwargs: Any) -> dict[str, Any]:
        """Update a storage zone."""
        result = self.client.post(f"/storagezone/{require_zone_id(zone_id)}", json=kwargs)
        return result if isinstance(result, dict) else {}

    def delete(self, zone_id: int) -> None:
        """Delete a storage zone."""
        self.client.delete(f"/storagezone/{require_zone_id(zone_id)}")


class StatisticsAPI:
    """Statistics API operations."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def get(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        pull_zone: int | None = None,
        server_zone_id: int | None = None,
        hourly: bool = False,
    ) -> dict[str, Any]:
        """Get statistics."""
        params: dict[str, Any] = {"hourly": str(hourly).lower()}
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        if pull_zone is not None:
            params["pullZone"] = require_zone_id(pull_zone)
        if server_zone_id is not None:
            params["serverZoneId"] = require_zone_id(server_zone_id, label="server zone id")
        result = self.client.get("/statistics", params=params)
        if not isinstance(result, dict):
            raise BunnyAPIError("Unexpected statistics response")
        return result


class PurgeAPI:
    """Cache purge operations."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def purge_url(self, url: str, *, background: bool = False, exact: bool = False) -> None:
        """Purge a URL from cache."""
        params: dict[str, Any] = {"url": require_http_url(url)}
        if background:
            params["async"] = "true"
        if exact:
            params["exactPath"] = "true"
        self.client.post("/purge", params=params)
