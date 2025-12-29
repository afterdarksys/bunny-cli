"""Bunny.net API client."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from bunny_cli.config import get_api_key


class BunnyAPIError(Exception):
    """Bunny API error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class BunnyClient:
    """Client for bunny.net API."""

    BASE_URL = "https://api.bunny.net"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_api_key()
        if not self.api_key:
            raise BunnyAPIError(
                "No API key configured. Run 'bunny config set-key' or set BUNNY_API_KEY"
            )
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "AccessKey": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Make an API request."""
        response = self._client.request(method, path, params=params, json=json)

        if response.status_code == 204:
            return None

        if response.status_code >= 400:
            try:
                error = response.json()
                message = error.get("Message", error.get("message", response.text))
            except Exception:
                message = response.text
            raise BunnyAPIError(message, response.status_code)

        if not response.text:
            return None

        return response.json()

    def get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        """GET request."""
        return self._request("GET", path, params=params)

    def post(
        self, path: str, json: Optional[dict[str, Any]] = None, params: Optional[dict[str, Any]] = None
    ) -> Any:
        """POST request."""
        return self._request("POST", path, json=json, params=params)

    def put(self, path: str, json: Optional[dict[str, Any]] = None) -> Any:
        """PUT request."""
        return self._request("PUT", path, json=json)

    def delete(self, path: str) -> Any:
        """DELETE request."""
        return self._request("DELETE", path)

    def close(self) -> None:
        """Close the client."""
        self._client.close()

    def __enter__(self) -> "BunnyClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# Pull Zone API
class PullZoneAPI:
    """Pull Zone API operations."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def list(self, include_certificate: bool = False) -> List[Dict[str, Any]]:
        """List all pull zones."""
        params = {"includeCertificate": str(include_certificate).lower()}
        return self.client.get("/pullzone", params=params)

    def get(self, zone_id: int) -> dict[str, Any]:
        """Get a pull zone by ID."""
        return self.client.get(f"/pullzone/{zone_id}")

    def create(
        self,
        name: str,
        origin_url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a new pull zone."""
        data = {"Name": name, "OriginUrl": origin_url, **kwargs}
        return self.client.post("/pullzone", json=data)

    def update(self, zone_id: int, **kwargs: Any) -> dict[str, Any]:
        """Update a pull zone."""
        return self.client.post(f"/pullzone/{zone_id}", json=kwargs)

    def delete(self, zone_id: int) -> None:
        """Delete a pull zone."""
        self.client.delete(f"/pullzone/{zone_id}")

    def purge_cache(self, zone_id: int) -> None:
        """Purge the entire cache for a pull zone."""
        self.client.post(f"/pullzone/{zone_id}/purgeCache")

    def purge_url(self, zone_id: int, url: str) -> None:
        """Purge a specific URL from cache."""
        self.client.post("/purge", params={"url": url})

    def add_hostname(self, zone_id: int, hostname: str) -> None:
        """Add a custom hostname to a pull zone."""
        self.client.post(f"/pullzone/{zone_id}/addHostname", json={"Hostname": hostname})

    def remove_hostname(self, zone_id: int, hostname: str) -> None:
        """Remove a custom hostname from a pull zone."""
        self.client.delete(f"/pullzone/{zone_id}/removeHostname?hostname={hostname}")

    def load_free_certificate(self, zone_id: int, hostname: str) -> None:
        """Load a free SSL certificate for a hostname."""
        self.client.get(f"/pullzone/{zone_id}/loadFreeCertificate", params={"hostname": hostname})


# DNS Zone API
class DNSZoneAPI:
    """DNS Zone API operations."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def list(self) -> List[Dict[str, Any]]:
        """List all DNS zones."""
        result = self.client.get("/dnszone")
        return result.get("Items", []) if isinstance(result, dict) else result

    def get(self, zone_id: int) -> dict[str, Any]:
        """Get a DNS zone by ID."""
        return self.client.get(f"/dnszone/{zone_id}")

    def create(self, domain: str) -> dict[str, Any]:
        """Create a new DNS zone."""
        return self.client.post("/dnszone", json={"Domain": domain})

    def delete(self, zone_id: int) -> None:
        """Delete a DNS zone."""
        self.client.delete(f"/dnszone/{zone_id}")

    def add_record(
        self,
        zone_id: int,
        record_type: str,
        name: str,
        value: str,
        ttl: int = 300,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add a DNS record."""
        data = {
            "Type": self._record_type_to_int(record_type),
            "Name": name,
            "Value": value,
            "Ttl": ttl,
            **kwargs,
        }
        return self.client.put(f"/dnszone/{zone_id}/records", json=data)

    def update_record(
        self,
        zone_id: int,
        record_id: int,
        **kwargs: Any,
    ) -> None:
        """Update a DNS record."""
        self.client.post(f"/dnszone/{zone_id}/records/{record_id}", json=kwargs)

    def delete_record(self, zone_id: int, record_id: int) -> None:
        """Delete a DNS record."""
        self.client.delete(f"/dnszone/{zone_id}/records/{record_id}")

    @staticmethod
    def _record_type_to_int(record_type: str) -> int:
        """Convert record type string to API integer."""
        types = {
            "A": 0,
            "AAAA": 1,
            "CNAME": 2,
            "TXT": 3,
            "MX": 4,
            "Redirect": 5,
            "Flatten": 6,
            "PullZone": 7,
            "SRV": 8,
            "CAA": 9,
            "PTR": 10,
            "Script": 11,
            "NS": 12,
        }
        return types.get(record_type.upper(), 0)

    @staticmethod
    def _int_to_record_type(type_int: int) -> str:
        """Convert API integer to record type string."""
        types = {
            0: "A",
            1: "AAAA",
            2: "CNAME",
            3: "TXT",
            4: "MX",
            5: "Redirect",
            6: "Flatten",
            7: "PullZone",
            8: "SRV",
            9: "CAA",
            10: "PTR",
            11: "Script",
            12: "NS",
        }
        return types.get(type_int, "Unknown")


# Storage Zone API
class StorageZoneAPI:
    """Storage Zone API operations."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def list(self, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """List all storage zones."""
        params = {"includeDeleted": str(include_deleted).lower()}
        return self.client.get("/storagezone", params=params)

    def get(self, zone_id: int) -> dict[str, Any]:
        """Get a storage zone by ID."""
        return self.client.get(f"/storagezone/{zone_id}")

    def create(
        self,
        name: str,
        region: str = "DE",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a new storage zone."""
        data = {"Name": name, "Region": region, **kwargs}
        return self.client.post("/storagezone", json=data)

    def update(self, zone_id: int, **kwargs: Any) -> dict[str, Any]:
        """Update a storage zone."""
        return self.client.post(f"/storagezone/{zone_id}", json=kwargs)

    def delete(self, zone_id: int) -> None:
        """Delete a storage zone."""
        self.client.delete(f"/storagezone/{zone_id}")


# Statistics API
class StatisticsAPI:
    """Statistics API operations."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def get(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        pull_zone: Optional[int] = None,
        server_zone_id: Optional[int] = None,
        hourly: bool = False,
    ) -> dict[str, Any]:
        """Get statistics."""
        params: dict[str, Any] = {"hourly": str(hourly).lower()}
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        if pull_zone:
            params["pullZone"] = pull_zone
        if server_zone_id:
            params["serverZoneId"] = server_zone_id
        return self.client.get("/statistics", params=params)


# Purge API
class PurgeAPI:
    """Cache purge operations."""

    def __init__(self, client: BunnyClient):
        self.client = client

    def purge_url(self, url: str) -> None:
        """Purge a URL from cache globally."""
        self.client.post("/purge", params={"url": url})

    def purge_pull_zone(self, zone_id: int) -> None:
        """Purge all cache for a pull zone."""
        self.client.post(f"/pullzone/{zone_id}/purgeCache")
