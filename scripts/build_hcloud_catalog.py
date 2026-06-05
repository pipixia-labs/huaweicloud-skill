#!/usr/bin/env python3
"""Build a compact hcloud service catalog from a local KooCLI metaRepo tree."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path.home() / ".hcloud" / "metaRepo"
DEFAULT_OUTPUT = ROOT / "references" / "hcloud-service-catalog.generated.json"

READ_ONLY_ACTIONS = ("List", "Show", "Count", "Check", "Search", "Query", "Get", "Download")
MUTATING_ACTIONS = (
    "Accept",
    "Add",
    "Apply",
    "Associate",
    "Attach",
    "Batch",
    "Bind",
    "Change",
    "Clear",
    "Copy",
    "Create",
    "Delete",
    "Detach",
    "Disable",
    "Disassociate",
    "Enable",
    "Execute",
    "Expand",
    "Export",
    "Import",
    "Migrate",
    "Modify",
    "Move",
    "Pause",
    "Reboot",
    "Remove",
    "Reset",
    "Resize",
    "Restore",
    "Resume",
    "Retry",
    "Run",
    "Set",
    "Start",
    "Stop",
    "Switch",
    "Unbind",
    "Uninstall",
    "Update",
    "Upgrade",
    "Upload",
    "Verify",
)
NAMESPACE_TOKENS = ("Batch", "Nova", "Neutron", "Glance", "Cinder", "Keystone")
ACTION_TOKENS = tuple(dict.fromkeys((*READ_ONLY_ACTIONS, *MUTATING_ACTIONS)))
IGNORED_PARAM_NAMES = {"x-auth-token", "content-type", "authorization", "x-language", "[n]"}
MAX_TEXT = 320


def normalize_token(value: str) -> str:
    """Return a lowercase alphanumeric-only token for loose matching."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def clean_text(value: Any, max_chars: int = MAX_TEXT) -> str:
    """Return a compact single-line text value."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def load_json(path: Path) -> Any:
    """Return parsed JSON content from a file."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_service_items(meta_repo: Path) -> dict[str, dict[str, Any]]:
    """Load service metadata keyed by normalized service name."""
    services_file = meta_repo / "services_en.json"
    if not services_file.exists():
        return {}
    data = load_json(services_file)
    services: dict[str, dict[str, Any]] = {}
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue
        service = item.get("Service", {})
        if not isinstance(service, dict):
            continue
        name = str(service.get("Text") or "").strip()
        if not name:
            continue
        services[normalize_token(name)] = {
            "name": name,
            "description": clean_text(service.get("Description")),
            "category": str(item.get("Category") or "Unknown"),
            "is_global": item.get("IsGlobal"),
        }
    return services


def select_version(versions: Any) -> str:
    """Select the highest version token from an apiList Versions field."""
    raw_versions = [str(version).strip() for version in versions if str(version).strip()] if isinstance(versions, list) else []
    if not raw_versions:
        return ""

    def version_key(version: str) -> list[int]:
        parts: list[int] = []
        for part in re.split(r"[._-]", version.lower().lstrip("v")):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(-1)
        return parts

    return max(raw_versions, key=version_key)


def operation_tokens(operation: str) -> list[str]:
    """Split an hcloud operation name into useful tokens."""
    raw_tokens = re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+", operation)
    if raw_tokens:
        return [token[:1].upper() + token[1:] for token in raw_tokens]

    lowered = operation.lower()
    matches: list[tuple[int, int, str]] = []
    for token in (*NAMESPACE_TOKENS, *ACTION_TOKENS):
        index = lowered.find(token.lower())
        if index >= 0:
            matches.append((index, -len(token), token))
    return [token for _, _, token in sorted(matches)] or [operation]


def operation_action(operation: str) -> str | None:
    """Return the first recognized action token in an operation name."""
    for token in operation_tokens(operation):
        if token in ACTION_TOKENS and token not in NAMESPACE_TOKENS:
            return token
    return None


