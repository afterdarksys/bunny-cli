"""Storage Zone commands."""
from __future__ import annotations

from typing import Any

import click

from bunny_cli.client import BunnyClient, StorageZoneAPI
from bunny_cli.config import selected_zone
from bunny_cli.output import (
    console,
    format_bytes,
    mask_secret,
    print_dict,
    print_json,
    print_success,
    print_table,
    wants_json,
)

REGIONS = {
    "DE": "Germany (Falkenstein)",
    "NY": "New York",
    "LA": "Los Angeles",
    "SG": "Singapore",
    "SYD": "Sydney",
    "UK": "London",
    "SE": "Stockholm",
    "BR": "Sao Paulo",
    "JH": "Johannesburg",
}


def _bytes_field(zone: dict[str, Any], key: str) -> str:
    try:
        return format_bytes(float(zone.get(key) or 0))
    except (TypeError, ValueError):
        return format_bytes(0)


@click.group()
def storage() -> None:
    """Manage storage zones."""
    pass


@storage.command("list")
@click.option("--include-deleted", is_flag=True, help="Include deleted zones")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_zones(include_deleted: bool, as_json: bool) -> None:
    """List all storage zones."""
    with BunnyClient() as client:
        zones = StorageZoneAPI(client).list(include_deleted)
        if wants_json(as_json):
            print_json(zones)
            return
        for zone in zones:
            zone["StorageUsedFormatted"] = _bytes_field(zone, "StorageUsed")
            zone["RegionName"] = REGIONS.get(zone.get("Region", ""), zone.get("Region", ""))
        print_table(
            zones,
            columns=["Id", "Name", "RegionName", "StorageUsedFormatted", "FilesStored"],
            headers=["ID", "Name", "Region", "Storage Used", "Files"],
        )


@storage.command("get")
@click.argument("zone_id", type=int, required=False)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON, including passwords")
@click.option("--show-secrets", is_flag=True, help="Print the storage passwords")
def get_zone(zone_id: int | None, as_json: bool, show_secrets: bool) -> None:
    """Get details for a storage zone.

    ZONE_ID is optional when default_storage_zone is configured.
    Passwords are masked unless --show-secrets or --json is set.
    """
    zone_id = selected_zone(zone_id, "storage")
    with BunnyClient() as client:
        zone = StorageZoneAPI(client).get(zone_id)
        if wants_json(as_json):
            print_json(zone)
            return
        password = zone.get("Password")
        readonly = zone.get("ReadOnlyPassword")
        if not show_secrets:
            password = mask_secret(password)
            readonly = mask_secret(readonly)
        regions = zone.get("ReplicationRegions") or []
        if isinstance(regions, list) and regions:
            region_text = ", ".join(str(item) for item in regions)
        else:
            region_text = "None"
        display = {
            "ID": zone.get("Id"),
            "Name": zone.get("Name"),
            "Region": REGIONS.get(zone.get("Region", ""), zone.get("Region", "")),
            "Storage Used": _bytes_field(zone, "StorageUsed"),
            "Files Stored": zone.get("FilesStored"),
            "Date Created": zone.get("DateCreated"),
            "Date Modified": zone.get("DateModified"),
            "Password": password,
            "Read-Only Password": readonly,
            "Replication Regions": region_text,
        }
        print_dict(display, f"Storage Zone: {zone.get('Name')}")
        pull_zones = zone.get("PullZones") or []
        if pull_zones:
            console.print("\n[bold]Connected Pull Zones:[/bold]")
            print_table(pull_zones, columns=["Id", "Name"], headers=["ID", "Name"])


@storage.command("create")
@click.argument("name")
@click.option(
    "--region",
    type=click.Choice(list(REGIONS.keys())),
    default="DE",
    help="Primary region",
)
@click.option(
    "--replicate",
    multiple=True,
    type=click.Choice(list(REGIONS.keys())),
    help="Replication regions",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create_zone(name: str, region: str, replicate: tuple[str, ...], as_json: bool) -> None:
    """Create a new storage zone."""
    kwargs: dict[str, Any] = {}
    if replicate:
        kwargs["ReplicationRegions"] = list(replicate)
    with BunnyClient() as client:
        zone = StorageZoneAPI(client).create(name, region, **kwargs)
        if wants_json(as_json):
            print_json(zone)
            return
        print_success(f"Created storage zone: {zone.get('Name')} (ID: {zone.get('Id')})")
        console.print(f"Region: {REGIONS.get(region, region)}")
        console.print("FTP Hostname: storage.bunnycdn.com")
        console.print(f"Username: {zone.get('Name')}")
        console.print(f"Password: {zone.get('Password')}")
        console.print("[dim]Shown once. Later reads mask it unless you pass --show-secrets.[/dim]")


@storage.command("update")
@click.argument("zone_id", type=int)
@click.option("--name", help="New zone name")
@click.option("--custom-404", help="Custom 404 file path")
def update_zone(zone_id: int, name: str | None, custom_404: str | None) -> None:
    """Update a storage zone."""
    kwargs: dict[str, str] = {}
    if name:
        kwargs["Name"] = name
    if custom_404:
        if len(custom_404) > 1024 or any(ord(char) < 32 for char in custom_404):
            raise click.ClickException("Custom 404 path is invalid")
        kwargs["Custom404FilePath"] = custom_404
    if not kwargs:
        raise click.ClickException("No updates specified")
    with BunnyClient() as client:
        StorageZoneAPI(client).update(zone_id, **kwargs)
        print_success(f"Updated storage zone {zone_id}")


@storage.command("delete")
@click.argument("zone_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_zone(zone_id: int, yes: bool) -> None:
    """Delete a storage zone."""
    if not yes:
        click.confirm(
            f"Are you sure you want to delete storage zone {zone_id}? This will delete ALL files!",
            abort=True,
        )
    with BunnyClient() as client:
        StorageZoneAPI(client).delete(zone_id)
        print_success(f"Deleted storage zone {zone_id}")


@storage.command("regions")
def list_regions() -> None:
    """List available storage regions."""
    console.print("[bold]Available Storage Regions:[/bold]\n")
    for code, name in REGIONS.items():
        console.print(f"  {code:4} - {name}")
