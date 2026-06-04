#!/usr/bin/env python3
"""Build or run list-only discovery commands from the service registry."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from hcloud_meta_lookup import collect_template_dirs, load_operation_detail, normalize_token


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "references" / "service-registry.json"
CURATED_LIMIT_OPERATIONS = {
    ("ECS", "ListCloudServers"),
    ("ECS", "ListServersDetails"),
}


def normalize_operation(value: str) -> str:
    """Return a loose operation key for case-insensitive matching."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Return the machine-readable service registry."""
    return json.loads(path.read_text(encoding="utf-8"))


def operation_param_names(service: str, operation: str) -> set[str]:
    """Return known hcloud parameter names for an operation from local metadata."""
    meta_repo = Path.home() / ".hcloud" / "metaRepo"
    template_dir = collect_template_dirs(meta_repo).get(normalize_token(service))
    detail = load_operation_detail(template_dir, operation)
    if not isinstance(detail, dict):
        if (service.upper(), operation) in CURATED_LIMIT_OPERATIONS:
            return {"limit"}
        return set()

    names: set[str] = set()
    for param in detail.get("params", []):
        for name in param.get("name", []):
            names.add(str(name).lower())
    return names


def resolve_cli_region(args: argparse.Namespace, service_entry: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve the cli-region for services with curated supported regions."""
    requested_region = args.region
    supported_regions = service_entry.get("supported_cli_regions", [])
    preferred_region = service_entry.get("preferred_cli_region")
    if not supported_regions:
        return requested_region, None

    if requested_region in supported_regions:
        return requested_region, None

    resolved_region = preferred_region or supported_regions[0]
    reason = "requested_region_not_supported" if requested_region else "explicit_supported_region_required"
    return resolved_region, {
        "requested_region": requested_region,
        "resolved_region": resolved_region,
        "supported_regions": supported_regions,
        "reason": reason,
    }


def resolve_query_operation(operations: list[str], requested_operation: str) -> str | None:
    """Resolve a requested operation against registered list-only operations."""
    if requested_operation in operations:
        return requested_operation
    normalized_requested = normalize_operation(requested_operation)
    for operation in operations:
        if normalize_operation(operation) == normalized_requested:
            return operation
    return None


def build_safe_exec_command(
    args: argparse.Namespace,
    service: str,
    operation: str,
    param_names: set[str],
    cli_region: str | None,
) -> tuple[list[str], list[str]]:
    """Build a JSON-friendly safe_exec command for one list-only operation."""
    command = [
        "python3",
        "scripts/hcloud_safe_exec.py",
        "--service",
        service,
        "--operation",
        operation,
        "--arg=--cli-output=json",
        "--expect-json",
    ]
    if args.profile:
        command.append(f"--arg=--cli-profile={args.profile}")
    if cli_region:
        command.append(f"--arg=--cli-region={cli_region}")
    if args.project_id:
        command.append(f"--arg=--project_id={args.project_id}")
    omitted_args: list[str] = []
    if args.limit is not None:
        if "limit" in param_names:
            command.append(f"--arg=--limit={args.limit}")
        else:
            omitted_args.append("--limit")
    return command, omitted_args


def build_command_item(args: argparse.Namespace, service: str, operation: str, service_entry: dict[str, Any]) -> dict[str, Any]:
    """Build one discovery command item with metadata-driven optional arguments."""
    cli_region, region_resolution = resolve_cli_region(args, service_entry)
    command, omitted_args = build_safe_exec_command(args, service, operation, operation_param_names(service, operation), cli_region)
    item: dict[str, Any] = {
        "service": service,
        "operation": operation,
        "command": command,
    }
    if region_resolution:
        item["region_resolution"] = region_resolution
    if omitted_args:
        item["omitted_args"] = omitted_args
        item["omitted_reason"] = "Operation metadata does not list these parameters."
    return item


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """Build list-only discovery commands without mutating cloud resources."""
    registry = load_registry()
    service = args.service.upper()
    service_entry = registry["services"].get(service)
    if service_entry is None:
        return {
            "success": False,
            "service": service,
            "error": f"Service is not registered: {service}",
            "available_services": sorted(registry["services"]),
        }
    query_runner = service_entry.get("query_runner")
    if query_runner and query_runner != "scripts/hcloud_resource_discovery.py":
        return {
            "success": False,
            "service": service,
            "error": "Service uses a dedicated query runner and is not compatible with generic discovery.",
            "query_runner": query_runner,
            "available_query_operations": service_entry.get("query_operations", []),
        }

    operations = service_entry.get("query_operations", [])
    if args.operation:
        operation = resolve_query_operation(operations, args.operation)
        if operation is None:
            return {
                "success": False,
                "service": service,
                "operation": args.operation,
                "error": f"Operation is not registered as list-only query for {service}: {args.operation}",
                "available_query_operations": operations,
            }
        operations = [operation]

    commands = [build_command_item(args, service, operation, service_entry) for operation in operations]
    result = {
        "success": True,
        "mode": "execute" if args.execute else "plan",
        "service": service,
        "coverage": service_entry.get("coverage"),
        "known_limits": service_entry.get("known_limits", []),
        "playbooks": service_entry.get("playbooks", []),
        "commands": commands,
    }
    if args.operation and operations and args.operation != operations[0]:
        result["requested_operation"] = args.operation
    return result


def execute_plan(plan: dict[str, Any], timeout: int) -> dict[str, Any]:
    """Run discovery commands and attach structured results."""
    results = []
    for item in plan.get("commands", []):
        completed = subprocess.run(
            item["command"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError:
            result = {
                "success": False,
                "return_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "parsed_json": None,
                "parsed_json_error": "hcloud_safe_exec.py did not return valid JSON.",
            }
        results.append(
            {
                "service": item["service"],
                "operation": item["operation"],
                "result": result,
            }
        )
    plan = dict(plan)
    plan["results"] = results
    plan["success"] = all(item["result"].get("success") for item in results)
    return plan


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, help="Registered service name, for example ECS, VPC, IMS, KPS, IAM.")
    parser.add_argument("--operation", help="Optional registered list-only operation to run.")
    parser.add_argument("--region", help="Explicit cli-region for generated commands.")
    parser.add_argument("--project-id", help="Optional project_id for generated commands.")
    parser.add_argument("--profile", help="Optional cli-profile for generated commands.")
    parser.add_argument("--limit", type=int, help="Optional limit parameter for list operations that support it.")
    parser.add_argument("--execute", action="store_true", help="Run the generated safe_exec commands.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per executed command.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be greater than 0.")
    if args.timeout < 1:
        parser.error("--timeout must be greater than 0.")
    return args


def main() -> int:
    """Build or run list-only discovery commands."""
    args = parse_args()
    result = build_plan(args)
    if result["success"] and args.execute:
        result = execute_plan(result, args.timeout)
    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
