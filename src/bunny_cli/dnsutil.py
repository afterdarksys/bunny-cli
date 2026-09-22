"""DNS record conversion shared by the API client and migration commands.

Threats: an unknown type is rejected instead of stored as an A record.
Does not check that record values are routable or that a migration target
zone is the one the operator intended.
"""
from __future__ import annotations

from typing import Any

import click

from bunny_cli.validate import MAX_DNS_NAME, MAX_DNS_VALUE, require_ttl

RECORD_TYPES: dict[str, int] = {
    "A": 0,
    "AAAA": 1,
    "CNAME": 2,
    "TXT": 3,
    "MX": 4,
    "REDIRECT": 5,
    "FLATTEN": 6,
    "PULLZONE": 7,
    "SRV": 8,
    "CAA": 9,
    "PTR": 10,
    "SCRIPT": 11,
    "NS": 12,
}

INT_TO_TYPE: dict[int, str] = {
    0: "A",
    1: "AAAA",
    2: "CNAME",
    3: "TXT",
    4: "MX",
    5: "Redirect",
    6: "Flatten",
    7: "PullZone",
    8: "SRV",
    9: "CAA",
    10: "PTR",
    11: "Script",
    12: "NS",
}


def type_to_int(record_type: str) -> int:
    """Convert a record type name to the Bunny integer. Unknown types fail."""
    key = record_type.strip().upper()
    if key not in RECORD_TYPES:
        raise click.ClickException(f"Unsupported DNS record type: {record_type}")
    return RECORD_TYPES[key]


def int_to_type(type_int: int) -> str:
    """Convert a Bunny record type integer to a display name."""
    return INT_TO_TYPE.get(type_int, "Unknown")


def normalize_record_name(name: str) -> str:
    """Normalize a record name. '@' is the zone apex."""
    cleaned = name.strip()
    if cleaned in {"@", "@."}:
        return ""
    if not cleaned or len(cleaned) > MAX_DNS_NAME:
        raise click.ClickException("DNS name length is invalid")
    if any(ord(char) < 33 or ord(char) == 127 for char in cleaned):
        raise click.ClickException("DNS name contains unsupported characters")
    if "\\" in cleaned or "/" in cleaned:
        raise click.ClickException("DNS name contains unsupported characters")
    return cleaned


def normalize_record_value(value: str) -> str:
    """Reject empty values and control characters."""
    if not isinstance(value, str):
        raise click.ClickException("DNS value must be a string")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_DNS_VALUE:
        raise click.ClickException("DNS value length is invalid")
    if any(ord(char) < 32 or ord(char) == 127 for char in cleaned):
        raise click.ClickException("DNS value contains unsupported characters")
    return cleaned


def record_payload(
    record_type: str,
    name: str,
    value: str,
    ttl: int,
    *,
    priority: int | None = None,
    weight: int | None = None,
    port: int | None = None,
    disabled: bool | None = None,
) -> dict[str, Any]:
    """Build a Bunny DNS record body."""
    type_int = type_to_int(record_type)
    payload: dict[str, Any] = {
        "Type": type_int,
        "Name": normalize_record_name(name),
        "Value": normalize_record_value(value),
        "Ttl": require_ttl(ttl),
    }
    if type_int in {RECORD_TYPES["MX"], RECORD_TYPES["SRV"]} and priority is None:
        raise click.ClickException(f"{record_type.upper()} records require --priority")
    if priority is not None:
        bad_priority = isinstance(priority, bool) or not isinstance(priority, int)
        if bad_priority or priority < 0 or priority > 65535:
            raise click.ClickException("Priority must be an integer from 0 to 65535")
        payload["Priority"] = priority
    if weight is not None:
        if isinstance(weight, bool) or not isinstance(weight, int) or not (0 <= weight <= 65535):
            raise click.ClickException("Weight must be an integer from 0 to 65535")
        payload["Weight"] = weight
    if port is not None:
        if isinstance(port, bool) or not isinstance(port, int) or not (1 <= port <= 65535):
            raise click.ClickException("Port must be an integer from 1 to 65535")
        payload["Port"] = port
    if disabled is not None:
        if not isinstance(disabled, bool):
            raise click.ClickException("disabled must be true or false")
        payload["Disabled"] = disabled
    return payload


def export_document(zone: dict[str, Any]) -> dict[str, Any]:
    """Convert a Bunny DNS zone payload into the import/export document."""
    records = zone.get("Records") or []
    if not isinstance(records, list):
        raise click.ClickException("Zone payload did not include a record list")
    exported: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        item: dict[str, Any] = {
            "type": int_to_type(int(record.get("Type") or 0)),
            "name": record.get("Name") or "@",
            "value": record.get("Value") or "",
            "ttl": record.get("Ttl") or 300,
        }
        for source, dest in (
            ("Priority", "priority"),
            ("Weight", "weight"),
            ("Port", "port"),
        ):
            if record.get(source) is not None:
                item[dest] = record.get(source)
        if record.get("Disabled"):
            item["disabled"] = True
        exported.append(item)
    return {"domain": zone.get("Domain"), "records": exported}


def parse_import_document(data: Any) -> list[dict[str, Any]]:
    """Validate an import document and return Bunny record bodies."""
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise click.ClickException("Import file must be a JSON object with a records array")
    records = data["records"]
    if len(records) > 10000:
        raise click.ClickException("Import file has too many records")
    payloads: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise click.ClickException(f"Record {index} is not an object")
        try:
            ttl_raw = 300 if record.get("ttl") is None else record.get("ttl")
            if isinstance(ttl_raw, bool) or not isinstance(ttl_raw, (int, str)):
                raise click.ClickException(f"Record {index} is invalid")
            payloads.append(
                record_payload(
                    str(record.get("type") or ""),
                    str(record.get("name") if record.get("name") is not None else "@"),
                    str(record.get("value") or ""),
                    int(ttl_raw),
                    priority=record.get("priority"),
                    weight=record.get("weight"),
                    port=record.get("port"),
                    disabled=record.get("disabled"),
                )
            )
        except (TypeError, ValueError) as exc:
            raise click.ClickException(f"Record {index} is invalid") from exc
    return payloads
