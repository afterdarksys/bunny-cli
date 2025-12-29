"""Pull Zone commands."""
from __future__ import annotations

from typing import Optional

import click

from bunny_cli.client import BunnyClient, PullZoneAPI
from bunny_cli.output import console, print_dict, print_error, print_json, print_success, print_table


@click.group()
def pullzone() -> None:
    """Manage CDN pull zones."""
    pass


@pullzone.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_zones(as_json: bool) -> None:
    """List all pull zones."""
    with BunnyClient() as client:
        api = PullZoneAPI(client)
        zones = api.list()

        if as_json:
            print_json(zones)
        else:
            print_table(
                zones,
                columns=["Id", "Name", "OriginUrl", "Enabled", "MonthlyBandwidthUsed"],
                headers=["ID", "Name", "Origin", "Enabled", "Bandwidth"],
            )


@pullzone.command("get")
@click.argument("zone_id", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def get_zone(zone_id: int, as_json: bool) -> None:
    """Get details for a pull zone."""
    with BunnyClient() as client:
        api = PullZoneAPI(client)
        zone = api.get(zone_id)

        if as_json:
            print_json(zone)
        else:
            # Show key fields
            display = {
                "ID": zone.get("Id"),
                "Name": zone.get("Name"),
                "Origin URL": zone.get("OriginUrl"),
                "Enabled": zone.get("Enabled"),
                "Hostnames": ", ".join(h.get("Value", "") for h in zone.get("Hostnames", [])),
                "Monthly Bandwidth": f"{zone.get('MonthlyBandwidthUsed', 0) / 1024 / 1024 / 1024:.2f} GB",
                "Cache Enabled": zone.get("EnableCacheSlice"),
                "CORS Enabled": zone.get("EnableAccessControlOriginHeader"),
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
    with BunnyClient() as client:
        api = PullZoneAPI(client)
        zone = api.create(name, origin_url)

        if as_json:
            print_json(zone)
        else:
            print_success(f"Created pull zone: {zone.get('Name')} (ID: {zone.get('Id')})")
            console.print(f"CDN URL: https://{name}.b-cdn.net")


@pullzone.command("update")
@click.argument("zone_id", type=int)
@click.option("--origin-url", help="New origin URL")
@click.option("--enabled/--disabled", default=None, help="Enable or disable the zone")
@click.option("--cache-enabled/--cache-disabled", default=None, help="Enable or disable caching")
def update_zone(
    zone_id: int,
    origin_url: Optional[str],
    enabled: Optional[bool],
    cache_enabled: Optional[bool],
) -> None:
    """Update a pull zone."""
    kwargs = {}
    if origin_url:
        kwargs["OriginUrl"] = origin_url
    if enabled is not None:
        kwargs["Enabled"] = enabled
    if cache_enabled is not None:
        kwargs["EnableCacheSlice"] = cache_enabled

    if not kwargs:
        raise click.ClickException("No updates specified")

    with BunnyClient() as client:
        api = PullZoneAPI(client)
        api.update(zone_id, **kwargs)
        print_success(f"Updated pull zone {zone_id}")


@pullzone.command("delete")
@click.argument("zone_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_zone(zone_id: int, yes: bool) -> None:
    """Delete a pull zone."""
    if not yes:
        click.confirm(f"Are you sure you want to delete pull zone {zone_id}?", abort=True)

    with BunnyClient() as client:
        api = PullZoneAPI(client)
        api.delete(zone_id)
        print_success(f"Deleted pull zone {zone_id}")


@pullzone.command("purge")
@click.argument("zone_id", type=int)
@click.option("--url", help="Specific URL to purge (otherwise purges entire zone)")
def purge_cache(zone_id: int, url: Optional[str]) -> None:
    """Purge cache for a pull zone."""
    with BunnyClient() as client:
        api = PullZoneAPI(client)
        if url:
            api.purge_url(zone_id, url)
            print_success(f"Purged URL: {url}")
        else:
            api.purge_cache(zone_id)
            print_success(f"Purged all cache for pull zone {zone_id}")


@pullzone.command("add-hostname")
@click.argument("zone_id", type=int)
@click.argument("hostname")
def add_hostname(zone_id: int, hostname: str) -> None:
    """Add a custom hostname to a pull zone."""
    with BunnyClient() as client:
        api = PullZoneAPI(client)
        api.add_hostname(zone_id, hostname)
        print_success(f"Added hostname {hostname} to pull zone {zone_id}")


@pullzone.command("remove-hostname")
@click.argument("zone_id", type=int)
@click.argument("hostname")
def remove_hostname(zone_id: int, hostname: str) -> None:
    """Remove a custom hostname from a pull zone."""
    with BunnyClient() as client:
        api = PullZoneAPI(client)
        api.remove_hostname(zone_id, hostname)
        print_success(f"Removed hostname {hostname} from pull zone {zone_id}")


@pullzone.command("ssl")
@click.argument("zone_id", type=int)
@click.argument("hostname")
def load_ssl(zone_id: int, hostname: str) -> None:
    """Request a free SSL certificate for a hostname."""
    with BunnyClient() as client:
        api = PullZoneAPI(client)
        api.load_free_certificate(zone_id, hostname)
        print_success(f"SSL certificate requested for {hostname}")
