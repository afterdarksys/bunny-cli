"""Cache purge commands."""
from __future__ import annotations

import click

from bunny_cli.client import BunnyClient, PullZoneAPI, PurgeAPI
from bunny_cli.output import print_success
from bunny_cli.validate import redact_url, require_tag


@click.group()
def purge() -> None:
    """Purge CDN cache."""
    pass


@purge.command("url")
@click.argument("url")
@click.option("--exact", is_flag=True, help="Purge only the exact path when the URL ends with /")
@click.option("--background", is_flag=True, help="Return before the purge finishes")
def purge_url(url: str, exact: bool, background: bool) -> None:
    """Purge a specific URL from the CDN cache.

    URL: The full URL to purge (e.g., https://cdn.example.com/path/file.js)
    """
    with BunnyClient() as client:
        PurgeAPI(client).purge_url(url, background=background, exact=exact)
        print_success(f"Purged: {redact_url(url)}")


@purge.command("zone")
@click.argument("zone_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def purge_zone(zone_id: int, yes: bool) -> None:
    """Purge all cache for a pull zone.

    ZONE_ID: The pull zone ID to purge
    """
    if not yes:
        click.confirm(f"Are you sure you want to purge ALL cache for zone {zone_id}?", abort=True)
    with BunnyClient() as client:
        PullZoneAPI(client).purge_cache(zone_id)
        print_success(f"Purged all cache for pull zone {zone_id}")


@purge.command("tag")
@click.argument("zone_id", type=int)
@click.argument("tag")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def purge_tag(zone_id: int, tag: str, yes: bool) -> None:
    """Purge cached responses that carry a CDN-Tag value."""
    tag = require_tag(tag)
    if not yes:
        click.confirm(f"Purge cache tag {tag} on pull zone {zone_id}?", abort=True)
    with BunnyClient() as client:
        PullZoneAPI(client).purge_cache(zone_id, tag)
        print_success(f"Purged cache tag {tag} on pull zone {zone_id}")


@purge.command("all")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def purge_all(yes: bool) -> None:
    """Purge cache for ALL pull zones."""
    if not yes:
        click.confirm("Are you sure you want to purge cache for ALL pull zones?", abort=True)
    with BunnyClient() as client:
        api = PullZoneAPI(client)
        zones = api.list()
        for zone in zones:
            zone_id = zone.get("Id")
            if not isinstance(zone_id, int):
                continue
            api.purge_cache(zone_id)
            print_success(f"Purged: {zone.get('Name')} (ID: {zone_id})")
        print_success(f"Purged cache for {len(zones)} pull zones")