def load_detail(template_dir: Path, operation_name: str, version: str) -> tuple[dict[str, Any], str | None]:
    """Load a selected operation detail file when present."""
    candidates: list[Path] = []
    if version:
        candidates.append(template_dir / f"{operation_name}_{version}_en.yaml")
    candidates.append(template_dir / f"{operation_name}_en.yaml")
    candidates.extend(sorted(template_dir.glob(f"{operation_name}_*_en.yaml")))

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen or not candidate.exists():
            continue
        seen.add(candidate)
        try:
            payload = load_json(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload, candidate.name
    return {}, None


def iter_param_names(param: dict[str, Any]) -> list[str]:
    """Return normalized parameter names from one metadata param object."""
    raw_names = param.get("Name", [])
    names = raw_names if isinstance(raw_names, list) else [raw_names]
    result: list[str] = []
    for raw_name in names:
        name = str(raw_name or "").strip()
        if not name or name.lower() in IGNORED_PARAM_NAMES:
            continue
        result.append(name)
    return result


def extract_params(detail: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return required and optional parameter names from an operation detail payload."""
    required: list[str] = []
    optional: list[str] = []
    params = detail.get("Params", [])
    if not isinstance(params, list):
        return required, optional
    for param in params:
        if not isinstance(param, dict):
            continue
        target = required if param.get("Required") is True else optional
        for name in iter_param_names(param):
            target.append(name)
    return list(dict.fromkeys(required)), list(dict.fromkeys(optional))


def build_operation(template_dir: Path, raw_api: dict[str, Any]) -> dict[str, Any] | None:
    """Build one compact catalog operation item."""
    operation_name = str(raw_api.get("Name") or "").strip()
    if not operation_name:
        return None
    version = select_version(raw_api.get("Versions", []))
    detail, detail_file = load_detail(template_dir, operation_name, version)
    required_params, optional_params = extract_params(detail)
    request = detail.get("Request", {}) if isinstance(detail.get("Request"), dict) else {}
    suggests = raw_api.get("Suggests", {})
    summary = ""
    if isinstance(suggests, dict):
        summary = str(suggests.get(version) or next((value for value in suggests.values() if value), "") or "")
    action = operation_action(operation_name)
    params_lower = {name.lower().replace("-", "_") for name in (*required_params, *optional_params)}
    return {
        "name": operation_name,
        "summary": clean_text(summary),
        "description": clean_text(detail.get("Description")),
        "versions": raw_api.get("Versions", []) if isinstance(raw_api.get("Versions"), list) else [],
        "selected_version": version,
        "action": action,
        "read_only": action in READ_ONLY_ACTIONS,
        "detail_cached": bool(detail_file),
        "detail_file": detail_file,
        "method": request.get("Method"),
        "path": request.get("Path"),
        "has_body_params": request.get("HasBodyParams"),
        "required_params": required_params,
        "optional_params": optional_params,
        "supports_limit": "limit" in params_lower,
    }


def build_catalog(meta_repo: Path) -> dict[str, Any]:
    """Build the complete generated catalog from a metaRepo directory."""
    services = load_service_items(meta_repo)
    template_root = meta_repo / "template"
    catalog_services: dict[str, Any] = {}
    if not template_root.exists():
        return {"schema_version": 1, "source": {"format": "hcloud metaRepo"}, "services": catalog_services}

    for template_dir in sorted(path for path in template_root.iterdir() if path.is_dir()):
        apis_file = template_dir / "apis_en.json"
        if not apis_file.exists():
            continue
        service_key = normalize_token(template_dir.name)
        service_info = services.get(service_key, {})
        service_name = str(service_info.get("name") or template_dir.name.upper())
        apis_data = load_json(apis_file)
        operations: dict[str, Any] = {}
        for raw_api in apis_data.get("apiList", {}).values():
            if not isinstance(raw_api, dict):
                continue
            operation = build_operation(template_dir, raw_api)
            if operation:
                operations[operation["name"]] = operation
        if not operations:
            continue
        catalog_services[service_key] = {
            "name": service_name,
            "service_key": service_key,
            "template_dir": template_dir.name,
            "category": service_info.get("category", "Unknown"),
            "description": service_info.get("description", ""),
            "is_global": service_info.get("is_global"),
            "operation_count": len(operations),
            "operations": dict(sorted(operations.items(), key=lambda item: item[0].lower())),
        }

    services_file = meta_repo / "services_en.json"
    services_update_time = None
    if services_file.exists():
        services_update_time = load_json(services_file).get("updateTime")
    operation_count = sum(service["operation_count"] for service in catalog_services.values())
    return {
        "schema_version": 1,
        "source": {
            "format": "hcloud metaRepo",
            "services_update_time": services_update_time,
            "service_count": len(catalog_services),
            "operation_count": operation_count,
        },
        "services": dict(sorted(catalog_services.items(), key=lambda item: item[1]["name"].lower())),
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-meta-repo", default=str(DEFAULT_SOURCE), help="Source hcloud metaRepo directory.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Generated catalog output path.")
    parser.add_argument("--pretty", action="store_true", help="Write indented JSON instead of compact JSON.")
    return parser.parse_args()


def main() -> int:
    """Generate the hcloud service catalog."""
    args = parse_args()
    source = Path(args.source_meta_repo).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    catalog = build_catalog(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.pretty:
        text = json.dumps(catalog, ensure_ascii=False, indent=2)
    else:
        text = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    output.write_text(text + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "success": True,
                "output": str(output),
                "service_count": catalog["source"]["service_count"],
                "operation_count": catalog["source"]["operation_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
