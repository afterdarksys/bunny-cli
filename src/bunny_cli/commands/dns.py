"""DNS Zone commands."""
from __future__ import annotations

import json
from typing import Any

import click

from bunny_cli.client import BunnyAPIError, BunnyClient, DNSZoneAPI
from bunny_cli.config import selected_zone
from bunny_cli.dnsutil import export_document, int_to_type, parse_import_document
from bunny_cli.output import console, print_dict, print_json, print_success, print_table, wants_json
from bunny_cli.validate import require_date


@click.group()
def dns() -> None:
    """Manage DNS zones and records."""
    pass


@dns.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_zones(as_json: bool) -> None:
    """List all DNS zones."""
    with BunnyClient() as client:
        zones = DNSZoneAPI(client).list()
        if wants_json(as_json):
            print_json(zones)
            return
        print_table(
            zones,
            columns=["Id", "Domain", "DateCreated", "RecordsCount"],
            headers=["ID", "Domain", "Created", "Records"],
        )


@dns.command("get")
@click.argument("zone_id", type=int, required=False)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def get_zone(zone_id: int | None, as_json: bool) -> None:
    """Get details for a DNS zone including all records.

    ZONE_ID is optional when default_dns_zone is configured.
    """
    zone_id = selected_zone(zone_id, "dns")
    with BunnyClient() as client:
        api = DNSZoneAPI(client)
        zone = api.get(zone_id)
        if wants_json(as_json):
            print_json(zone)
            return
        display = {
            "ID": zone.get("Id"),
            "Domain": zone.get("Domain"),
            "Created": zone.get("DateCreated"),
            "Modified": zone.get("DateModified"),
            "Custom Nameservers Detected": zone.get("CustomNameserversEnabled"),
            "Nameservers Detected": zone.get("NameserversDetected"),
        }
        print_dict(display, f"DNS Zone: {zone.get('Domain')}")
        records = zone.get("Records") or []
        if records:
            console.print("\n[bold]Records:[/bold]")
            formatted = []
            for record in records:
                if not isinstance(record, dict):
                    continue
                formatted.append(
                    {
                        "Id": record.get("Id"),
                        "Type": int_to_type(int(record.get("Type") or 0)),
                        "Name": record.get("Name") or "@",
                        "Value": record.get("Value"),
                        "TTL": record.get("Ttl"),
                        "Disabled": record.get("Disabled", False),
                    }
                )
            print_table(
                formatted,
                columns=["Id", "Type", "Name", "Value", "TTL", "Disabled"],
                headers=["ID", "Type", "Name", "Value", "TTL", "Disabled"],
            )


@dns.command("create")
@click.argument("domain")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create_zone(domain: str, as_json: bool) -> None:
    """Create a new DNS zone."""
    with BunnyClient() as client:
        zone = DNSZoneAPI(client).create(domain)
        if wants_json(as_json):
            print_json(zone)
            return
        print_success(f"Created DNS zone: {domain} (ID: {zone.get('Id')})")
        console.print("\nNameservers:")
        for nameserver in zone.get("Nameservers") or []:
            console.print(f"  {nameserver}")


