#!/usr/bin/env python3
"""Read the generated hcloud metadata catalog used for broad service discovery."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "references" / "hcloud-service-catalog.generated.json"
CONFIDENCE_PATH = ROOT / "references" / "hcloud-service-confidence.json"

READ_ONLY_ACTIONS = {"List", "Show", "Count", "Check", "Search", "Query", "Get", "Download"}
DISCOVERY_ACTIONS = {"List", "Count", "Search", "Query", "Check"}
IGNORED_REQUIRED_PARAMS = {"x-auth-token", "content-type", "authorization", "x-language", "project_id", "projectid"}
PROJECT_PARAM_NAMES = {"project_id", "projectid"}
AUTH_PARAM_NAMES = IGNORED_REQUIRED_PARAMS - PROJECT_PARAM_NAMES


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


def load_confidence(path: Path = CONFIDENCE_PATH) -> dict[str, Any]:
    """Load optional confidence and live-validation metadata."""
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


def parameter_items(operation: dict[str, Any]) -> list[dict[str, Any]]:
    """Return structured parameter items, falling back to legacy lists."""
    raw_params = operation.get("params")
    if isinstance(raw_params, list):
        items = [param for param in raw_params if isinstance(param, dict)]
        known = {normalize_param_name(str(param.get("name") or "")) for param in items}
        for raw_name in operation.get("optional_params") or []:
            name = str(raw_name)
            normalized = normalize_param_name(name)
            if not normalized or normalized in known:
                continue
            items.append(
                {
                    "name": name,
                    "required": False,
                    "position": "",
                }
            )
        return items

    items: list[dict[str, Any]] = []
    for required, field in ((True, "required_params"), (False, "optional_params")):
        for raw_name in operation.get(field) or []:
            name = str(raw_name)
            normalized = normalize_param_name(name)
            if not normalized:
                continue
            items.append(
                {
                    "name": name,
                    "normalized_name": normalized,
                    "required": required,
                    "position": "",
                }
            )
    return items


def is_header_param(param: dict[str, Any]) -> bool:
    """Return whether a parameter is a header parameter."""
    return str(param.get("position") or param.get("in") or "").lower() == "header"


def operation_param_names(operation: dict[str, Any], include_headers: bool = False) -> list[str]:
    """Return known operation parameter names preserving catalog spelling."""
    names: list[str] = []
    for param in parameter_items(operation):
        if not include_headers and is_header_param(param):
            continue
        name = str(param.get("name") or "")
        normalized = normalize_param_name(name)
        if not normalized or normalized in IGNORED_REQUIRED_PARAMS:
            continue
        names.append(name)
    return list(dict.fromkeys(names))


def normalized_required_params(operation: dict[str, Any], include_project: bool = False) -> list[str]:
    """Return required non-auth parameter names for a catalog operation."""
    required: list[str] = []
    for param in parameter_items(operation):
        if param.get("required") is not True:
            continue
        if is_header_param(param):
            continue
        normalized = normalize_param_name(str(param.get("name") or ""))
        if not normalized:
            continue
        if normalized in AUTH_PARAM_NAMES:
            continue
        if not include_project and normalized in PROJECT_PARAM_NAMES:
            continue
        required.append(normalized)
    return list(dict.fromkeys(required))


def required_param_names(operation: dict[str, Any], include_project: bool = False) -> list[str]:
    """Return required non-auth parameter names preserving catalog spelling."""
    names: list[str] = []
    for param in parameter_items(operation):
        if param.get("required") is not True:
            continue
        if is_header_param(param):
            continue
        name = str(param.get("name") or "")
        normalized = normalize_param_name(name)
        if not normalized:
            continue
        if normalized in AUTH_PARAM_NAMES:
            continue
        if not include_project and normalized in PROJECT_PARAM_NAMES:
            continue
        names.append(name)
    return list(dict.fromkeys(names))


def optional_param_names(operation: dict[str, Any]) -> list[str]:
    """Return optional non-header parameter names preserving catalog spelling."""
    names: list[str] = []
    for param in parameter_items(operation):
        if param.get("required") is True:
            continue
        if is_header_param(param):
            continue
        name = str(param.get("name") or "")
        normalized = normalize_param_name(name)
        if not normalized or normalized in PROJECT_PARAM_NAMES:
            continue
        names.append(name)
    return list(dict.fromkeys(names))


def supports_limit(operation: dict[str, Any]) -> bool:
    """Return whether operation metadata exposes a limit parameter."""
    return any(normalize_param_name(name) == "limit" for name in operation_param_names(operation, include_headers=False))


def service_confidence(confidence: dict[str, Any], service_name: str) -> dict[str, Any]:
    """Return optional confidence metadata for a service."""
    services = confidence.get("services", {})
    if not isinstance(services, dict):
        return {}
    return services.get(service_name) or services.get(service_name.upper()) or {}


def operation_confidence(confidence: dict[str, Any], service_name: str, operation_name: str) -> dict[str, Any]:
    """Return optional confidence metadata for a service operation."""
    service = service_confidence(confidence, service_name)
    operations = service.get("operations", {})
    if not isinstance(operations, dict):
        return {}
    return operations.get(operation_name) or {}


def operation_dryrun_state(confidence: dict[str, Any], service_name: str, operation_name: str) -> str:
    """Return dry-run support state for an operation."""
    state = str(operation_confidence(confidence, service_name, operation_name).get("dryrun") or "unknown").lower()
    if state not in {"supported", "unsupported", "unknown"}:
        return "unknown"
    return state


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
