"""Statistics commands."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import click

from bunny_cli.client import BunnyClient, StatisticsAPI
from bunny_cli.output import console, print_dict, print_json


@click.group()
def stats() -> None:
    """View CDN statistics."""
    pass


@stats.command("overview")
@click.option("--from", "date_from", help="Start date (YYYY-MM-DD)")
@click.option("--to", "date_to", help="End date (YYYY-MM-DD)")
@click.option("--zone", "pull_zone", type=int, help="Filter by pull zone ID")
@click.option("--hourly", is_flag=True, help="Show hourly breakdown")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def overview(
    date_from: Optional[str],
    date_to: Optional[str],
    pull_zone: Optional[int],
    hourly: bool,
    as_json: bool,
) -> None:
    """View CDN statistics overview."""
    # Default to last 30 days if not specified
    if not date_from:
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not date_to:
        date_to = datetime.now().strftime("%Y-%m-%d")

    with BunnyClient() as client:
        api = StatisticsAPI(client)
        data = api.get(date_from, date_to, pull_zone, hourly=hourly)

        if as_json:
            print_json(data)
        else:
            # Format and display
            total_bandwidth = data.get("TotalBandwidthUsed", 0)
            total_requests = data.get("TotalRequestsServed", 0)
            cache_hit_rate = data.get("CacheHitRate", 0)

            display = {
                "Period": f"{date_from} to {date_to}",
                "Total Bandwidth": _format_bytes(total_bandwidth),
                "Total Requests": f"{total_requests:,}",
                "Cache Hit Rate": f"{cache_hit_rate:.1f}%",
                "Bandwidth Cached": _format_bytes(data.get("BandwidthCachedChart", {}).get("Total", 0)),
                "Requests Served": f"{data.get('RequestsServedChart', {}).get('Total', 0):,}",
            }

            if pull_zone:
                display["Pull Zone ID"] = pull_zone

            print_dict(display, "CDN Statistics")

            # Show geographic breakdown if available
            geo = data.get("GeoTrafficDistribution", {})
            if geo and not as_json:
                console.print("\n[bold]Traffic by Region:[/bold]")
                sorted_geo = sorted(geo.items(), key=lambda x: x[1], reverse=True)[:10]
                for country, traffic in sorted_geo:
                    pct = (traffic / total_bandwidth * 100) if total_bandwidth > 0 else 0
                    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                    console.print(f"  {country:3} {bar} {pct:.1f}%")


@stats.command("bandwidth")
@click.option("--from", "date_from", help="Start date (YYYY-MM-DD)")
@click.option("--to", "date_to", help="End date (YYYY-MM-DD)")
@click.option("--zone", "pull_zone", type=int, help="Filter by pull zone ID")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def bandwidth(
    date_from: Optional[str],
    date_to: Optional[str],
    pull_zone: Optional[int],
    as_json: bool,
) -> None:
    """View bandwidth usage."""
    if not date_from:
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not date_to:
        date_to = datetime.now().strftime("%Y-%m-%d")

    with BunnyClient() as client:
        api = StatisticsAPI(client)
        data = api.get(date_from, date_to, pull_zone)

        if as_json:
            print_json(data.get("BandwidthUsedChart", {}))
        else:
            chart = data.get("BandwidthUsedChart", {})
            total = data.get("TotalBandwidthUsed", 0)

            console.print(f"[bold]Bandwidth Usage ({date_from} to {date_to})[/bold]\n")
            console.print(f"Total: {_format_bytes(total)}\n")

            # Show daily breakdown
            if chart:
                sorted_days = sorted(chart.items())[-14:]  # Last 14 days
                max_val = max(v for _, v in sorted_days) if sorted_days else 1

                for day, val in sorted_days:
                    bar_len = int((val / max_val) * 30) if max_val > 0 else 0
                    bar = "█" * bar_len
                    console.print(f"  {day[:10]} {bar} {_format_bytes(val)}")


def _format_bytes(bytes_val: float) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if abs(bytes_val) < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} EB"
