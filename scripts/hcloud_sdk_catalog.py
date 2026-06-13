#!/usr/bin/env python3
"""Inspect Huawei Cloud Python SDK metadata as a supplemental source.

Runtime discovery prefers installed huaweicloudsdk* packages. A local SDK source
tree can be supplied for maintenance and tests, but user machines are not
expected to carry the SDK repository.
"""

from __future__ import annotations

import argparse
import ast
from importlib import metadata as importlib_metadata
from importlib import util as importlib_util
import re
from pathlib import Path
from typing import Any

import hcloud_common


ROOT = hcloud_common.ROOT
DEFAULT_SDK_ROOT = ROOT.parent / "reference-projects" / "huaweicloud-sdk-python-v3"
READ_ONLY_ACTIONS = {"List", "Show", "Count", "Check", "Search", "Query", "Get", "Download"}
IGNORED_REQUIRED_PATH_PARAMS = {"project_id", "projectid", "domain_id", "domainid"}
IGNORED_SDK_PACKAGES = {"huaweicloudsdkcore", "huaweicloudsdkall"}


def normalize_token(value: str) -> str:
    """Return a lowercase alphanumeric-only token for loose matching."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def normalize_param_name(value: str) -> str:
    """Normalize a parameter name for comparison."""
    return value.strip().lstrip("-").replace("-", "_").lower()


def camel_to_snake(value: str) -> str:
    """Convert CamelCase to snake_case."""
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first).lower()


def snake_to_camel(value: str) -> str:
    """Convert snake_case operation method names to SDK operation names."""
    return "".join(part[:1].upper() + part[1:] for part in value.split("_") if part)


def operation_action(operation: str) -> str:
    """Return the leading action verb of an SDK operation name."""
    match = re.match(r"[A-Z][a-z0-9]*", operation)
    return match.group(0) if match else ""


def is_read_only_operation(operation: str) -> bool:
    """Return whether an SDK operation name is read-only by conservative verb rules."""
    return operation_action(operation) in READ_ONLY_ACTIONS


def service_token_from_package(package_name: str) -> str:
    """Return the SDK service token from a huaweicloudsdk* package name."""
    if package_name.startswith("huaweicloudsdk"):
        return package_name[len("huaweicloudsdk") :]
    return package_name


def find_service_packages(sdk_root: Path, service: str | None = None) -> list[dict[str, Any]]:
    """Find SDK service packages under a huaweicloud-sdk-python-v3 source tree."""
    if not sdk_root.exists():
        return []

    wanted = normalize_token(service or "")
    packages: list[dict[str, Any]] = []
    for distribution in sorted(sdk_root.glob("huaweicloud-sdk-*")):
        if not distribution.is_dir() or distribution.name == "huaweicloud-sdk-core":
            continue
        for package_path in sorted(distribution.iterdir()):
            if not package_path.is_dir() or not package_path.name.startswith("huaweicloudsdk"):
                continue
            if package_path.name in IGNORED_SDK_PACKAGES:
                continue
            service_key = service_token_from_package(package_path.name)
            if wanted and normalize_token(service_key) != wanted:
                continue
            packages.append(
                {
                    "distribution": distribution.name,
                    "package": package_path.name,
                    "service_key": service_key,
                    "path": package_path,
                    "source_kind": "source_tree",
                }
            )
    return packages


def installed_package_path(package_name: str) -> Path | None:
    """Return the filesystem path of an installed SDK package."""
    spec = importlib_util.find_spec(package_name)
    if not spec or not spec.submodule_search_locations:
        return None
    paths = list(spec.submodule_search_locations)
    return Path(paths[0]) if paths else None


def installed_distribution_name(package_name: str) -> str | None:
    """Return the distribution name that provides an installed top-level package."""
    distributions = importlib_metadata.packages_distributions()
    candidates = distributions.get(package_name)
    return candidates[0] if candidates else None


def find_installed_service_packages(service: str | None = None) -> list[dict[str, Any]]:
    """Find installed huaweicloudsdk* service packages."""
    wanted = normalize_token(service or "")
    package_names: set[str] = set()
    if wanted:
        package_names.add(f"huaweicloudsdk{wanted}")
    else:
        try:
            package_names.update(
                name
                for name in importlib_metadata.packages_distributions()
                if name.startswith("huaweicloudsdk") and name not in IGNORED_SDK_PACKAGES
            )
        except Exception:
            package_names = set()

    packages: list[dict[str, Any]] = []
    for package_name in sorted(package_names):
        if package_name in IGNORED_SDK_PACKAGES:
            continue
        package_path = installed_package_path(package_name)
        if not package_path:
            continue
        service_key = service_token_from_package(package_name)
        if wanted and normalize_token(service_key) != wanted:
            continue
        packages.append(
            {
                "distribution": installed_distribution_name(package_name) or "",
                "package": package_name,
                "service_key": service_key,
                "path": package_path,
                "source_kind": "installed_package",
            }
        )
    return packages


def find_sdk_packages(sdk_root: Path | None = None, service: str | None = None) -> list[dict[str, Any]]:
    """Find SDK service packages, preferring installed runtime packages."""
    packages = find_installed_service_packages(service)
    seen = {normalize_token(str(package["service_key"])) for package in packages}
    if sdk_root and sdk_root.exists():
        for package in find_service_packages(sdk_root, service):
            token = normalize_token(str(package["service_key"]))
            if token in seen:
                continue
            packages.append(package)
            seen.add(token)
    return packages


def version_dirs(package_path: Path) -> list[Path]:
    """Return SDK version directories under one service package."""
    return sorted(path for path in package_path.iterdir() if path.is_dir() and re.fullmatch(r"v\d+", path.name))


def client_file_for_version(version_dir: Path) -> Path | None:
    """Return the sync client file for one SDK version directory."""
    candidates = sorted(path for path in version_dir.glob("*_client.py") if not path.name.endswith("_async_client.py"))
    return candidates[0] if candidates else None


def region_file_for_version(version_dir: Path) -> Path | None:
    """Return the region metadata file for one SDK version directory."""
    region_dir = version_dir / "region"
    if not region_dir.exists():
        return None
    candidates = sorted(region_dir.glob("*_region.py"))
    return candidates[0] if candidates else None


def literal_class_attribute(path: Path, class_name: str, attribute: str, default: Any) -> Any:
    """Read a literal class attribute from a Python source file."""
    if not path.exists():
        return default
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return default
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if not isinstance(child, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == attribute for target in child.targets):
                continue
            try:
                return ast.literal_eval(child.value)
            except (ValueError, SyntaxError):
                return default
    return default


def request_model_path(version_dir: Path, operation: str) -> Path:
    """Return the generated SDK request model path for an operation."""
    return version_dir / "model" / f"{camel_to_snake(operation)}_request.py"


def parse_request_model(version_dir: Path, operation: str) -> dict[str, Any] | None:
    """Parse request model type and attribute metadata for one SDK operation."""
    path = request_model_path(version_dir, operation)
    if not path.exists():
        return None
    class_name = f"{operation}Request"
    openapi_types = literal_class_attribute(path, class_name, "openapi_types", {})
    attribute_map = literal_class_attribute(path, class_name, "attribute_map", {})
    sensitive_list = literal_class_attribute(path, class_name, "sensitive_list", [])
    params = []
    if isinstance(openapi_types, dict):
        for name, type_name in openapi_types.items():
            params.append(
                {
                    "name": str(name),
                    "type": str(type_name),
                    "serialized_name": str(attribute_map.get(name, name)) if isinstance(attribute_map, dict) else str(name),
                    "sensitive": str(name) in sensitive_list if isinstance(sensitive_list, list) else False,
                }
            )
    return {
        "class_name": class_name,
        "path": str(path),
        "openapi_types": openapi_types if isinstance(openapi_types, dict) else {},
        "attribute_map": attribute_map if isinstance(attribute_map, dict) else {},
        "sensitive_list": sensitive_list if isinstance(sensitive_list, list) else [],
        "params": params,
    }


def parse_client_operations(client_path: Path) -> dict[str, dict[str, Any]]:
    """Parse SDK operation http_info blocks from a generated client file."""
    if not client_path or not client_path.exists():
        return {}
    text = client_path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"^    def _([a-z0-9_]+)_http_info\(cls, request\):", text, flags=re.MULTILINE))
    operations: dict[str, dict[str, Any]] = {}
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]
        method_name = match.group(1)
        operation = snake_to_camel(method_name)
        method_match = re.search(r'"method":\s*"([^"]+)"', block)
        path_match = re.search(r'"resource_path":\s*"([^"]+)"', block)
        response_match = re.search(r'"response_type":\s*"([^"]+)"', block)
        query_params = re.findall(r"query_params\.append\(\('([^']+)'", block)
        header_params = re.findall(r"header_params\['([^']+)'\]", block)
        path_params = re.findall(r"\{([^{}]+)\}", path_match.group(1) if path_match else "")
        business_path_params = [
            normalize_param_name(param) for param in path_params if normalize_param_name(param) not in IGNORED_REQUIRED_PATH_PARAMS
        ]
        operations[operation] = {
            "name": operation,
            "method_name": method_name,
            "client_http_info_method": f"_{method_name}_http_info",
            "method": method_match.group(1) if method_match else None,
            "resource_path": path_match.group(1) if path_match else None,
            "request_type": f"{operation}Request",
            "response_type": response_match.group(1) if response_match else f"{operation}Response",
            "action": operation_action(operation),
            "read_only": is_read_only_operation(operation),
            "query_params": list(dict.fromkeys(query_params)),
            "header_params": sorted(set(header_params)),
            "path_params": list(dict.fromkeys(path_params)),
            "required_business_path_params": list(dict.fromkeys(business_path_params)),
            "has_body": "body = local_var_params['body']" in block or 'if "body" in local_var_params' in block,
        }
    return operations


def parse_regions(region_path: Path | None, limit: int | None = None) -> list[dict[str, str]]:
    """Parse static Region entries from an SDK region file."""
    if not region_path or not region_path.exists():
        return []
    text = region_path.read_text(encoding="utf-8")
    regions = [
        {"id": match.group(1), "endpoint": match.group(2)}
        for match in re.finditer(r'Region\(\s*"([^"]+)"\s*,\s*"([^"]+)"', text, flags=re.DOTALL)
    ]
    if limit is not None:
        return regions[:limit]
    return regions


def annotate_request_params(operation: dict[str, Any], request_model: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Merge request model fields with http_info placement hints."""
    if not request_model:
        return []
    query = {normalize_param_name(name) for name in operation.get("query_params", [])}
    path = {normalize_param_name(name) for name in operation.get("path_params", [])}
    result = []
    for param in request_model.get("params", []):
        normalized = normalize_param_name(str(param.get("serialized_name") or param.get("name") or ""))
        placement = "body"
        if normalized in query:
            placement = "query"
        elif normalized in path:
            placement = "path"
        result.append({**param, "normalized_name": normalized, "position": placement})
    return result


