"""Statistics commands."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import click

from bunny_cli.client import BunnyClient, StatisticsAPI
from bunny_cli.output import (
    console,
    format_bytes,
    print_dict,
    print_json,
    sum_numeric_chart,
    wants_json,
)
from bunny_cli.validate import require_date


@click.group()
def stats() -> None:
    """View CDN statistics."""
    pass


def _window(date_from: str | None, date_to: str | None) -> tuple[str, str]:
    if date_from:
        date_from = require_date(date_from, flag="--from")
    else:
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if date_to:
        date_to = require_date(date_to, flag="--to")
    else:
        date_to = datetime.now().strftime("%Y-%m-%d")
    if date_from > date_to:
        raise click.ClickException("--from must be on or before --to")
    return date_from, date_to


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


@stats.command("overview")
@click.option("--from", "date_from", help="Start date (YYYY-MM-DD)")
@click.option("--to", "date_to", help="End date (YYYY-MM-DD)")
@click.option("--zone", "pull_zone", type=int, help="Filter by pull zone ID")
@click.option("--hourly", is_flag=True, help="Request an hourly breakdown")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def overview(
    date_from: str | None,
    date_to: str | None,
    pull_zone: int | None,
    hourly: bool,
    as_json: bool,
) -> None:
    """View CDN statistics overview."""
    date_from, date_to = _window(date_from, date_to)
    with BunnyClient() as client:
        data = StatisticsAPI(client).get(date_from, date_to, pull_zone, hourly=hourly)
    if wants_json(as_json):
        print_json(data)
        return

    total_bandwidth = _number(data.get("TotalBandwidthUsed"))
    total_requests = _number(data.get("TotalRequestsServed"))
    cache_hit_rate = _number(data.get("CacheHitRate"))
    display: dict[str, Any] = {
        "Period": f"{date_from} to {date_to}",
        "Total Bandwidth": format_bytes(total_bandwidth),
        "Cached Bandwidth": format_bytes(sum_numeric_chart(data.get("BandwidthCachedChart"))),
        "Total Requests": f"{int(total_requests):,}",
        "Cache Hit Rate": f"{cache_hit_rate:.1f}%",
        "Origin Traffic": format_bytes(_number(data.get("TotalOriginTraffic"))),
        "4xx Responses": f"{int(sum_numeric_chart(data.get('Error4xxChart'))):,}",
        "5xx Responses": f"{int(sum_numeric_chart(data.get('Error5xxChart'))):,}",
    }
    if pull_zone is not None:
        display["Pull Zone ID"] = pull_zone
    print_dict(display, "CDN Statistics")

    geo = data.get("GeoTrafficDistribution")
    if isinstance(geo, dict) and geo:
        console.print("\n[bold]Traffic by Region:[/bold]")
        pairs: list[tuple[str, float]] = []
        for country, traffic in geo.items():
            if isinstance(traffic, (int, float)) and not isinstance(traffic, bool):
                pairs.append((str(country), float(traffic)))
        pairs.sort(key=lambda item: item[1], reverse=True)
        for country, traffic in pairs[:10]:
            pct = (traffic / total_bandwidth * 100) if total_bandwidth > 0 else 0
            filled = max(0, min(20, int(pct / 5)))
            bar = "█" * filled + "░" * (20 - filled)
            console.print(f"  {country:3} {bar} {pct:.1f}%")


@stats.command("bandwidth")
@click.option("--from", "date_from", help="Start date (YYYY-MM-DD)")
@click.option("--to", "date_to", help="End date (YYYY-MM-DD)")
@click.option("--zone", "pull_zone", type=int, help="Filter by pull zone ID")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def bandwidth(
    date_from: str | None,
    date_to: str | None,
    pull_zone: int | None,
    as_json: bool,
) -> None:
    """View bandwidth usage."""
    date_from, date_to = _window(date_from, date_to)
    with BunnyClient() as client:
        data = StatisticsAPI(client).get(date_from, date_to, pull_zone)
    chart = data.get("BandwidthUsedChart")
    if wants_json(as_json):
        print_json(chart if isinstance(chart, dict) else {})
        return

    total = _number(data.get("TotalBandwidthUsed"))
    console.print(f"[bold]Bandwidth Usage ({date_from} to {date_to})[/bold]\n")
    console.print(f"Total: {format_bytes(total)}\n")
    if not isinstance(chart, dict):
        return
    points = [
        (str(day), float(val))
        for day, val in chart.items()
        if isinstance(val, (int, float)) and not isinstance(val, bool)
    ]
    points.sort()
    shown = points[-14:]
    max_val = max((val for _, val in shown), default=0)
    for day, val in shown:
        bar_len = int((val / max_val) * 30) if max_val > 0 else 0
        console.print(f"  {day[:10]} {'█' * max(0, bar_len)} {format_bytes(val)}")
