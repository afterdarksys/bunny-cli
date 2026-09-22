"""Negative tests for credential handling and fail-closed input checks."""
from __future__ import annotations

import json
import os
from pathlib import Path

import click
import httpx
import pytest
from click.testing import CliRunner

from bunny_cli.client import BunnyAPIError, BunnyClient, PullZoneAPI, install_transport
from bunny_cli.config import BunnyConfig, ConfigError, load_config, load_stored_config, save_config
from bunny_cli.dnsutil import parse_import_document, record_payload, type_to_int
from bunny_cli.main import cli
from bunny_cli.output import sum_numeric_chart
from bunny_cli.validate import require_hostname, require_http_url

KEY = "k" * 32


def test_config_file_is_private(isolated_config: Path) -> None:
    save_config(BunnyConfig(api_key=KEY))
    assert isolated_config.stat().st_mode & 0o777 == 0o600
    assert isolated_config.parent.stat().st_mode & 0o777 == 0o700


def test_open_config_is_tightened(isolated_config: Path) -> None:
    isolated_config.parent.mkdir(parents=True)
    isolated_config.write_text(json.dumps({"api_key": KEY}), encoding="utf-8")
    os.chmod(isolated_config, 0o644)
    loaded = load_stored_config()
    assert loaded.api_key == KEY
    assert isolated_config.stat().st_mode & 0o777 == 0o600


def test_symlink_config_is_refused(isolated_config: Path, tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.json"
    target.write_text("{}", encoding="utf-8")
    isolated_config.parent.mkdir(parents=True)
    isolated_config.symlink_to(target)
    with pytest.raises(ConfigError):
        load_stored_config()


def test_corrupt_config_fails_closed(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_config.parent.mkdir(parents=True)
    isolated_config.write_text("{", encoding="utf-8")
    os.chmod(isolated_config, 0o600)
    monkeypatch.setenv("BUNNY_API_KEY", KEY)
    with pytest.raises(ConfigError):
        load_config()
    with pytest.raises(ConfigError):
        BunnyClient()


def test_set_value_does_not_persist_env_key(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUNNY_API_KEY", KEY)
    result = CliRunner().invoke(cli, ["config", "set", "output_format", "json"])
    assert result.exit_code == 0
    stored = json.loads(isolated_config.read_text(encoding="utf-8"))
    assert "api_key" not in stored
    assert stored["output_format"] == "json"


def test_config_show_prints_fingerprint_not_secret(isolated_config: Path) -> None:
    result = CliRunner().invoke(cli, ["config", "set-key"], input=KEY + "\n")
    assert result.exit_code == 0
    assert KEY not in result.output
    shown = CliRunner().invoke(cli, ["config", "show"])
    assert shown.exit_code == 0
    assert KEY not in shown.output
    assert "sha256:" in shown.output
    assert json.loads(isolated_config.read_text(encoding="utf-8"))["api_key"] == KEY


def test_short_api_key_is_rejected() -> None:
    result = CliRunner().invoke(cli, ["config", "set-key", "too-short"])
    assert result.exit_code != 0


def test_unknown_dns_type_is_not_coerced_to_a() -> None:
    with pytest.raises(click.ClickException):
        type_to_int("ALIAS")


def test_apex_name_and_mx_priority() -> None:
    payload = record_payload("A", "@", "192.0.2.10", 300)
    assert payload["Name"] == ""
    with pytest.raises(click.ClickException):
        record_payload("MX", "@", "mail.example.com", 300)
    with pytest.raises(click.ClickException):
        record_payload("A", "www", "192.0.2.10", 0)


def test_import_rejects_unknown_type_before_any_request() -> None:
    with pytest.raises(click.ClickException):
        parse_import_document(
            {"records": [{"type": "ALIAS", "name": "@", "value": "192.0.2.1", "ttl": 300}]}
        )


def test_local_and_non_http_urls_are_rejected() -> None:
    with pytest.raises(click.ClickException):
        require_http_url("javascript:alert(1)")
    with pytest.raises(click.ClickException):
        require_http_url("https://127.0.0.1/secret")
    with pytest.raises(click.ClickException):
        require_http_url("https://169.254.169.254/latest/meta-data")
    assert require_http_url("https://origin.example/a") == "https://origin.example/a"


def test_redirect_is_refused_and_not_followed() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://evil.example/collect"})

    install_transport(httpx.MockTransport(handler))
    with pytest.raises(BunnyAPIError) as caught:
        with BunnyClient(KEY) as client:
            client.get("/pullzone")
    assert caught.value.status_code == 302
    assert len(calls) == 1
    assert "evil.example" not in str(calls[0].url)


def test_oversized_response_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-length": str(9 * 1024 * 1024)}, content=b"{}")

    install_transport(httpx.MockTransport(handler))
    with pytest.raises(BunnyAPIError, match="size limit"):
        with BunnyClient(KEY) as client:
            client.get("/pullzone")


def test_hostname_is_sent_as_a_query_parameter() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    with BunnyClient(KEY, transport=httpx.MockTransport(handler)) as client:
        PullZoneAPI(client).remove_hostname(7, "cdn.example.com")
        with pytest.raises(click.ClickException):
            PullZoneAPI(client).remove_hostname(7, "not a host")
    assert len(seen) == 1
    assert seen[0].url.params["hostname"] == "cdn.example.com"


def test_wildcard_hostname_is_allowed() -> None:
    assert require_hostname("*.example.com") == "*.example.com"


def test_chart_total_sums_timestamp_maps() -> None:
    assert sum_numeric_chart({"2024-01-01T00:00:00Z": 10, "2024-01-02T00:00:00Z": 5}) == 15
    assert sum_numeric_chart({"Total": 4, "ignored": "nope"}) == 4