def package_summary(package: dict[str, Any], operation: str | None = None, max_regions: int | None = 20) -> dict[str, Any]:
    """Build a metadata summary for one SDK service package."""
    result: dict[str, Any] = {
        "distribution": package["distribution"],
        "package": package["package"],
        "service_key": package["service_key"],
        "path": str(package["path"]),
        "source_kind": package.get("source_kind", "unknown"),
        "versions": [],
    }
    for version_dir in version_dirs(package["path"]):
        client_path = client_file_for_version(version_dir)
        operations = parse_client_operations(client_path) if client_path else {}
        region_path = region_file_for_version(version_dir)
        version_entry: dict[str, Any] = {
            "version": version_dir.name,
            "client_file": str(client_path) if client_path else None,
            "client_module": f"{package['package']}.{version_dir.name}.{client_path.stem}" if client_path else None,
            "client_class": snake_to_camel(client_path.stem) if client_path else None,
            "operation_count": len(operations),
            "read_only_operation_count": sum(1 for item in operations.values() if item.get("read_only")),
            "region_file": str(region_path) if region_path else None,
            "regions": parse_regions(region_path, max_regions),
        }
        if operation:
            resolved = resolve_operation(operations, operation)
            if resolved:
                request_model = parse_request_model(version_dir, resolved["name"])
                version_entry["operation"] = {
                    **resolved,
                    "request_model": request_model,
                    "request_params": annotate_request_params(resolved, request_model),
                }
            else:
                version_entry["operation"] = None
        else:
            version_entry["operations_sample"] = sorted(operations)[:50]
            version_entry["read_only_operations_sample"] = sorted(name for name, item in operations.items() if item.get("read_only"))[:50]
        result["versions"].append(version_entry)
    return result


