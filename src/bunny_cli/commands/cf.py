"""Cloudflare migration commands."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import click
import httpx

from bunny_cli.client import BunnyClient, DNSZoneAPI, PullZoneAPI
from bunny_cli.output import console, print_error, print_info, print_success, print_table, print_warning


class CloudflareClient:
    """Cloudflare API client."""

    BASE_URL = "https://api.cloudflare.com/client/v4"

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
        if not self.api_token:
            raise click.ClickException(
                "No Cloudflare API token. Set CF_API_TOKEN or use --cf-token"
            )
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET request."""
        response = self._client.get(path, params=params)
        data = response.json()
        if not data.get("success", False):
            errors = data.get("errors", [])
            msg = errors[0].get("message") if errors else "Unknown error"
            raise click.ClickException(f"Cloudflare API error: {msg}")
        return data.get("result", data)

    def list_zones(self) -> List[Dict[str, Any]]:
        """List all zones."""
        return self.get("/zones")

    def get_zone(self, zone_id: str) -> Dict[str, Any]:
        """Get zone details."""
        return self.get(f"/zones/{zone_id}")

    def list_dns_records(self, zone_id: str) -> List[Dict[str, Any]]:
        """List DNS records for a zone."""
        return self.get(f"/zones/{zone_id}/dns_records", params={"per_page": 1000})

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CloudflareClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# Record type mapping from CF to Bunny
CF_TO_BUNNY_TYPE = {
    "A": "A",
    "AAAA": "AAAA",
    "CNAME": "CNAME",
    "TXT": "TXT",
    "MX": "MX",
    "NS": "NS",
    "SRV": "SRV",
    "CAA": "CAA",
    "PTR": "PTR",
}


@click.group()
def cf() -> None:
    """Migrate from Cloudflare to Bunny.net.

    Requires CF_API_TOKEN environment variable or --cf-token option.
    Get your token from: https://dash.cloudflare.com/profile/api-tokens
    """
    pass


@cf.command("zones")
@click.option("--cf-token", envvar="CF_API_TOKEN", help="Cloudflare API token")
def list_cf_zones(cf_token: Optional[str]) -> None:
    """List your Cloudflare zones."""
    with CloudflareClient(cf_token) as cf_client:
        zones = cf_client.list_zones()
        print_table(
            zones,
            columns=["id", "name", "status", "name_servers"],
            headers=["Zone ID", "Domain", "Status", "Nameservers"],
        )


@cf.command("records")
@click.argument("zone_id")
@click.option("--cf-token", envvar="CF_API_TOKEN", help="Cloudflare API token")
def list_cf_records(zone_id: str, cf_token: Optional[str]) -> None:
    """List DNS records in a Cloudflare zone."""
    with CloudflareClient(cf_token) as cf_client:
        records = cf_client.list_dns_records(zone_id)
        formatted = []
        for r in records:
            formatted.append({
                "type": r.get("type"),
                "name": r.get("name"),
                "content": r.get("content", "")[:50],
                "ttl": r.get("ttl"),
                "proxied": "Yes" if r.get("proxied") else "No",
            })
        print_table(
            formatted,
            columns=["type", "name", "content", "ttl", "proxied"],
            headers=["Type", "Name", "Value", "TTL", "Proxied"],
        )


