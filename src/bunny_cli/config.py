"""Configuration management for Bunny CLI."""

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from pydantic_settings import BaseSettings


class BunnyConfig(BaseModel):
    """Bunny CLI configuration."""

    api_key: Optional[str] = None
    default_storage_zone: Optional[str] = None
    default_pull_zone: Optional[str] = None
    default_dns_zone: Optional[str] = None
    output_format: str = "table"  # table, json, yaml


class Settings(BaseSettings):
    """Environment-based settings."""

    bunny_api_key: Optional[str] = None

    class Config:
        env_prefix = "BUNNY_"
        env_file = ".env"


def get_config_path() -> Path:
    """Get the configuration file path."""
    config_dir = Path.home() / ".config" / "bunny"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def load_config() -> BunnyConfig:
    """Load configuration from file and environment."""
    config_path = get_config_path()
    config = BunnyConfig()

    # Load from file if exists
    if config_path.exists():
        try:
            with open(config_path) as f:
                data = json.load(f)
                config = BunnyConfig(**data)
        except (json.JSONDecodeError, ValueError):
            pass

    # Environment variables override file config
    env_key = os.environ.get("BUNNY_API_KEY")
    if env_key:
        config.api_key = env_key

    # Also check BUNNY_API_ACCESS_KEY for compatibility
    env_key = os.environ.get("BUNNY_API_ACCESS_KEY")
    if env_key:
        config.api_key = env_key

    return config


def save_config(config: BunnyConfig) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    with open(config_path, "w") as f:
        json.dump(config.model_dump(exclude_none=True), f, indent=2)


def get_api_key() -> Optional[str]:
    """Get the API key from config or environment."""
    config = load_config()
    return config.api_key