def resolve_operation(operations: dict[str, dict[str, Any]], operation: str) -> dict[str, Any] | None:
    """Resolve an operation by loose normalized name."""
    wanted = normalize_token(operation)
    for name, entry in operations.items():
        if normalize_token(name) == wanted:
            return entry
    return None


def inspect_sdk(
    sdk_root: Path | None = DEFAULT_SDK_ROOT,
    service: str | None = None,
    operation: str | None = None,
    max_regions: int | None = 20,
) -> dict[str, Any]:
    """Inspect SDK metadata from installed packages and optional source fallback."""
    source_root_exists = bool(sdk_root and sdk_root.exists())
    result: dict[str, Any] = {
        "success": True,
        "mode": "sdk_metadata",
        "role": "supplemental_to_hcloud",
        "package_discovery": "installed_packages_first",
        "sdk_source_root": str(sdk_root) if sdk_root else None,
        "sdk_source_root_exists": source_root_exists,
        "service": service.upper() if service else None,
        "operation": operation,
        "boundaries": {
            "primary_runtime": "hcloud",
            "sdk_default_use": "metadata_and_curated_read_only_supplement",
            "mutations": "do_not_execute_via_sdk_generic_runner",
        },
    }
    packages = find_sdk_packages(sdk_root, service)
    if service and not packages:
        result.update(
            {
                "success": False,
                "error": "SDK service package not found in installed packages or optional source root.",
                "available_service_sample": service_names(sdk_root)[:80],
                "install_hint": f"Install the service SDK package, for example: pip install huaweicloudsdk{service.lower()}",
            }
        )
        return result

    if not service:
        result["service_count"] = len(packages)
        result["services_sample"] = service_names(sdk_root)[:120]
        return result

    result["packages"] = [package_summary(package, operation, max_regions=max_regions) for package in packages]
    if operation:
        matches = [
            version
            for package in result["packages"]
            for version in package.get("versions", [])
            if version.get("operation")
        ]
        if not matches:
            result.update({"success": False, "error": "SDK operation not found for service."})
    return result


