"""Bunny CLI - A complete CLI for bunny.net"""
from __future__ import annotations

import click
from rich.console import Console

from bunny_cli import __version__
from bunny_cli.client import BunnyAPIError, command_api_key, set_command_api_key
from bunny_cli.commands.cf import cf
from bunny_cli.commands.config import config
from bunny_cli.commands.dns import dns
from bunny_cli.commands.pullzone import pullzone
from bunny_cli.commands.purge import purge
from bunny_cli.commands.stats import stats
from bunny_cli.commands.storage import storage
from bunny_cli.config import ConfigError, api_key_from_env
from bunny_cli.validate import require_api_key

console = Console()


def _public_error(message: str) -> str:
    text = "".join(char if char.isprintable() else " " for char in message)
    text = " ".join(text.split())
    for secret in (command_api_key(), api_key_from_env()[0]):
        if secret and secret in text:
            text = text.replace(secret, "[redacted]")
    if len(text) > 300:
        return text[:300] + "..."
    return text or "unexpected failure"


class BunnyCLI(click.Group):
    """Custom CLI group with error handling."""

    def invoke(self, ctx: click.Context) -> None:
        try:
            super().invoke(ctx)
            return None
        except (click.Abort, click.exceptions.Exit):
            raise
        except click.ClickException:
            raise
        except (BunnyAPIError, ConfigError) as exc:
            console.print(f"[red]Error:[/red] {_public_error(exc.message)}")
            if isinstance(exc, BunnyAPIError) and exc.status_code:
                console.print(f"[dim]Status code: {exc.status_code}[/dim]")
            ctx.exit(1)
        except Exception as exc:
            console.print(f"[red]Error:[/red] {_public_error(str(exc))}")
            ctx.exit(1)


@click.group(cls=BunnyCLI)
@click.version_option(version=__version__, prog_name="bunny")
@click.option("--api-key", envvar="BUNNY_API_KEY", help="Bunny.net API key")
@click.pass_context
def cli(ctx: click.Context, api_key: str | None) -> None:
    """Bunny CLI - A complete CLI for bunny.net

    Manage CDN pull zones, DNS zones, storage, and more from the command line.

    Get your API key from: https://panel.bunny.net/account

    \b
    Quick start:
      bunny config set-key
      bunny pullzone list
      bunny dns list
    """
    ctx.ensure_object(dict)
    command_key = None
    if api_key and ctx.get_parameter_source("api_key") == click.core.ParameterSource.COMMANDLINE:
        command_key = require_api_key(api_key)
    set_command_api_key(command_key)
    ctx.obj["api_key"] = command_key


cli.add_command(cf)
cli.add_command(config)
cli.add_command(pullzone)
cli.add_command(dns)
cli.add_command(storage)
cli.add_command(purge)
cli.add_command(stats)


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
