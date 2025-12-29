"""Configuration commands."""
from __future__ import annotations

import click

from bunny_cli.config import get_config_path, load_config, save_config
from bunny_cli.output import console, print_dict, print_success


@click.group()
def config() -> None:
    """Manage Bunny CLI configuration."""
    pass


@config.command("set-key")
@click.argument("api_key")
def set_key(api_key: str) -> None:
    """Set your Bunny.net API key.

    Get your API key from: https://panel.bunny.net/account
    """
    cfg = load_config()
    cfg.api_key = api_key
    save_config(cfg)
    print_success(f"API key saved to {get_config_path()}")


@config.command("show")
def show() -> None:
    """Show current configuration."""
    cfg = load_config()
    data = cfg.model_dump()

    # Mask the API key
    if data.get("api_key"):
        key = data["api_key"]
        data["api_key"] = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"

    print_dict(data, "Configuration")
    console.print(f"\n[dim]Config file: {get_config_path()}[/dim]")


@config.command("set")
@click.argument("key")
@click.argument("value")
def set_value(key: str, value: str) -> None:
    """Set a configuration value.

    Available keys: default_storage_zone, default_pull_zone, default_dns_zone, output_format
    """
    cfg = load_config()

    valid_keys = ["default_storage_zone", "default_pull_zone", "default_dns_zone", "output_format"]
    if key not in valid_keys:
        raise click.ClickException(f"Invalid key. Valid keys: {', '.join(valid_keys)}")

    setattr(cfg, key, value)
    save_config(cfg)
    print_success(f"Set {key} = {value}")


@config.command("path")
def path() -> None:
    """Show the configuration file path."""
    console.print(str(get_config_path()))
