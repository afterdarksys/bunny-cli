"""Output formatting utilities."""
from __future__ import annotations

import json
from typing import Any, List, Dict, Optional

from rich.console import Console
from rich.table import Table

console = Console()


def print_json(data: Any) -> None:
    """Print data as JSON."""
    console.print_json(json.dumps(data, indent=2, default=str))


def print_table(
    data: List[Dict[str, Any]],
    columns: List[str],
    headers: Optional[List[str]] = None,
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


def print_dict(data: Dict[str, Any], title: Optional[str] = None) -> None:
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
