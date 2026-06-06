#!/usr/bin/env python3
"""Plan or run metadata-backed read-only smoke checks for generated catalog services."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import hcloud_common
import hcloud_resource_discovery


DEFAULT_SERVICES = ("UCS", "RFS", "WAF", "DCS")
SMOKE_RECORD_SCHEMA_VERSION = 1


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp for persisted smoke evidence."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def evidence_summary(row: dict[str, Any]) -> str:
    """Return a compact human-readable summary for one smoke matrix row."""
    bucket = row.get("result_bucket")
    if bucket == "planned":
        return "Generated a metadata-backed read-only discovery command; live execution was not requested."
    if bucket == "command_shape_ok":
        return "Read-only command executed successfully through hcloud_safe_exec."
    if bucket == "auth_or_permission":
        return "Read-only command shape reached hcloud, but auth or permission blocked the request."
    if bucket == "service_not_subscribed":
        return "Read-only command shape reached hcloud, but the account or project does not have this service enabled."
    if bucket == "region_or_endpoint":
        return "Read-only command shape reached hcloud, but region, project, or endpoint context is not valid for this service."
    if bucket == "missing_required_param":
        return "The selected discovery operation still required a business parameter; treat this as a catalog command-shape issue."
    if bucket == "command_shape_error":
        return "The generated command or local hcloud metadata path failed before proving a valid service request."
    if bucket == "network":
        return "The read-only request could not complete because of network transport failure."
    return "The read-only request failed with an unclassified cloud or local error."


def parsed_json_shape(value: Any) -> dict[str, Any]:
    """Return non-sensitive shape information about a parsed JSON response."""
    if isinstance(value, dict):
        keys = sorted(str(key) for key in value.keys())
        return {"type": "dict", "top_level_key_count": len(keys), "top_level_keys_sample": keys[:10]}
    if isinstance(value, list):
        return {"type": "list", "item_count": len(value)}
    if value is None:
        return {"type": "null"}
    return {"type": type(value).__name__}


def discovery_args(args: argparse.Namespace, service: str, operation: str | None = None) -> SimpleNamespace:
    """Build discovery arguments for one metadata-backed smoke service."""
    return SimpleNamespace(
        service=service,
        operation=operation,
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
        rows[-1]["evidence_summary"] = evidence_summary(rows[-1])
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
                "return_code": execution.get("return_code") if isinstance(execution, dict) else None,
                "command": command_item.get("command"),
                "catalog_operation_summary": command_item.get("catalog_operation_summary"),
                "parsed_json_shape": parsed_json_shape(execution.get("parsed_json")) if isinstance(execution, dict) else None,
            }
        )
        rows[-1]["evidence_summary"] = evidence_summary(rows[-1])
    return rows


def bucket_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Return sorted bucket counts for matrix rows."""
    counts: dict[str, int] = {}
    for row in rows:
        bucket = str(row.get("result_bucket") or "unknown")
        counts[bucket] = counts.get(bucket, 0) + 1
    return dict(sorted(counts.items()))


