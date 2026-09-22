"""Command behavior that does not touch the network."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
from click.testing import CliRunner

from bunny_cli.client import install_transport
from bunny_cli.commands.cf import CloudflareClient, plan_dns_migration
from bunny_cli.main import cli

KEY = "a" * 32
CF = "c" * 40
ZONE = "ab" * 16


def _zones(request: httpx.Request) -> httpx.Response:
    assert request.headers["AccessKey"] == KEY
    return httpx.Response(
        200,
        json=[
            {
                "Id": 9,
                "Name": "widgets",
                "OriginUrl": "https://origin.example",
                "Enabled": True,
                "MonthlyBandwidthUsed": 2048,
                "Hostnames": [{"Value": "cdn.example.com"}],
            }
        ],
    )


def test_api_key_flag_is_used(isolated_config: Path) -> None:
    install_transport(httpx.MockTransport(_zones))
    result = CliRunner().invoke(cli, ["--api-key", KEY, "pullzone", "list"])
    assert result.exit_code == 0, result.output
    assert "widgets" in result.output
    assert KEY not in result.output


def test_configured_output_format_json(isolated_config: Path) -> None:
    isolated_config.parent.mkdir(parents=True)
    isolated_config.write_text(
        json.dumps({"api_key": KEY, "output_format": "json"}),
        encoding="utf-8",
    )
    install_transport(httpx.MockTransport(_zones))
    result = CliRunner().invoke(cli, ["pullzone", "list"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed[0]["Name"] == "widgets"


def test_default_pull_zone_is_used_for_get(isolated_config: Path) -> None:
    isolated_config.parent.mkdir(parents=True)
    isolated_config.write_text(
        json.dumps({"api_key": KEY, "default_pull_zone": "9"}),
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/pullzone/9"
        return httpx.Response(
            200,
            json={
                "Id": 9,
                "Name": "widgets",
                "OriginUrl": "https://origin.example",
                "Enabled": True,
                "MonthlyBandwidthUsed": 0,
                "Hostnames": [],
                "EnableCacheSlice": False,
                "EnableAccessControlOriginHeader": False,
            },
        )

    install_transport(httpx.MockTransport(handler))
    result = CliRunner().invoke(cli, ["pullzone", "get"])
    assert result.exit_code == 0, result.output
    assert "widgets" in result.output


def test_declined_delete_aborts_quietly() -> None:
    result = CliRunner().invoke(cli, ["--api-key", KEY, "pullzone", "delete", "4"], input="n\n")
    assert result.exit_code != 0
    assert "API Error" not in result.output
    assert "Aborted" in result.output


def test_storage_get_masks_password_and_shows_created_date(isolated_config: Path) -> None:
    isolated_config.parent.mkdir(parents=True)
    isolated_config.write_text(json.dumps({"api_key": KEY}), encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Id": 3,
                "Name": "media",
                "Region": "DE",
                "StorageUsed": 1024,
                "FilesStored": 2,
                "DateCreated": "2024-02-02T00:00:00Z",
                "DateModified": "2024-03-03T00:00:00Z",
                "Password": "storage-secret-value",
                "ReadOnlyPassword": "read-secret-value",
                "ReplicationRegions": [],
                "PullZones": [],
            },
        )

    install_transport(httpx.MockTransport(handler))
    hidden = CliRunner().invoke(cli, ["storage", "get", "3"])
    assert hidden.exit_code == 0, hidden.output
    assert "storage-secret-value" not in hidden.output
    assert "2024-02-02T00:00:00Z" in hidden.output
    shown = CliRunner().invoke(cli, ["storage", "get", "3", "--show-secrets"])
    assert "storage-secret-value" in shown.output


def test_play_and_exec_cannot_be_combined() -> None:
    result = CliRunner().invoke(
        cli,
        ["cf", "pullzone", ZONE, "my-cdn", "--play", "--exec", "--cf-token", CF],
    )
    assert result.exit_code != 0
    assert "Specify --play" in result.output


def test_include_ns_keeps_nameserver_records() -> None:
    records = [
        {
            "type": "NS",
            "name": "example.com",
            "content": "ns1.example.com",
            "ttl": 300,
            "proxied": False,
        },
        {
            "type": "A",
            "name": "www.example.com",
            "content": "192.0.2.20",
            "ttl": 1,
            "proxied": False,
        },
    ]
    migrated, skipped_rows = plan_dns_migration(
        records, "example.com", skip_proxied=False, skip_ns=True
    )
    assert [row["type"] for row in migrated] == ["A"]
    assert skipped_rows[0]["reason"] == "NS record skipped"
    migrated, skipped_rows = plan_dns_migration(
        records, "example.com", skip_proxied=False, skip_ns=False
    )
    assert [row["type"] for row in migrated] == ["NS", "A"]
    assert migrated[1]["ttl"] == 300
    assert migrated[1]["name"] == "www"


def test_cloudflare_record_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        assert request.headers["Authorization"] == f"Bearer {CF}"
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "id": str(page),
                        "type": "A",
                        "name": "example.com",
                        "content": "192.0.2.1",
                    }
                ],
                "result_info": {"total_pages": 2},
            },
        )

    with CloudflareClient(CF, transport=httpx.MockTransport(handler)) as client:
        rows = client.list_dns_records(ZONE)
    assert [row["id"] for row in rows] == ["1", "2"]


def test_invalid_cloudflare_zone_id_is_rejected() -> None:
    result = CliRunner().invoke(cli, ["cf", "records", "../zones", "--cf-token", CF])
    assert result.exit_code != 0
    assert "32 hex" in result.output