@cf.command("dns")
@click.argument("cf_zone_id")
@click.argument("bunny_zone_id", type=int)
@click.option("--cf-token", envvar="CF_API_TOKEN", help="Cloudflare API token")
@click.option("--play", is_flag=True, help="Dry run - show what would be migrated")
@click.option("--exec", "execute", is_flag=True, help="Actually execute the migration")
@click.option("--skip-proxied", is_flag=True, help="Skip records that are proxied through CF")
@click.option("--skip-ns", is_flag=True, default=True, help="Skip NS records (default: true)")
def migrate_dns(
    cf_zone_id: str,
    bunny_zone_id: int,
    cf_token: Optional[str],
    play: bool,
    execute: bool,
    skip_proxied: bool,
    skip_ns: bool,
) -> None:
    """Migrate DNS records from Cloudflare to Bunny.

    CF_ZONE_ID: Cloudflare zone ID (from 'bunny cf zones')
    BUNNY_ZONE_ID: Bunny DNS zone ID (from 'bunny dns list')

    \b
    Examples:
      bunny cf dns abc123 456 --play      # Preview migration
      bunny cf dns abc123 456 --exec      # Execute migration
    """
    if not play and not execute:
        raise click.ClickException("Specify --play to preview or --exec to execute")

    if play and execute:
        raise click.ClickException("Cannot use both --play and --exec")

    with CloudflareClient(cf_token) as cf_client:
        # Get CF zone info
        cf_zone = cf_client.get_zone(cf_zone_id)
        domain = cf_zone.get("name")
        console.print(f"\n[bold]Migrating DNS: {domain}[/bold]")
        console.print(f"From Cloudflare zone: {cf_zone_id}")
        console.print(f"To Bunny zone: {bunny_zone_id}\n")

        # Get CF records
        cf_records = cf_client.list_dns_records(cf_zone_id)

        # Filter and prepare records
        to_migrate = []
        skipped = []

        for record in cf_records:
            rtype = record.get("type")
            name = record.get("name", "")
            content = record.get("content", "")
            ttl = record.get("ttl", 300)
            proxied = record.get("proxied", False)
            priority = record.get("priority")

            # Convert name to relative (remove domain suffix)
            if name == domain:
                rel_name = ""  # Root
            elif name.endswith(f".{domain}"):
                rel_name = name[: -(len(domain) + 1)]
            else:
                rel_name = name

            # Skip unsupported types
            if rtype not in CF_TO_BUNNY_TYPE:
                skipped.append({"record": f"{rtype} {name}", "reason": "Unsupported type"})
                continue

            # Skip NS records if requested
            if skip_ns and rtype == "NS":
                skipped.append({"record": f"{rtype} {name}", "reason": "NS record skipped"})
                continue

            # Skip proxied records if requested
            if skip_proxied and proxied:
                skipped.append({"record": f"{rtype} {name}", "reason": "Proxied record"})
                continue

            # Handle TTL (CF uses 1 for "auto")
            if ttl == 1:
                ttl = 300

            to_migrate.append({
                "type": rtype,
                "name": rel_name or "@",
                "value": content,
                "ttl": ttl,
                "priority": priority,
                "proxied": proxied,
                "original": f"{rtype} {name} -> {content}",
            })

        # Show what will be migrated
        console.print(f"[cyan]Records to migrate: {len(to_migrate)}[/cyan]")
        if skipped:
            console.print(f"[yellow]Records skipped: {len(skipped)}[/yellow]")

        print_table(
            to_migrate,
            columns=["type", "name", "value", "ttl"],
            headers=["Type", "Name", "Value", "TTL"],
        )

        if skipped:
            console.print("\n[yellow]Skipped records:[/yellow]")
            for s in skipped:
                console.print(f"  {s['record']} - {s['reason']}")

        if play:
            console.print("\n[dim]This is a dry run. Use --exec to actually migrate.[/dim]")
            return

        # Execute migration
        if execute:
            console.print("\n[bold]Executing migration...[/bold]\n")

            with BunnyClient() as bunny_client:
                dns_api = DNSZoneAPI(bunny_client)
                success = 0
                failed = 0

                for record in to_migrate:
                    try:
                        kwargs = {}
                        if record["priority"] is not None:
                            kwargs["Priority"] = record["priority"]

                        dns_api.add_record(
                            bunny_zone_id,
                            record["type"],
                            record["name"],
                            record["value"],
                            record["ttl"],
                            **kwargs,
                        )
                        print_success(f"{record['type']} {record['name']} -> {record['value'][:40]}")
                        success += 1
                    except Exception as e:
                        print_error(f"{record['type']} {record['name']}: {e}")
                        failed += 1

                console.print(f"\n[bold]Migration complete![/bold]")
                console.print(f"[green]Success: {success}[/green]")
                if failed:
                    console.print(f"[red]Failed: {failed}[/red]")


@cf.command("pullzone")
@click.argument("cf_zone_id")
@click.argument("bunny_name")
@click.option("--cf-token", envvar="CF_API_TOKEN", help="Cloudflare API token")
@click.option("--origin", help="Origin URL (default: https://domain)")
@click.option("--play", is_flag=True, help="Dry run - show what would be created")
@click.option("--exec", "execute", is_flag=True, help="Actually execute the migration")
def migrate_pullzone(
    cf_zone_id: str,
    bunny_name: str,
    cf_token: Optional[str],
    origin: Optional[str],
    play: bool,
    execute: bool,
) -> None:
    """Create a Bunny pull zone for a Cloudflare domain.

    This creates a pull zone that can replace Cloudflare's CDN proxy.

    \b
    CF_ZONE_ID: Cloudflare zone ID
    BUNNY_NAME: Name for the new Bunny pull zone

    \b
    Examples:
      bunny cf pullzone abc123 my-cdn --play
      bunny cf pullzone abc123 my-cdn --origin https://origin.example.com --exec
    """
    if not play and not execute:
        raise click.ClickException("Specify --play to preview or --exec to execute")

    with CloudflareClient(cf_token) as cf_client:
        cf_zone = cf_client.get_zone(cf_zone_id)
        domain = cf_zone.get("name")
        origin_url = origin or f"https://{domain}"

        console.print(f"\n[bold]Create Pull Zone for: {domain}[/bold]")
        console.print(f"Pull Zone Name: {bunny_name}")
        console.print(f"Origin URL: {origin_url}")
        console.print(f"CDN URL: https://{bunny_name}.b-cdn.net\n")

        if play:
            console.print("[dim]This is a dry run. Use --exec to create the pull zone.[/dim]")

            console.print("\n[cyan]Next steps after creation:[/cyan]")
            console.print(f"1. Add custom hostname: bunny pullzone add-hostname <ID> cdn.{domain}")
            console.print(f"2. Request SSL: bunny pullzone ssl <ID> cdn.{domain}")
            console.print(f"3. Update DNS to point to Bunny instead of Cloudflare proxy")
            return

        if execute:
            with BunnyClient() as bunny_client:
                pz_api = PullZoneAPI(bunny_client)

                zone = pz_api.create(bunny_name, origin_url)
                zone_id = zone.get("Id")

                print_success(f"Created pull zone: {bunny_name} (ID: {zone_id})")
                console.print(f"CDN URL: https://{bunny_name}.b-cdn.net")

                console.print("\n[cyan]Next steps:[/cyan]")
                console.print(f"1. bunny pullzone add-hostname {zone_id} cdn.{domain}")
                console.print(f"2. bunny pullzone ssl {zone_id} cdn.{domain}")
                console.print(f"3. Update DNS: cdn.{domain} CNAME {bunny_name}.b-cdn.net")
