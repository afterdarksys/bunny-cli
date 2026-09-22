"""Output formatting utilities."""
from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

from bunny_cli.config import load_config

console = Console()


def wants_json(as_json: bool) -> bool:
    """True when this command should print JSON.

    An explicit ``--json`` flag wins. Otherwise ``BUNNY_OUTPUT_FORMAT`` and
    the configured ``output_format`` are consulted.
    """
    if as_json:
        return True
    return load_config().output_format == "json"


def format_bytes(byte_count: float) -> str:
    """Format a byte count for a terminal column."""
    value = float(byte_count)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(value) < 1024.0:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} EB"


def sum_numeric_chart(chart: Any) -> float:
    """Sum a Bunny chart object.

    Some responses use ``{"Total": n}`` and others map timestamps to numbers.
    Non-numeric values are ignored.
    """
    if not isinstance(chart, dict):
        return 0.0
    total = chart.get("Total")
    if isinstance(total, (int, float)) and not isinstance(total, bool):
        return float(total)
    summed = 0.0
    for value in chart.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            summed += float(value)
    return summed


def mask_secret(value: Any) -> str:
    """Return a fixed mask. The secret is not echoed."""
    if not value:
        return "[dim]-[/dim]"
    return "********"


def print_json(data: Any) -> None:
    """Print data as JSON."""
    console.print_json(json.dumps(data, indent=2, default=str))


def print_table(
    data: list[dict[str, Any]],
    columns: list[str],
    headers: list[str] | None = None,
) -> None:
    """Print data as a table."""
    if not data:
        console.print("[dim]No results[/dim]")
        return

    if headers is None:
        headers = columns

    table = Table(show_header=True, header_style="bold cyan")
    for header in headers:
        table.add_column(header)

    for row in data:
        values = []
        for col in columns:
            value = row.get(col, "")
            if isinstance(value, bool):
                value = "[green]Yes[/green]" if value else "[red]No[/red]"
            elif value is None:
                value = "[dim]-[/dim]"
            else:
                value = str(value)
            values.append(value)
        table.add_row(*values)

    console.print(table)


def print_dict(data: dict[str, Any], title: str | None = None) -> None:
    """Print a dictionary as a formatted table."""
    if title:
        console.print(f"\n[bold]{title}[/bold]")

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    for key, value in data.items():
        if isinstance(value, bool):
            value_str = "[green]Yes[/green]" if value else "[red]No[/red]"
        elif isinstance(value, (list, dict)):
            value_str = json.dumps(value, indent=2, default=str)
        elif value is None:
            value_str = "[dim]-[/dim]"
        else:
            value_str = str(value)
        table.add_row(key, value_str)

    console.print(table)


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]ℹ[/blue] {message}")