@dns.command("delete")
@click.argument("zone_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_zone(zone_id: int, yes: bool) -> None:
    """Delete a DNS zone."""
    if not yes:
        click.confirm(f"Are you sure you want to delete DNS zone {zone_id}?", abort=True)
    with BunnyClient() as client:
        DNSZoneAPI(client).delete(zone_id)
        print_success(f"Deleted DNS zone {zone_id}")


@dns.command("export")
@click.argument("zone_id", type=int, required=False)
@click.option("--output", "-o", type=click.File("w", encoding="utf-8"), default="-")
def export_zone(zone_id: int | None, output: Any) -> None:
    """Export a DNS zone as JSON.

    ZONE_ID is optional when default_dns_zone is configured.
    """
    zone_id = selected_zone(zone_id, "dns")
    with BunnyClient() as client:
        document = export_document(DNSZoneAPI(client).get(zone_id))
    json.dump(document, output, indent=2)
    output.write("\n")
    destination = getattr(output, "name", "-")
    if destination not in {"-", "<stdout>"}:
        click.echo(f"Exported {len(document['records'])} records to {destination}", err=True)


@dns.command("import")
@click.argument("zone_id", type=int)
@click.argument("file", type=click.File("r", encoding="utf-8"))
@click.option("--play", is_flag=True, help="Show records without creating them")
@click.option("--exec", "execute", is_flag=True, help="Create the records")
def import_zone(zone_id: int, file: Any, play: bool, execute: bool) -> None:
    """Import DNS records from a JSON export.

    Existing records are not deleted. Review with --play before --exec.
    """
    if play == execute:
        raise click.ClickException("Specify --play to preview or --exec to import")
    raw = file.read(2_000_001)
    if len(raw) > 2_000_000:
        raise click.ClickException("Import file is too large")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.ClickException("Import file is not valid JSON") from exc
    payloads = parse_import_document(data)
    console.print(f"[cyan]Records to import: {len(payloads)}[/cyan]")
    preview = []
    for payload in payloads:
        preview.append(
            {
                "type": int_to_type(payload["Type"]),
                "name": payload["Name"] or "@",
                "value": payload["Value"],
                "ttl": payload["Ttl"],
            }
        )
    print_table(
        preview,
        columns=["type", "name", "value", "ttl"],
        headers=["Type", "Name", "Value", "TTL"],
    )
    if play:
        console.print("[dim]This is a dry run. Use --exec to import.[/dim]")
        return
    with BunnyClient() as client:
        api = DNSZoneAPI(client)
        failed = 0
        for payload in payloads:
            try:
                api.client.put(f"/dnszone/{zone_id}/records", json=payload)
                print_success(f"{int_to_type(payload['Type'])} {payload['Name'] or '@'}")
            except BunnyAPIError as exc:
                failed += 1
                console.print(f"[red]✗[/red] {payload['Name'] or '@'}: {exc.message}")
        if failed:
            raise click.ClickException(f"Imported with {failed} failure(s)")
    print_success(f"Imported {len(payloads)} records into zone {zone_id}")


@dns.command("stats")
@click.argument("zone_id", type=int, required=False)
@click.option("--from", "date_from", help="Start date (YYYY-MM-DD)")
@click.option("--to", "date_to", help="End date (YYYY-MM-DD)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def zone_stats(
    zone_id: int | None,
    date_from: str | None,
    date_to: str | None,
    as_json: bool,
) -> None:
    """Show DNS query statistics for a zone."""
    zone_id = selected_zone(zone_id, "dns")
    if date_from:
        date_from = require_date(date_from, flag="--from")
    if date_to:
        date_to = require_date(date_to, flag="--to")
    with BunnyClient() as client:
        data = DNSZoneAPI(client).statistics(zone_id, date_from, date_to)
    if wants_json(as_json):
        print_json(data)
        return
    print_dict(
        {
            "Zone ID": zone_id,
            "Total Queries": f"{int(data.get('TotalQueriesServed') or 0):,}",
        },
        "DNS Statistics",
    )


@dns.group("record")
def record() -> None:
    """Manage DNS records."""
    pass


@record.command("add")
@click.argument("zone_id", type=int)
@click.argument(
    "record_type",
    type=click.Choice(
        ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA", "PTR"],
        case_sensitive=False,
    ),
)
@click.argument("name")
@click.argument("value")
@click.option("--ttl", type=int, default=300, help="Time to live in seconds (default: 300)")
@click.option("--priority", type=int, help="Priority (required for MX and SRV)")
@click.option("--weight", type=int, help="Weight (for SRV records)")
@click.option("--port", type=int, help="Port (for SRV records)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def add_record(
    zone_id: int,
    record_type: str,
    name: str,
    value: str,
    ttl: int,
    priority: int | None,
    weight: int | None,
    port: int | None,
    as_json: bool,
) -> None:
    """Add a DNS record.

    NAME: Record name (use @ for the zone apex)
    VALUE: Record value (IP address, hostname, or text)
    """
    kwargs = {}
    if priority is not None:
        kwargs["Priority"] = priority
    if weight is not None:
        kwargs["Weight"] = weight
    if port is not None:
        kwargs["Port"] = port
    with BunnyClient() as client:
        result = DNSZoneAPI(client).add_record(zone_id, record_type, name, value, ttl, **kwargs)
        if wants_json(as_json):
            print_json(result)
            return
        print_success(f"Added {record_type.upper()} record: {name} -> {value}")


@record.command("update")
@click.argument("zone_id", type=int)
@click.argument("record_id", type=int)
@click.option("--value", help="New record value")
@click.option("--ttl", type=int, help="New TTL")
@click.option("--disabled/--enabled", default=None, help="Disable or enable the record")
def update_record(
    zone_id: int,
    record_id: int,
    value: str | None,
    ttl: int | None,
    disabled: bool | None,
) -> None:
    """Update a DNS record."""
    kwargs: dict[str, Any] = {}
    if value:
        kwargs["Value"] = value
    if ttl is not None:
        kwargs["Ttl"] = ttl
    if disabled is not None:
        kwargs["Disabled"] = disabled
    if not kwargs:
        raise click.ClickException("No updates specified")
    with BunnyClient() as client:
        DNSZoneAPI(client).update_record(zone_id, record_id, **kwargs)
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
        DNSZoneAPI(client).delete_record(zone_id, record_id)
        print_success(f"Deleted record {record_id}")
