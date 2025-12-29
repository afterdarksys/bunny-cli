"""DNS Zone commands."""
from __future__ import annotations

from typing import Optional

import click

from bunny_cli.client import BunnyClient, DNSZoneAPI
from bunny_cli.output import console, print_dict, print_json, print_success, print_table


@click.group()
def dns() -> None:
    """Manage DNS zones and records."""
    pass


@dns.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_zones(as_json: bool) -> None:
    """List all DNS zones."""
    with BunnyClient() as client:
        api = DNSZoneAPI(client)
        zones = api.list()

        if as_json:
            print_json(zones)
        else:
            print_table(
                zones,
                columns=["Id", "Domain", "DateCreated", "RecordsCount"],
                headers=["ID", "Domain", "Created", "Records"],
            )


@dns.command("get")
@click.argument("zone_id", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def get_zone(zone_id: int, as_json: bool) -> None:
    """Get details for a DNS zone including all records."""
    with BunnyClient() as client:
        api = DNSZoneAPI(client)
        zone = api.get(zone_id)

        if as_json:
            print_json(zone)
        else:
            # Zone info
            display = {
                "ID": zone.get("Id"),
                "Domain": zone.get("Domain"),
                "Created": zone.get("DateCreated"),
                "Modified": zone.get("DateModified"),
                "Nameserver Custom": zone.get("NameserversDetected"),
            }
            print_dict(display, f"DNS Zone: {zone.get('Domain')}")

            # Records
            records = zone.get("Records", [])
            if records:
                console.print("\n[bold]Records:[/bold]")
                formatted_records = []
                for r in records:
                    formatted_records.append({
                        "Id": r.get("Id"),
                        "Type": api._int_to_record_type(r.get("Type", 0)),
                        "Name": r.get("Name") or "@",
                        "Value": r.get("Value"),
                        "TTL": r.get("Ttl"),
                        "Disabled": r.get("Disabled", False),
                    })
                print_table(
                    formatted_records,
                    columns=["Id", "Type", "Name", "Value", "TTL", "Disabled"],
                    headers=["ID", "Type", "Name", "Value", "TTL", "Disabled"],
                )


@dns.command("create")
@click.argument("domain")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create_zone(domain: str, as_json: bool) -> None:
    """Create a new DNS zone."""
    with BunnyClient() as client:
        api = DNSZoneAPI(client)
        zone = api.create(domain)

        if as_json:
            print_json(zone)
        else:
            print_success(f"Created DNS zone: {domain} (ID: {zone.get('Id')})")
            console.print("\nNameservers:")
            for ns in zone.get("Nameservers", []):
                console.print(f"  {ns}")


@dns.command("delete")
@click.argument("zone_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_zone(zone_id: int, yes: bool) -> None:
    """Delete a DNS zone."""
    if not yes:
        click.confirm(f"Are you sure you want to delete DNS zone {zone_id}?", abort=True)

    with BunnyClient() as client:
        api = DNSZoneAPI(client)
        api.delete(zone_id)
        print_success(f"Deleted DNS zone {zone_id}")


# Record management
@dns.group("record")
def record() -> None:
    """Manage DNS records."""
    pass


@record.command("add")
@click.argument("zone_id", type=int)
@click.argument("record_type", type=click.Choice(["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA", "PTR"]))
@click.argument("name")
@click.argument("value")
@click.option("--ttl", type=int, default=300, help="Time to live in seconds (default: 300)")
@click.option("--priority", type=int, help="Priority (for MX records)")
@click.option("--weight", type=int, help="Weight (for SRV records)")
@click.option("--port", type=int, help="Port (for SRV records)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def add_record(
    zone_id: int,
    record_type: str,
    name: str,
    value: str,
    ttl: int,
    priority: Optional[int],
    weight: Optional[int],
    port: Optional[int],
    as_json: bool,
) -> None:
    """Add a DNS record.

    NAME: Record name (use @ for root, or subdomain name)
    VALUE: Record value (IP address, hostname, text, etc.)
    """
    kwargs = {}
    if priority is not None:
        kwargs["Priority"] = priority
    if weight is not None:
        kwargs["Weight"] = weight
    if port is not None:
        kwargs["Port"] = port

    with BunnyClient() as client:
        api = DNSZoneAPI(client)
        result = api.add_record(zone_id, record_type, name, value, ttl, **kwargs)

        if as_json:
            print_json(result)
        else:
            print_success(f"Added {record_type} record: {name} -> {value}")


@record.command("update")
@click.argument("zone_id", type=int)
@click.argument("record_id", type=int)
@click.option("--value", help="New record value")
@click.option("--ttl", type=int, help="New TTL")
@click.option("--disabled/--enabled", default=None, help="Disable or enable the record")
def update_record(
    zone_id: int,
    record_id: int,
    value: Optional[str],
    ttl: Optional[int],
    disabled: Optional[bool],
) -> None:
    """Update a DNS record."""
    kwargs = {}
    if value:
        kwargs["Value"] = value
    if ttl is not None:
        kwargs["Ttl"] = ttl
    if disabled is not None:
        kwargs["Disabled"] = disabled

    if not kwargs:
        raise click.ClickException("No updates specified")

    with BunnyClient() as client:
        api = DNSZoneAPI(client)
        api.update_record(zone_id, record_id, **kwargs)
        print_success(f"Updated record {record_id}")


@record.command("delete")
@click.argument("zone_id", type=int)
@click.argument("record_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_record(zone_id: int, record_id: int, yes: bool) -> None:
    """Delete a DNS record."""
    if not yes:
        click.confirm(f"Are you sure you want to delete record {record_id}?", abort=True)

    with BunnyClient() as client:
        api = DNSZoneAPI(client)
        api.delete_record(zone_id, record_id)
        print_success(f"Deleted record {record_id}")
