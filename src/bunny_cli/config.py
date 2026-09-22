"""Configuration management for Bunny CLI.

Threats: keeps the account API key out of group/world-readable files and
out of command output. A key passed as a process argument can still appear
in shell history. This module does not protect a key readable by the same
Unix user.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

CONFIG_MODE = 0o600
DIR_MODE = 0o700
OUTPUT_FORMATS = {"table", "json"}
SETTABLE_KEYS = (
    "default_storage_zone",
    "default_pull_zone",
    "default_dns_zone",
    "output_format",
)


class ConfigError(Exception):
    """The local configuration file cannot be used safely."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class BunnyConfig(BaseModel):
    """Bunny CLI configuration."""

    model_config = ConfigDict(extra="ignore")

    api_key: str | None = None
    default_storage_zone: str | None = None
    default_pull_zone: str | None = None
    default_dns_zone: str | None = None
    output_format: str = "table"

    @field_validator("output_format")
    @classmethod
    def _check_output_format(cls, value: str) -> str:
        if value not in OUTPUT_FORMATS:
            raise ValueError("output_format must be 'table' or 'json'")
        return value


def get_config_path() -> Path:
    """Return the configuration file path. Does not create it."""
    return Path.home() / ".config" / "bunny" / "config.json"


def fingerprint_secret(secret: str) -> str:
    """Return a short SHA-256 fingerprint. The secret itself is not included."""
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def _reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise ConfigError(f"Refusing to use a symlinked config file: {path}")


def _prepare_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, DIR_MODE)


def _tighten_file(path: Path) -> bool:
    """Force mode 0600. Returns True when the previous mode was too open."""
    _reject_symlink(path)
    current = path.stat().st_mode & 0o777
    os.chmod(path, CONFIG_MODE)
    return current & 0o077 != 0


def load_stored_config() -> BunnyConfig:
    """Load the on-disk configuration without applying environment overrides."""
    config_path = get_config_path()
    if not config_path.exists():
        return BunnyConfig()
    _reject_symlink(config_path)
    _tighten_file(config_path)
    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read {config_path}") from exc
    if len(raw) > 64 * 1024:
        raise ConfigError(f"Config file is too large: {config_path}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is not valid JSON: {config_path}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a JSON object: {config_path}")
    try:
        return BunnyConfig(**data)
    except ValueError as exc:
        raise ConfigError(f"Config file is invalid: {config_path}") from exc


def api_key_from_env() -> tuple[str | None, str | None]:
    """Return (key, variable name) from the process environment."""
    for name in ("BUNNY_API_KEY", "BUNNY_API_ACCESS_KEY"):
        value = os.environ.get(name)
        if value:
            return value, name
    return None, None


def describe_api_key(command_key: str | None = None) -> tuple[str | None, str]:
    """Return the effective API key and where it came from.

    Precedence is the command-line flag, then the process environment,
    then the config file.
    """
    if command_key is None:
        from bunny_cli.client import command_api_key

        command_key = command_api_key()
    if command_key:
        return command_key, "flag"
    # Read the file first so a corrupt config fails closed, even when an
    # environment variable is also set.
    stored = load_stored_config()
    env_key, env_name = api_key_from_env()
    if env_key and env_name:
        return env_key, env_name
    if stored.api_key:
        return stored.api_key, "file"
    return None, "none"


def load_config(command_key: str | None = None) -> BunnyConfig:
    """Load configuration and overlay the effective API key."""
    config = load_stored_config()
    key, _source = describe_api_key(command_key)
    config.api_key = key
    env_format = os.environ.get("BUNNY_OUTPUT_FORMAT")
    if env_format:
        if env_format not in OUTPUT_FORMATS:
            raise ConfigError("BUNNY_OUTPUT_FORMAT must be 'table' or 'json'")
        config.output_format = env_format
    return config


def save_config(config: BunnyConfig) -> None:
    """Atomically write configuration as a private file."""
    config_path = get_config_path()
    _prepare_dir(config_path.parent)
    _reject_symlink(config_path)
    payload = json.dumps(config.model_dump(exclude_none=True), indent=2) + "\n"
    temporary = config_path.with_name(f".{config_path.name}.tmp")
    if temporary.is_symlink():
        raise ConfigError(f"Refusing to write through a symlink: {temporary}")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, CONFIG_MODE)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(temporary, CONFIG_MODE)
    os.replace(temporary, config_path)
    os.chmod(config_path, CONFIG_MODE)


def get_api_key(command_key: str | None = None) -> str | None:
    """Return the effective API key."""
    key, _source = describe_api_key(command_key)
    return key


def selected_zone(zone_id: int | None, kind: str) -> int:
    """Use the explicit zone id, or the configured default for read commands."""
    if zone_id is None:
        return default_zone_id(kind)
    if isinstance(zone_id, bool) or not isinstance(zone_id, int) or zone_id < 1:
        raise ConfigError("Invalid zone id")
    return zone_id


def default_zone_id(kind: str) -> int:
    """Resolve a configured default zone id. `kind` is pull, dns, or storage."""
    field = f"default_{kind}_zone"
    raw = getattr(load_stored_config(), field)
    if raw is None or raw == "":
        raise ConfigError(f"No zone id given and {field} is not configured")
    try:
        zone_id = int(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field} is not an integer") from exc
    if zone_id < 1:
        raise ConfigError(f"{field} is not a valid zone id")
    return zone_id
