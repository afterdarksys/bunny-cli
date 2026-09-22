"""Configuration commands."""
from __future__ import annotations

import click

from bunny_cli.client import BunnyClient
from bunny_cli.config import (
    SETTABLE_KEYS,
    describe_api_key,
    fingerprint_secret,
    get_config_path,
    load_config,
    load_stored_config,
    save_config,
)
from bunny_cli.output import console, print_dict, print_success
from bunny_cli.validate import require_api_key


@click.group()
def config() -> None:
    """Manage Bunny CLI configuration."""
    pass


@config.command("set-key")
@click.argument("api_key", required=False)
def set_key(api_key: str | None) -> None:
    """Set your Bunny.net API key.

    Omit the argument to type the key without saving it in shell history.
    Get your API key from: https://panel.bunny.net/account
    """
    if not api_key:
        api_key = click.prompt("API key", hide_input=True)
    cleaned = require_api_key(api_key)
    cfg = load_stored_config()
    cfg.api_key = cleaned
    save_config(cfg)
    print_success(f"API key saved to {get_config_path()}")


@config.command("show")
def show() -> None:
    """Show current configuration.

    The API key is shown as a SHA-256 fingerprint, never as the key itself.
    """
    cfg = load_config()
    key, source = describe_api_key()
    data = cfg.model_dump()
    data["api_key"] = fingerprint_secret(key) if key else None
    data["api_key_source"] = source
    print_dict(data, "Configuration")
    console.print(f"\n[dim]Config file: {get_config_path()}[/dim]")
    console.print("[dim]File mode is restricted to the current user.[/dim]")


@config.command("set")
@click.argument("key")
@click.argument("value")
def set_value(key: str, value: str) -> None:
    """Set a configuration value.

    Available keys: default_storage_zone, default_pull_zone, default_dns_zone, output_format
    """
    if key not in SETTABLE_KEYS:
        raise click.ClickException(f"Invalid key. Valid keys: {', '.join(SETTABLE_KEYS)}")
    if key == "output_format" and value not in {"table", "json"}:
        raise click.ClickException("output_format must be 'table' or 'json'")
    if key != "output_format":
        try:
            zone_id = int(value)
        except ValueError as exc:
            raise click.ClickException(f"{key} must be an integer zone id") from exc
        if zone_id < 1:
            raise click.ClickException(f"{key} must be an integer zone id")

    cfg = load_stored_config()
    setattr(cfg, key, value)
    save_config(cfg)
    print_success(f"Set {key} = {value}")


@config.command("unset")
@click.argument("key")
def unset_value(key: str) -> None:
    """Remove a stored configuration value.

    Available keys: api_key, default_storage_zone, default_pull_zone,
    default_dns_zone, output_format
    """
    valid = ("api_key", *SETTABLE_KEYS)
    if key not in valid:
        raise click.ClickException(f"Invalid key. Valid keys: {', '.join(valid)}")
    cfg = load_stored_config()
    if key == "output_format":
        cfg.output_format = "table"
    else:
        setattr(cfg, key, None)
    save_config(cfg)
    print_success(f"Unset {key}")


@config.command("path")
def path() -> None:
    """Show the configuration file path."""
    console.print(str(get_config_path()))


@config.command("test")
def test_key() -> None:
    """Check that the configured API key is accepted."""
    with BunnyClient() as client:
        client.get("/pullzone", params={"page": 1, "perPage": 1})
    print_success("API key accepted")
