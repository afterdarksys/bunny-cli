"""Cache purge commands."""
from __future__ import annotations

import click

from bunny_cli.client import BunnyClient, PurgeAPI, PullZoneAPI
from bunny_cli.output import print_success


@click.group()
def purge() -> None:
    """Purge CDN cache."""
    pass


@purge.command("url")
@click.argument("url")
def purge_url(url: str) -> None:
    """Purge a specific URL from the CDN cache.

    URL: The full URL to purge (e.g., https://cdn.example.com/path/file.js)
    """
    with BunnyClient() as client:
        api = PurgeAPI(client)
        api.purge_url(url)
        print_success(f"Purged: {url}")


@purge.command("zone")
@click.argument("zone_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def purge_zone(zone_id: int, yes: bool) -> None:
    """Purge all cache for a pull zone.

    ZONE_ID: The pull zone ID to purge
    """
    if not yes:
        click.confirm(
            f"Are you sure you want to purge ALL cache for zone {zone_id}?",
            abort=True,
        )

    with BunnyClient() as client:
        api = PullZoneAPI(client)
        api.purge_cache(zone_id)
        print_success(f"Purged all cache for pull zone {zone_id}")


@purge.command("all")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def purge_all(yes: bool) -> None:
    """Purge cache for ALL pull zones."""
    if not yes:
        click.confirm(
            "Are you sure you want to purge cache for ALL pull zones?",
            abort=True,
        )

    with BunnyClient() as client:
        pz_api = PullZoneAPI(client)
        zones = pz_api.list()

        for zone in zones:
            zone_id = zone.get("Id")
            zone_name = zone.get("Name")
            pz_api.purge_cache(zone_id)
            print_success(f"Purged: {zone_name} (ID: {zone_id})")

        print_success(f"Purged cache for {len(zones)} pull zones")
