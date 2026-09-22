"""Tests for configuration module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from bunny_cli.config import BunnyConfig, load_config, save_config


def test_bunny_config_defaults():
    """Test BunnyConfig has correct defaults."""
    config = BunnyConfig()
    assert config.api_key is None
    assert config.output_format == "table"
    assert config.default_pull_zone is None


def test_bunny_config_with_values():
    """Test BunnyConfig with custom values."""
    config = BunnyConfig(
        api_key="test-key",
        output_format="json",
        default_pull_zone="12345",
    )
    assert config.api_key == "test-key"
    assert config.output_format == "json"
    assert config.default_pull_zone == "12345"


def test_save_and_load_config():
    """Test saving and loading configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        with patch("bunny_cli.config.get_config_path", return_value=config_path):
            # Save config
            config = BunnyConfig(api_key="test-key-123")
            save_config(config)

            # Verify file exists
            assert config_path.exists()

            # Load config
            loaded = load_config()
            assert loaded.api_key == "test-key-123"


def test_load_config_with_env_override():
    """Test that environment variables override file config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        # Create a config file
        with open(config_path, "w") as f:
            json.dump({"api_key": "file-key"}, f)

        with patch("bunny_cli.config.get_config_path", return_value=config_path):
            with patch.dict("os.environ", {"BUNNY_API_KEY": "env-key"}):
                loaded = load_config()
                assert loaded.api_key == "env-key"


def test_load_config_missing_file():
    """Test loading config when file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "nonexistent" / "config.json"

        with patch("bunny_cli.config.get_config_path", return_value=config_path):
            loaded = load_config()
            assert loaded.api_key is None
