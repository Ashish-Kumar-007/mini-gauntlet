import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from app.domain.errors import InventoryLoadError
from app.domain.models import Account, InventorySnapshot, Provider


def _object(value: object, location: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise InventoryLoadError(f"{location} must be an object")
    return value


def _non_empty_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InventoryLoadError(f"{location} must be a non-empty string")
    return value


def load_inventory(path: str | Path) -> InventorySnapshot:
    try:
        text = Path(path).read_text(encoding="utf-8")
        raw = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InventoryLoadError("Inventory file could not be read or parsed") from error

    root = _object(raw, "inventory")
    timestamp = _non_empty_string(root.get("snapshot_taken_at"), "snapshot_taken_at")
    try:
        snapshot_taken_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise InventoryLoadError("snapshot_taken_at must be an ISO-8601 timestamp") from error
    if snapshot_taken_at.tzinfo is None or snapshot_taken_at.utcoffset() is None:
        raise InventoryLoadError("snapshot_taken_at must include a timezone")

    raw_accounts = root.get("accounts")
    if not isinstance(raw_accounts, list):
        raise InventoryLoadError("accounts must be an array")

    accounts: list[Account] = []
    account_ids: set[str] = set()
    for index, value in enumerate(raw_accounts):
        location = f"accounts[{index}]"
        item = _object(value, location)
        try:
            provider = Provider(_non_empty_string(item.get("provider"), f"{location}.provider"))
        except ValueError as error:
            raise InventoryLoadError(f"{location}.provider is unsupported") from error

        account_id = _non_empty_string(item.get("account_id"), f"{location}.account_id")
        if account_id in account_ids:
            raise InventoryLoadError(f"duplicate account_id: {account_id}")
        account_ids.add(account_id)

        name = item.get("name")
        if name is not None and not isinstance(name, str):
            raise InventoryLoadError(f"{location}.name must be a string or null")

        latency = item.get("simulated_latency_ms", 0)
        if type(latency) is not int or latency < 0:
            raise InventoryLoadError(f"{location}.simulated_latency_ms must be non-negative")

        errors_value = item.get("errors", {})
        errors_object = _object(errors_value, f"{location}.errors")
        errors: dict[str, str] = {}
        for collection, code in errors_object.items():
            if not isinstance(collection, str) or not isinstance(code, str):
                raise InventoryLoadError(f"{location}.errors entries must be string pairs")
            errors[collection] = code

        resources_value = item.get("resources", {})
        resources_object = _object(resources_value, f"{location}.resources")
        resources: dict[str, list[object]] = {}
        for collection, collection_value in resources_object.items():
            if not isinstance(collection, str) or not isinstance(collection_value, list):
                raise InventoryLoadError(f"{location}.resources collections must be arrays")
            resources[collection] = collection_value

        accounts.append(
            Account(
                provider=provider,
                account_id=account_id,
                name=name,
                simulated_latency_ms=latency,
                errors=errors,
                resources=resources,
            )
        )

    return InventorySnapshot(snapshot_taken_at=snapshot_taken_at, accounts=tuple(accounts))
