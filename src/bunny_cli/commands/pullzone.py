"""Pull Zone commands."""
from __future__ import annotations

from typing import Any

import click

from bunny_cli.client import BunnyClient, PullZoneAPI, PurgeAPI
from bunny_cli.config import selected_zone
from bunny_cli.output import (
    console,
    format_bytes,
    print_dict,
    print_json,
    print_success,
    print_table,
    wants_json,
)
from bunny_cli.validate import redact_url, require_hostname, require_http_url, require_tag


@click.group()
def pullzone() -> None:
    """Manage CDN pull zones."""
    pass


def _hostname_count(zone: dict[str, Any]) -> int:
    hostnames = zone.get("Hostnames") or []
    return len(hostnames) if isinstance(hostnames, list) else 0


@pullzone.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_zones(as_json: bool) -> None:
    """List all pull zones."""
    with BunnyClient() as client:
        zones = PullZoneAPI(client).list()
        if wants_json(as_json):
            print_json(zones)
            return
        rows = []
        for zone in zones:
            rows.append(
                {
                    "Id": zone.get("Id"),
                    "Name": zone.get("Name"),
                    "OriginUrl": zone.get("OriginUrl"),
                    "Enabled": zone.get("Enabled"),
                    "Bandwidth": format_bytes(float(zone.get("MonthlyBandwidthUsed") or 0)),
                    "Hostnames": _hostname_count(zone),
                }
            )
        print_table(
            rows,
            columns=["Id", "Name", "OriginUrl", "Enabled", "Bandwidth", "Hostnames"],
            headers=["ID", "Name", "Origin", "Enabled", "Bandwidth", "Hostnames"],
        )


@pullzone.command("get")
@click.argument("zone_id", type=int, required=False)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def get_zone(zone_id: int | None, as_json: bool) -> None:
    """Get details for a pull zone.

    ZONE_ID is optional when default_pull_zone is configured.
    """
    zone_id = selected_zone(zone_id, "pull")
    with BunnyClient() as client:
        zone = PullZoneAPI(client).get(zone_id)
        if wants_json(as_json):
            print_json(zone)
            return
        hostnames = zone.get("Hostnames") or []
        names = ", ".join(item.get("Value", "") for item in hostnames if isinstance(item, dict))
        display = {
            "ID": zone.get("Id"),
            "Name": zone.get("Name"),
            "Origin URL": zone.get("OriginUrl"),
            "Enabled": zone.get("Enabled"),
            "Hostnames": names or None,
            "Monthly Bandwidth": format_bytes(float(zone.get("MonthlyBandwidthUsed") or 0)),
            "Cache Slice": zone.get("EnableCacheSlice"),
            "CORS Header": zone.get("EnableAccessControlOriginHeader"),
        }
        print_dict(display, f"Pull Zone: {zone.get('Name')}")


@pullzone.command("create")
@click.argument("name")
@click.argument("origin_url")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create_zone(name: str, origin_url: str, as_json: bool) -> None:
    """Create a new pull zone.

    NAME: Name for the pull zone (used in *.b-cdn.net URL)
    ORIGIN_URL: Origin server URL (e.g., https://example.com)
    """
    origin_url = require_http_url(origin_url, what="Origin URL")
    with BunnyClient() as client:
        zone = PullZoneAPI(client).create(name, origin_url)
        if wants_json(as_json):
            print_json(zone)
            return
        print_success(f"Created pull zone: {zone.get('Name')} (ID: {zone.get('Id')})")
        console.print(f"CDN URL: https://{name.strip()}.b-cdn.net")
        console.print(f"Origin: {redact_url(origin_url)}")


@pullzone.command("update")
@click.argument("zone_id", type=int)
@click.option("--origin-url", help="New origin URL")
@click.option("--enabled/--disabled", default=None, help="Enable or disable the zone")
@click.option("--cache-enabled/--cache-disabled", default=None, help="Toggle cache slice")
def update_zone(
    zone_id: int,
    origin_url: str | None,
    enabled: bool | None,
    cache_enabled: bool | None,
) -> None:
    """Update a pull zone."""
    kwargs: dict[str, Any] = {}
    if origin_url:
        kwargs["OriginUrl"] = require_http_url(origin_url, what="Origin URL")
    if enabled is not None:
        kwargs["Enabled"] = enabled
    if cache_enabled is not None:
        kwargs["EnableCacheSlice"] = cache_enabled
    if not kwargs:
        raise click.ClickException("No updates specified")

    with BunnyClient() as client:
        PullZoneAPI(client).update(zone_id, **kwargs)
        print_success(f"Updated pull zone {zone_id}")


@pullzone.command("delete")
@click.argument("zone_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_zone(zone_id: int, yes: bool) -> None:
    """Delete a pull zone."""
    if not yes:
        click.confirm(f"Are you sure you want to delete pull zone {zone_id}?", abort=True)

    with BunnyClient() as client:
        PullZoneAPI(client).delete(zone_id)
        print_success(f"Deleted pull zone {zone_id}")


@pullzone.command("purge")
@click.argument("zone_id", type=int)
@click.option("--url", help="Specific URL to purge (otherwise purges the zone or a tag)")
@click.option("--tag", help="Purge responses tagged with this CDN-Tag value")
@click.option("--exact", is_flag=True, help="Purge only the exact URL path")
@click.option("--background", is_flag=True, help="Return before the URL purge finishes")
def purge_cache(
    zone_id: int,
    url: str | None,
    tag: str | None,
    exact: bool,
    background: bool,
) -> None:
    """Purge cache for a pull zone."""
    if url and tag:
        raise click.ClickException("Use either --url or --tag")
    with BunnyClient() as client:
        api = PullZoneAPI(client)
        if url:
            PurgeAPI(client).purge_url(url, background=background, exact=exact)
            print_success(f"Purged URL: {redact_url(url)}")
            return
        if exact or background:
            raise click.ClickException("--exact and --background apply to --url purges")
        api.purge_cache(zone_id, require_tag(tag) if tag else None)
        if tag:
            print_success(f"Purged cache tag {tag} on pull zone {zone_id}")
        else:
            print_success(f"Purged all cache for pull zone {zone_id}")


@pullzone.command("add-hostname")
@click.argument("zone_id", type=int)
@click.argument("hostname")
def add_hostname(zone_id: int, hostname: str) -> None:
    """Add a custom hostname to a pull zone."""
    hostname = require_hostname(hostname)
    with BunnyClient() as client:
        PullZoneAPI(client).add_hostname(zone_id, hostname)
        print_success(f"Added hostname {hostname} to pull zone {zone_id}")


@pullzone.command("remove-hostname")
@click.argument("zone_id", type=int)
@click.argument("hostname")
def remove_hostname(zone_id: int, hostname: str) -> None:
    """Remove a custom hostname from a pull zone."""
    hostname = require_hostname(hostname)
    with BunnyClient() as client:
        PullZoneAPI(client).remove_hostname(zone_id, hostname)
        print_success(f"Removed hostname {hostname} from pull zone {zone_id}")


@pullzone.command("ssl")
@click.argument("zone_id", type=int)
@click.argument("hostname")
def load_ssl(zone_id: int, hostname: str) -> None:
    """Request a free SSL certificate for a hostname."""
    hostname = require_hostname(hostname)
    with BunnyClient() as client:
        PullZoneAPI(client).load_free_certificate(zone_id, hostname)
        print_success(f"SSL certificate requested for {hostname}")