def service_names(sdk_root: Path | None = DEFAULT_SDK_ROOT) -> list[str]:
    """Return available SDK service names from installed packages and optional source."""
    return sorted({package["service_key"].upper() for package in find_sdk_packages(sdk_root)})


def sdk_hint_for_operation(service: str, operation: str, sdk_root: Path | None = DEFAULT_SDK_ROOT) -> dict[str, Any] | None:
    """Return a compact SDK evidence hint for hcloud planners."""
    result = inspect_sdk(sdk_root, service=service, operation=operation, max_regions=10)
    if not result.get("success"):
        return None
    candidates = []
    for package in result.get("packages", []):
        for version in package.get("versions", []):
            operation_entry = version.get("operation")
            if not operation_entry:
                continue
            candidates.append(
                {
                    "source": "huaweicloud-python-sdk",
                    "role": "supplemental_to_hcloud",
                    "source_kind": package.get("source_kind"),
                    "package": package.get("package"),
                    "version": version.get("version"),
                    "client_module": version.get("client_module"),
                    "client_class": version.get("client_class"),
                    "operation": operation_entry.get("name"),
                    "method": operation_entry.get("method"),
                    "resource_path": operation_entry.get("resource_path"),
                    "read_only": operation_entry.get("read_only"),
                    "query_params": operation_entry.get("query_params", []),
                    "required_business_path_params": operation_entry.get("required_business_path_params", []),
                    "request_types": (operation_entry.get("request_model") or {}).get("openapi_types", {}),
                    "regions_sample": version.get("regions", [])[:5],
                }
            )
    for candidate in candidates:
        if candidate.get("operation") == operation:
            return candidate
    return candidates[0] if candidates else None


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk-root",
        type=Path,
        default=DEFAULT_SDK_ROOT,
        help="Optional huaweicloud-sdk-python-v3 source tree used as maintenance/test fallback after installed packages.",
    )
    parser.add_argument("--service", help="SDK service name, for example ECS or VPC.")
    parser.add_argument("--operation", help="SDK operation name, for example ListFlavors.")
    parser.add_argument("--max-regions", type=int, default=20, help="Maximum static regions to include per SDK version.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    if args.operation and not args.service:
        parser.error("--operation requires --service.")
    if args.max_regions < 0:
        parser.error("--max-regions must be >= 0.")
    return args


def main() -> int:
    """Inspect SDK metadata and print JSON."""
    args = parse_args()
    result = inspect_sdk(
        args.sdk_root,
        service=args.service,
        operation=args.operation,
        max_regions=args.max_regions,
    )
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
