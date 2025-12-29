"""Storage Zone commands."""
from __future__ import annotations

from typing import Optional

import click

from bunny_cli.client import BunnyClient, StorageZoneAPI
from bunny_cli.output import console, print_dict, print_json, print_success, print_table


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
        api = StorageZoneAPI(client)
        zones = api.list(include_deleted)

        if as_json:
            print_json(zones)
        else:
            for z in zones:
                z["StorageUsedFormatted"] = f"{z.get('StorageUsed', 0) / 1024 / 1024:.2f} MB"
                z["RegionName"] = REGIONS.get(z.get("Region", ""), z.get("Region", ""))
            print_table(
                zones,
                columns=["Id", "Name", "RegionName", "StorageUsedFormatted", "FilesStored"],
                headers=["ID", "Name", "Region", "Storage Used", "Files"],
            )


@storage.command("get")
@click.argument("zone_id", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def get_zone(zone_id: int, as_json: bool) -> None:
    """Get details for a storage zone."""
    with BunnyClient() as client:
        api = StorageZoneAPI(client)
        zone = api.get(zone_id)

        if as_json:
            print_json(zone)
        else:
            display = {
                "ID": zone.get("Id"),
                "Name": zone.get("Name"),
                "Region": REGIONS.get(zone.get("Region", ""), zone.get("Region", "")),
                "Storage Used": f"{zone.get('StorageUsed', 0) / 1024 / 1024:.2f} MB",
                "Files Stored": zone.get("FilesStored"),
                "Date Created": zone.get("DateModified"),
                "Read-Only Password": zone.get("ReadOnlyPassword"),
                "Password": zone.get("Password"),
                "Replication Regions": ", ".join(zone.get("ReplicationRegions", [])) or "None",
            }
            print_dict(display, f"Storage Zone: {zone.get('Name')}")

            # Show connected pull zones
            pull_zones = zone.get("PullZones", [])
            if pull_zones:
                console.print("\n[bold]Connected Pull Zones:[/bold]")
                print_table(
                    pull_zones,
                    columns=["Id", "Name"],
                    headers=["ID", "Name"],
                )


@storage.command("create")
@click.argument("name")
@click.option(
    "--region",
    type=click.Choice(list(REGIONS.keys())),
    default="DE",
    help="Primary region (default: DE)",
)
@click.option("--replicate", multiple=True, type=click.Choice(list(REGIONS.keys())), help="Replication regions")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create_zone(name: str, region: str, replicate: tuple[str, ...], as_json: bool) -> None:
    """Create a new storage zone."""
    kwargs = {}
    if replicate:
        kwargs["ReplicationRegions"] = list(replicate)

    with BunnyClient() as client:
        api = StorageZoneAPI(client)
        zone = api.create(name, region, **kwargs)

        if as_json:
            print_json(zone)
        else:
            print_success(f"Created storage zone: {zone.get('Name')} (ID: {zone.get('Id')})")
            console.print(f"Region: {REGIONS.get(region, region)}")
            console.print(f"FTP Hostname: storage.bunnycdn.com")
            console.print(f"Username: {zone.get('Name')}")
            console.print(f"Password: {zone.get('Password')}")


@storage.command("update")
@click.argument("zone_id", type=int)
@click.option("--name", help="New zone name")
@click.option("--custom-404", help="Custom 404 file path")
def update_zone(zone_id: int, name: Optional[str], custom_404: Optional[str]) -> None:
    """Update a storage zone."""
    kwargs = {}
    if name:
        kwargs["Name"] = name
    if custom_404:
        kwargs["Custom404FilePath"] = custom_404

    if not kwargs:
        raise click.ClickException("No updates specified")

    with BunnyClient() as client:
        api = StorageZoneAPI(client)
        api.update(zone_id, **kwargs)
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
        api = StorageZoneAPI(client)
        api.delete(zone_id)
        print_success(f"Deleted storage zone {zone_id}")


@storage.command("regions")
def list_regions() -> None:
    """List available storage regions."""
    console.print("[bold]Available Storage Regions:[/bold]\n")
    for code, name in REGIONS.items():
        console.print(f"  {code:4} - {name}")
