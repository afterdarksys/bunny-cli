"""Cloudflare migration commands."""
from __future__ import annotations

import os
from typing import Any

import click
import httpx

from bunny_cli.client import BunnyAPIError, BunnyClient, DNSZoneAPI, PullZoneAPI, exchange
from bunny_cli.output import console, print_error, print_success, print_table
from bunny_cli.validate import require_cf_zone_id, require_http_url

_MAX_PAGES = 200


class CloudflareClient:
    """Cloudflare API client.

    Threats: the API token is sent only to api.cloudflare.com and is not
    written to disk by this command. Redirects are refused. The token can
    still appear in the process environment.
    """

    BASE_URL = "https://api.cloudflare.com/client/v4"

    def __init__(
        self,
        api_token: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        env_token = os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
        token = api_token or env_token
        if not token:
            raise click.ClickException("No Cloudflare API token. Set CF_API_TOKEN or --cf-token")
        self.api_token = token.strip()
        printable = all(33 <= ord(char) <= 126 for char in self.api_token)
        if not (20 <= len(self.api_token) <= 256) or not printable:
            raise click.ClickException("Cloudflare API token is invalid")
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Accept": "application/json",
                "User-Agent": "bunny-cli",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=False,
            transport=transport,
        )

    def _page(self, path: str, params: dict[str, Any] | None = None) -> tuple[Any, dict[str, Any]]:
        data = exchange(self._client, "GET", path, params=params)
        if not isinstance(data, dict) or not data.get("success"):
            raise click.ClickException("Cloudflare API error")
        info = data.get("result_info")
        return data.get("result"), info if isinstance(info, dict) else {}

    def _collect(self, path: str) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        while page <= _MAX_PAGES:
            result, info = self._page(path, {"page": page, "per_page": 100})
            if not isinstance(result, list):
                raise click.ClickException("Unexpected Cloudflare response")
            rows.extend(item for item in result if isinstance(item, dict))
            total_pages = info.get("total_pages") or 1
            try:
                total_pages_int = int(total_pages)
            except (TypeError, ValueError) as exc:
                raise click.ClickException("Unexpected Cloudflare response") from exc
            if page >= total_pages_int:
                return rows
            page += 1
        raise click.ClickException("Cloudflare pagination limit exceeded")

    def list_zones(self) -> list[dict[str, Any]]:
        """List zones, following pagination."""
        return self._collect("/zones")

    def get_zone(self, zone_id: str) -> dict[str, Any]:
        """Get one zone."""
        zone_id = require_cf_zone_id(zone_id)
        result, _info = self._page(f"/zones/{zone_id}")
        if not isinstance(result, dict):
            raise click.ClickException("Unexpected Cloudflare response")
        return result

    def list_dns_records(self, zone_id: str) -> list[dict[str, Any]]:
        """List every DNS record in a zone."""
        zone_id = require_cf_zone_id(zone_id)
        return self._collect(f"/zones/{zone_id}/dns_records")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CloudflareClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def plan_dns_migration(
    records: list[dict[str, Any]],
    domain: str,
    *,
    skip_proxied: bool,
    skip_ns: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Decide which Cloudflare records can be copied. Unknown types are skipped."""
    supported = {"A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA", "PTR"}
    to_migrate: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for record in records:
        rtype = str(record.get("type") or "")
        name = str(record.get("name") or "")
        content = str(record.get("content") or "")
        label = f"{rtype} {name}"
        if rtype not in supported:
            skipped.append({"record": label, "reason": "Unsupported type"})
            continue
        if skip_ns and rtype == "NS":
            skipped.append({"record": label, "reason": "NS record skipped"})
            continue
        if skip_proxied and record.get("proxied"):
            skipped.append({"record": label, "reason": "Proxied record"})
            continue
        if name == domain or name == f"{domain}.":
            relative = "@"
        elif name.endswith(f".{domain}"):
            relative = name[: -(len(domain) + 1)]
        elif name.endswith(f".{domain}."):
            relative = name[: -(len(domain) + 2)]
        else:
            relative = name
        ttl = record.get("ttl", 300)
        try:
            ttl_int = 300 if ttl in (None, 1) else int(ttl)
        except (TypeError, ValueError):
            skipped.append({"record": label, "reason": "Invalid TTL"})
            continue
        priority = record.get("priority")
        raw_data = record.get("data")
        data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
        if rtype in {"MX", "SRV"} and priority is None:
            priority = data.get("priority")
        if rtype in {"MX", "SRV"} and priority is None:
            skipped.append({"record": label, "reason": "Missing priority"})
            continue
        to_migrate.append(
            {
                "type": rtype,
                "name": relative or "@",
                "value": content,
                "ttl": ttl_int,
                "priority": priority,
                "weight": data.get("weight"),
                "port": data.get("port"),
                "proxied": bool(record.get("proxied")),
            }
        )
    return to_migrate, skipped


def _require_mode(play: bool, execute: bool) -> None:
    if play == execute:
        raise click.ClickException("Specify --play to preview or --exec to execute")


@click.group()
def cf() -> None:
    """Migrate from Cloudflare to Bunny.net.

    Requires CF_API_TOKEN or --cf-token.
    Get a token from: https://dash.cloudflare.com/profile/api-tokens
    """
    pass


@cf.command("zones")
@click.option("--cf-token", envvar="CF_API_TOKEN", help="Cloudflare API token")
def list_cf_zones(cf_token: str | None) -> None:
    """List your Cloudflare zones."""
    with CloudflareClient(cf_token) as cf_client:
        zones = []
        for zone in cf_client.list_zones():
            nameservers = zone.get("name_servers") or []
            if isinstance(nameservers, list):
                nameserver_text = ", ".join(str(item) for item in nameservers)
            else:
                nameserver_text = str(nameservers)
            zones.append(
                {
                    "id": zone.get("id"),
                    "name": zone.get("name"),
                    "status": zone.get("status"),
                    "name_servers": nameserver_text,
                }
            )
        print_table(
            zones,
            columns=["id", "name", "status", "name_servers"],
            headers=["Zone ID", "Domain", "Status", "Nameservers"],
        )


@cf.command("records")
@click.argument("zone_id")
@click.option("--cf-token", envvar="CF_API_TOKEN", help="Cloudflare API token")
def list_cf_records(zone_id: str, cf_token: str | None) -> None:
    """List DNS records in a Cloudflare zone."""
    with CloudflareClient(cf_token) as cf_client:
        formatted = []
        for record in cf_client.list_dns_records(zone_id):
            content = str(record.get("content") or "")
            formatted.append(
                {
                    "type": record.get("type"),
                    "name": record.get("name"),
                    "content": content[:50],
                    "ttl": record.get("ttl"),
                    "proxied": "Yes" if record.get("proxied") else "No",
                }
            )
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
@click.option("--skip-proxied", is_flag=True, help="Skip Cloudflare-proxied records")
@click.option("--skip-ns/--include-ns", default=True, help="Skip NS records (default: skip)")
def migrate_dns(
    cf_zone_id: str,
    bunny_zone_id: int,
    cf_token: str | None,
    play: bool,
    execute: bool,
    skip_proxied: bool,
    skip_ns: bool,
) -> None:
    """Migrate DNS records from Cloudflare to Bunny.

    \b
    Examples:
      bunny cf dns <cf-zone-id> <bunny-zone-id> --play
      bunny cf dns <cf-zone-id> <bunny-zone-id> --exec
      bunny cf dns <cf-zone-id> <bunny-zone-id> --include-ns --exec
    """
    _require_mode(play, execute)
    cf_zone_id = require_cf_zone_id(cf_zone_id)
    with CloudflareClient(cf_token) as cf_client:
        cf_zone = cf_client.get_zone(cf_zone_id)
        domain = str(cf_zone.get("name") or "")
        console.print(f"\n[bold]Migrating DNS: {domain}[/bold]")
        console.print(f"From Cloudflare zone: {cf_zone_id}")
        console.print(f"To Bunny zone: {bunny_zone_id}\n")
        to_migrate, skipped = plan_dns_migration(
            cf_client.list_dns_records(cf_zone_id),
            domain,
            skip_proxied=skip_proxied,
            skip_ns=skip_ns,
        )

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
            for item in skipped:
                console.print(f"  {item['record']} - {item['reason']}")
        if play:
            console.print("\n[dim]This is a dry run. Use --exec to actually migrate.[/dim]")
            return

        console.print("\n[bold]Executing migration...[/bold]\n")
        with BunnyClient() as bunny_client:
            dns_api = DNSZoneAPI(bunny_client)
            success = 0
            failed = 0
            for record in to_migrate:
                try:
                    kwargs = {}
                    if record["priority"] is not None:
                        kwargs["Priority"] = int(record["priority"])
                    if record["weight"] is not None:
                        kwargs["Weight"] = int(record["weight"])
                    if record["port"] is not None:
                        kwargs["Port"] = int(record["port"])
                    dns_api.add_record(
                        bunny_zone_id,
                        record["type"],
                        record["name"],
                        record["value"],
                        record["ttl"],
                        **kwargs,
                    )
                    print_success(f"{record['type']} {record['name']}")
                    success += 1
                except (click.ClickException, BunnyAPIError, ValueError, TypeError) as exc:
                    detail = exc.message if isinstance(exc, BunnyAPIError) else str(exc)
                    print_error(f"{record['type']} {record['name']}: {detail}")
                    failed += 1
            console.print("\n[bold]Migration complete[/bold]")
            console.print(f"[green]Success: {success}[/green]")
            if failed:
                console.print(f"[red]Failed: {failed}[/red]")
                raise click.ClickException(f"{failed} record(s) failed")


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
    cf_token: str | None,
    origin: str | None,
    play: bool,
    execute: bool,
) -> None:
    """Create a Bunny pull zone for a Cloudflare domain.

    \b
    Examples:
      bunny cf pullzone <cf-zone-id> my-cdn --play
      bunny cf pullzone <cf-zone-id> my-cdn --origin https://origin.example.com --exec
    """
    _require_mode(play, execute)
    cf_zone_id = require_cf_zone_id(cf_zone_id)
    with CloudflareClient(cf_token) as cf_client:
        cf_zone = cf_client.get_zone(cf_zone_id)
        domain = str(cf_zone.get("name") or "")
        origin_url = require_http_url(origin or f"https://{domain}", what="Origin URL")
        console.print(f"\n[bold]Create Pull Zone for: {domain}[/bold]")
        console.print(f"Pull Zone Name: {bunny_name}")
        console.print(f"Origin URL: {origin_url}")
        console.print(f"CDN URL: https://{bunny_name}.b-cdn.net\n")
        if play:
            console.print("[dim]This is a dry run. Use --exec to create the pull zone.[/dim]")
            console.print("\n[cyan]Next steps after creation:[/cyan]")
            console.print(f"1. bunny pullzone add-hostname <ID> cdn.{domain}")
            console.print(f"2. bunny pullzone ssl <ID> cdn.{domain}")
            console.print("3. Update DNS to point at the Bunny hostname")
            return

        with BunnyClient() as bunny_client:
            zone = PullZoneAPI(bunny_client).create(bunny_name, origin_url)
            zone_id = zone.get("Id")
            print_success(f"Created pull zone: {bunny_name} (ID: {zone_id})")
            console.print(f"CDN URL: https://{bunny_name}.b-cdn.net")
            console.print("\n[cyan]Next steps:[/cyan]")
            console.print(f"1. bunny pullzone add-hostname {zone_id} cdn.{domain}")
            console.print(f"2. bunny pullzone ssl {zone_id} cdn.{domain}")
            console.print(f"3. Update DNS: cdn.{domain} CNAME {bunny_name}.b-cdn.net")
