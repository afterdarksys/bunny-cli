"""Bunny CLI - A complete CLI for bunny.net"""
from __future__ import annotations

from typing import Optional

import click
from rich.console import Console

from bunny_cli import __version__
from bunny_cli.client import BunnyAPIError
from bunny_cli.commands.config import config
from bunny_cli.commands.dns import dns
from bunny_cli.commands.pullzone import pullzone
from bunny_cli.commands.purge import purge
from bunny_cli.commands.stats import stats
from bunny_cli.commands.storage import storage

console = Console()


class BunnyCLI(click.Group):
    """Custom CLI group with error handling."""

    def invoke(self, ctx: click.Context) -> None:
        try:
            return super().invoke(ctx)
        except BunnyAPIError as e:
            console.print(f"[red]API Error:[/red] {e.message}")
            if e.status_code:
                console.print(f"[dim]Status code: {e.status_code}[/dim]")
            ctx.exit(1)
        except click.ClickException:
            raise
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            ctx.exit(1)


@click.group(cls=BunnyCLI)
@click.version_option(version=__version__, prog_name="bunny")
@click.option("--api-key", envvar="BUNNY_API_KEY", help="Bunny.net API key")
@click.pass_context
def cli(ctx: click.Context, api_key: Optional[str]) -> None:
    """Bunny CLI - A complete CLI for bunny.net

    Manage CDN pull zones, DNS zones, storage, and more from the command line.

    Get your API key from: https://panel.bunny.net/account

    \b
    Quick start:
      bunny config set-key YOUR_API_KEY
      bunny pullzone list
      bunny dns list
    """
    ctx.ensure_object(dict)
    if api_key:
        ctx.obj["api_key"] = api_key


# Register command groups
cli.add_command(config)
cli.add_command(pullzone)
cli.add_command(dns)
cli.add_command(storage)
cli.add_command(purge)
cli.add_command(stats)


# Convenience aliases
@cli.command("zones")
@click.pass_context
def zones_alias(ctx: click.Context) -> None:
    """Alias for 'pullzone list'"""
    ctx.invoke(pullzone.commands["list"])


@cli.command("domains")
@click.pass_context
def domains_alias(ctx: click.Context) -> None:
    """Alias for 'dns list'"""
    ctx.invoke(dns.commands["list"])


def main() -> None:
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
