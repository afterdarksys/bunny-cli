"""Keep tests off the real config file and away from the network."""
from __future__ import annotations

from pathlib import Path

import pytest

from bunny_cli.client import install_transport, set_command_api_key


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_path = tmp_path / "bunny" / "config.json"
    monkeypatch.setattr("bunny_cli.config.get_config_path", lambda: config_path)
    monkeypatch.setattr("bunny_cli.commands.config.get_config_path", lambda: config_path)
    for name in (
        "BUNNY_API_KEY",
        "BUNNY_API_ACCESS_KEY",
        "BUNNY_OUTPUT_FORMAT",
        "CF_API_TOKEN",
        "CLOUDFLARE_API_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    install_transport(None)
    set_command_api_key(None)
    yield config_path
    install_transport(None)
    set_command_api_key(None)