def execution_summary(plan: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return an execution summary without raw command output or response bodies."""
    return {
        "success": bool(plan.get("success")),
        "result_count": len(rows),
        "bucket_counts": bucket_counts(rows),
    }


def build_smoke(args: argparse.Namespace) -> dict[str, Any]:
    """Build or run a metadata-backed read-only smoke matrix."""
    services = args.service or list(DEFAULT_SERVICES)
    operations = operation_filters(args, services)
    checks = []
    matrix = []
    for service, operation in zip(services, operations):
        plan = hcloud_resource_discovery.build_plan(discovery_args(args, service, operation))
        check = {
            "service": service,
            "requested_operation": operation,
            "success": bool(plan.get("success")),
            "plan": plan,
        }
        if args.execute and plan.get("success"):
            executed = hcloud_resource_discovery.execute_plan(plan, args.timeout)
            rows = summarize_execution(executed)
            if getattr(args, "include_raw_execution", False):
                check["execution"] = executed
            check["execution_summary"] = execution_summary(executed, rows)
            check["success"] = bool(executed.get("success"))
            matrix.extend(rows)
        else:
            matrix.extend(summarize_plan(service, plan))
        checks.append(check)

    return {
        "success": all(check["success"] for check in checks) if args.strict else True,
        "mode": "execute" if args.execute else "plan",
        "service_count": len(services),
        "operation_count": len(matrix),
        "bucket_counts": bucket_counts(matrix),
        "checks": checks,
        "matrix": matrix,
    }


def operation_filters(args: argparse.Namespace, services: list[str]) -> list[str | None]:
    """Return per-service operation filters for smoke planning."""
    operations = getattr(args, "operation", None) or []
    if not operations:
        return [None for _ in services]
    if len(operations) == 1:
        return [str(operations[0]) for _ in services]
    if len(operations) != len(services):
        raise ValueError("--operation must be provided once or exactly once per --service.")
    return [str(operation) for operation in operations]


def build_smoke_record(args: argparse.Namespace, result: dict[str, Any]) -> dict[str, Any]:
    """Build a sanitized smoke evidence record safe to persist."""
    return {
        "schema_version": SMOKE_RECORD_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "tool": "scripts/hcloud_catalog_readonly_smoke.py",
        "mode": result.get("mode"),
        "success": result.get("success"),
        "service_count": result.get("service_count"),
        "operation_count": result.get("operation_count"),
        "bucket_counts": result.get("bucket_counts", {}),
        "context": {
            "region": args.region,
            "project_id_provided": bool(args.project_id),
            "profile_provided": bool(args.profile),
            "limit": args.limit,
            "catalog_max_operations": args.catalog_max_operations,
            "operations": args.operation or [],
            "strict": bool(args.strict),
        },
        "services": args.service or list(DEFAULT_SERVICES),
        "matrix": sanitize_matrix(result.get("matrix", [])),
        "confidence_suggestions": build_confidence_suggestions(result),
        "notes": [
            "This record intentionally omits raw stdout, stderr, and parsed response bodies.",
            "A command_shape_ok bucket means the read-only command executed successfully; it does not promote a service to curated coverage by itself.",
        ],
    }


def sanitize_command(command: Any) -> Any:
    """Return a command with local account context placeholders."""
    if not isinstance(command, list):
        return command
    sanitized = []
    for item in command:
        if isinstance(item, str) and item.startswith("--arg=--project_id="):
            sanitized.append("--arg=--project_id=<project-id>")
        elif isinstance(item, str) and item.startswith("--arg=--cli-profile="):
            sanitized.append("--arg=--cli-profile=<profile>")
        else:
            sanitized.append(item)
    return sanitized


def sanitize_matrix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return matrix rows safe for checked-in smoke evidence records."""
    sanitized = []
    for row in rows:
        item = dict(row)
        item["command"] = sanitize_command(item.get("command"))
        sanitized.append(item)
    return sanitized


def build_confidence_suggestions(result: dict[str, Any]) -> dict[str, Any]:
    """Return a confidence sidecar patch for successful live read-only smoke rows."""
    services: dict[str, Any] = {}
    for row in result.get("matrix", []):
        if row.get("mode") != "execute" or row.get("result_bucket") != "command_shape_ok":
            continue
        service = str(row.get("service") or "")
        operation = str(row.get("operation") or "")
        if not service or not operation:
            continue
        service_entry = services.setdefault(service, {"confidence": "catalog-derived", "operations": {}})
        service_entry["operations"][operation] = {
            "confidence": "live-read-smoked",
            "last_smoke": {
                "result_bucket": row.get("result_bucket"),
                "evidence_summary": row.get("evidence_summary"),
            },
        }
    return {"schema_version": 1, "services": services}


def write_json(path: Path, value: dict[str, Any], pretty: bool = True) -> None:
    """Write a JSON document to disk using repository-standard encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2 if pretty else None)
    path.write_text(f"{text}\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", action="append", help="Catalog service to smoke. Can be repeated.")
    parser.add_argument(
        "--operation",
        action="append",
        help="Optional operation filter. Provide once for all services or once per --service.",
    )
    parser.add_argument("--region", help="Explicit cli-region for generated commands.")
    parser.add_argument("--project-id", help="Optional project_id for generated commands.")
    parser.add_argument("--profile", help="Optional cli-profile for generated commands.")
    parser.add_argument("--limit", type=int, default=5, help="Optional limit for operations that support it.")
    parser.add_argument("--catalog-max-operations", type=int, default=2, help="Max discovery operations per service.")
    parser.add_argument("--execute", action="store_true", help="Execute generated read-only commands.")
    parser.add_argument("--strict", action="store_true", help="Return failure when any plan or execution fails.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per executed command.")
    parser.add_argument("--output", help="Write a sanitized smoke evidence record to this JSON path.")
    parser.add_argument(
        "--confidence-output",
        help="Write live-read-smoked confidence suggestions for successful executed operations to this JSON path.",
    )
    parser.add_argument(
        "--include-raw-execution",
        action="store_true",
        help="Include raw safe_exec execution results in stdout for local debugging. Do not use this for persisted evidence.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be greater than 0.")
    if args.catalog_max_operations < 1:
        parser.error("--catalog-max-operations must be greater than 0.")
    if args.timeout < 1:
        parser.error("--timeout must be greater than 0.")
    service_count = len(args.service or [])
    operation_count = len(args.operation or [])
    if operation_count > 1 and service_count and operation_count != service_count:
        parser.error("--operation must be provided once or exactly once per --service.")
    return args


def main() -> int:
    """Build or run metadata-backed read-only smoke checks."""
    args = parse_args()
    result = build_smoke(args)
    record = build_smoke_record(args, result)
    if args.output:
        write_json(Path(args.output), record)
        result["output"] = args.output
    if args.confidence_output:
        write_json(Path(args.confidence_output), record["confidence_suggestions"])
        result["confidence_output"] = args.confidence_output
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
