#!/usr/bin/env python3
"""Read the generated hcloud metadata catalog used for broad service discovery."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "references" / "hcloud-service-catalog.generated.json"

READ_ONLY_ACTIONS = {"List", "Show", "Count", "Check", "Search", "Query", "Get", "Download"}
DISCOVERY_ACTIONS = {"List", "Count", "Search", "Query", "Check"}
IGNORED_REQUIRED_PARAMS = {"x-auth-token", "content-type", "authorization", "x-language", "project_id", "projectid"}


def normalize_token(value: str) -> str:
    """Return a lowercase alphanumeric-only token for loose matching."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def normalize_param_name(value: str) -> str:
    """Normalize a KooCLI parameter name for comparison."""
    return value.strip().lstrip("-").replace("-", "_").lower()


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    """Load the generated hcloud service catalog."""
    if not path.exists():
        return {"schema_version": 1, "services": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def service_index(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return catalog services keyed by normalized service name and template dir."""
    index: dict[str, dict[str, Any]] = {}
    for service in catalog.get("services", {}).values():
        if not isinstance(service, dict):
            continue
        candidates = [
            str(service.get("name") or ""),
            str(service.get("template_dir") or ""),
            str(service.get("service_key") or ""),
        ]
        for candidate in candidates:
            token = normalize_token(candidate)
            if token:
                index[token] = service
    return index


def resolve_service(catalog: dict[str, Any], service_name: str) -> dict[str, Any] | None:
    """Resolve a service name against the generated catalog."""
    return service_index(catalog).get(normalize_token(service_name))


def operation_index(service: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return service operations keyed by normalized operation name."""
    index: dict[str, dict[str, Any]] = {}
    for operation in service.get("operations", {}).values():
        if not isinstance(operation, dict):
            continue
        name = str(operation.get("name") or "")
        token = normalize_token(name)
        if token:
            index[token] = operation
    return index


def resolve_operation(service: dict[str, Any], operation_name: str) -> dict[str, Any] | None:
    """Resolve an operation name against a catalog service."""
    return operation_index(service).get(normalize_token(operation_name))


def command_service_name(service: dict[str, Any], fallback: str) -> str:
    """Return the service name to pass to hcloud."""
    return str(service.get("name") or fallback)


def normalized_required_params(operation: dict[str, Any], include_project: bool = False) -> list[str]:
    """Return required non-auth parameter names for a catalog operation."""
    required: list[str] = []
    for name in operation.get("required_params") or []:
        normalized = normalize_param_name(str(name))
        if not normalized:
            continue
        if not include_project and normalized in IGNORED_REQUIRED_PARAMS:
            continue
        required.append(normalized)
    return list(dict.fromkeys(required))


def supports_limit(operation: dict[str, Any]) -> bool:
    """Return whether operation metadata exposes a limit parameter."""
    names = [*(operation.get("required_params") or []), *(operation.get("optional_params") or [])]
    return any(normalize_param_name(str(name)) == "limit" for name in names)


def is_read_only(operation: dict[str, Any]) -> bool:
    """Return whether the catalog classifies an operation as read-only."""
    return bool(operation.get("read_only"))


def is_discovery_operation(operation: dict[str, Any]) -> bool:
    """Return whether an operation is safe as a generic list/count discovery entry."""
    return (
        is_read_only(operation)
        and str(operation.get("action") or "") in DISCOVERY_ACTIONS
        and not normalized_required_params(operation)
    )


def discovery_operations(service: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Return deterministic metadata-backed discovery operations for one service."""
    operations = [
        operation
        for operation in service.get("operations", {}).values()
        if isinstance(operation, dict) and is_discovery_operation(operation)
    ]
    priority = {"List": 0, "Count": 1, "Search": 2, "Query": 3, "Check": 4}
    operations.sort(key=lambda item: (priority.get(str(item.get("action")), 99), str(item.get("name", "")).lower()))
    return operations[:limit]


def catalog_service_names(catalog: dict[str, Any]) -> list[str]:
    """Return sorted catalog service display names."""
    return sorted(
        str(service.get("name") or key)
        for key, service in catalog.get("services", {}).items()
        if isinstance(service, dict)
    )
