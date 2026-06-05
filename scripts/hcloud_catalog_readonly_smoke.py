#!/usr/bin/env python3
"""Plan or run metadata-backed read-only smoke checks for generated catalog services."""

from __future__ import annotations

import argparse
from types import SimpleNamespace
from typing import Any

import hcloud_common
import hcloud_resource_discovery


DEFAULT_SERVICES = ("UCS", "RFS", "WAF", "DCS")


def classify_execution(execution: dict[str, Any]) -> dict[str, Any]:
    """Classify one hcloud_safe_exec result into a review-friendly bucket."""
    if execution.get("success"):
        return {"result_bucket": "command_shape_ok", "error_category": None, "error_source": None}

    details = execution.get("error_details") if isinstance(execution.get("error_details"), dict) else {}
    category = details.get("category")
    message = " ".join(
        str(value or "")
        for value in (
            details.get("message"),
            details.get("cloud_message"),
            execution.get("stderr"),
            execution.get("stdout"),
        )
    ).lower()
    if category in {"credential", "permission"}:
        bucket = "auth_or_permission"
    elif category in {"region_or_endpoint", "project"}:
        bucket = "region_or_endpoint"
    elif category == "parameter":
        bucket = "missing_required_param" if "required" in message or "missing" in message else "command_shape_error"
    elif category == "network":
        bucket = "network"
    elif "not subscribed" in message or "not enabled" in message or "not open" in message:
        bucket = "service_not_subscribed"
    elif category in {"metadata", "local_environment"}:
        bucket = "command_shape_error"
    else:
        bucket = "unknown_cloud_error"
    return {
        "result_bucket": bucket,
        "error_category": category,
        "error_source": details.get("source"),
    }


def discovery_args(args: argparse.Namespace, service: str) -> SimpleNamespace:
    """Build discovery arguments for one metadata-backed smoke service."""
    return SimpleNamespace(
        service=service,
        operation=None,
        region=args.region,
        project_id=args.project_id,
        profile=args.profile,
        limit=args.limit,
        catalog_max_operations=args.catalog_max_operations,
        execute=False,
    )


def summarize_plan(service: str, plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return matrix rows for a planned discovery result."""
    if not plan.get("success"):
        return [
            {
                "service": service,
                "operation": None,
                "mode": "plan",
                "metadata_backed": plan.get("metadata_backed", False),
                "result_bucket": "command_shape_error",
                "error": plan.get("error"),
                "execution_success": None,
            }
        ]
    rows = []
    for item in plan.get("commands", []):
        rows.append(
            {
                "service": item.get("service", service),
                "operation": item.get("operation"),
                "mode": "plan",
                "metadata_backed": item.get("metadata_backed", False),
                "result_bucket": "planned",
                "command": item.get("command"),
                "execution_success": None,
                "catalog_operation_summary": item.get("catalog_operation_summary"),
            }
        )
    return rows


def summarize_execution(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return matrix rows for an executed discovery result."""
    rows = []
    command_by_operation = {item.get("operation"): item for item in plan.get("commands", [])}
    for result in plan.get("results", []):
        execution = result.get("result", {}) if isinstance(result, dict) else {}
        classification = classify_execution(execution if isinstance(execution, dict) else {})
        operation = result.get("operation")
        command_item = command_by_operation.get(operation, {})
        rows.append(
            {
                "service": result.get("service"),
                "operation": operation,
                "mode": "execute",
                "metadata_backed": command_item.get("metadata_backed", False),
                "result_bucket": classification["result_bucket"],
                "error_category": classification["error_category"],
                "error_source": classification["error_source"],
                "execution_success": bool(execution.get("success")) if isinstance(execution, dict) else False,
                "command": command_item.get("command"),
                "catalog_operation_summary": command_item.get("catalog_operation_summary"),
            }
        )
    return rows


def build_smoke(args: argparse.Namespace) -> dict[str, Any]:
    """Build or run a metadata-backed read-only smoke matrix."""
    services = args.service or list(DEFAULT_SERVICES)
    checks = []
    matrix = []
    for service in services:
        plan = hcloud_resource_discovery.build_plan(discovery_args(args, service))
        check = {
            "service": service,
            "success": bool(plan.get("success")),
            "plan": plan,
        }
        if args.execute and plan.get("success"):
            executed = hcloud_resource_discovery.execute_plan(plan, args.timeout)
            check["execution"] = executed
            check["success"] = bool(executed.get("success"))
            matrix.extend(summarize_execution(executed))
        else:
            matrix.extend(summarize_plan(service, plan))
        checks.append(check)

    bucket_counts: dict[str, int] = {}
    for row in matrix:
        bucket = str(row.get("result_bucket") or "unknown")
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    return {
        "success": all(check["success"] for check in checks) if args.strict else True,
        "mode": "execute" if args.execute else "plan",
        "service_count": len(services),
        "operation_count": len(matrix),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "checks": checks,
        "matrix": matrix,
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", action="append", help="Catalog service to smoke. Can be repeated.")
    parser.add_argument("--region", help="Explicit cli-region for generated commands.")
    parser.add_argument("--project-id", help="Optional project_id for generated commands.")
    parser.add_argument("--profile", help="Optional cli-profile for generated commands.")
    parser.add_argument("--limit", type=int, default=5, help="Optional limit for operations that support it.")
    parser.add_argument("--catalog-max-operations", type=int, default=2, help="Max discovery operations per service.")
    parser.add_argument("--execute", action="store_true", help="Execute generated read-only commands.")
    parser.add_argument("--strict", action="store_true", help="Return failure when any plan or execution fails.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per executed command.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be greater than 0.")
    if args.catalog_max_operations < 1:
        parser.error("--catalog-max-operations must be greater than 0.")
    if args.timeout < 1:
        parser.error("--timeout must be greater than 0.")
    return args


def main() -> int:
    """Build or run metadata-backed read-only smoke checks."""
    args = parse_args()
    result = build_smoke(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
