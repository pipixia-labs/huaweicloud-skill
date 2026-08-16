#!/usr/bin/env python3
"""Poll a registered Huawei read operation until an async status converges."""

from __future__ import annotations

import argparse
import time
from types import SimpleNamespace
from typing import Any

import hcloud_change_state
import hcloud_common
import hcloud_resource_query

DEFAULT_SUCCESS_STATUSES = ["SUCCESS", "SUCCEEDED", "COMPLETE", "COMPLETED"]
DEFAULT_FAILURE_STATUSES = [
    "FAIL",
    "FAILED",
    "ERROR",
    "CANCELLED",
    "CANCELED",
    "ROLLBACK",
    "ROLLED_BACK",
]
DEFAULT_STATUS_PATHS = ["status", "job.status", "data.status", "result.status"]


def normalize_status(value: Any) -> str | None:
    """Return a normalized uppercase status string when one is present."""
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text.upper() if text else None


def extract_path(payload: Any, path: str) -> Any:
    """Resolve one bounded dot path through JSON objects and list indexes."""
    current = payload
    parts = [part for part in str(path).split(".") if part]
    if not parts or len(parts) > 32:
        return None
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def extract_status(payload: Any, status_paths: list[str]) -> tuple[str | None, str | None]:
    """Return the first status found at an explicitly allowed JSON path."""
    for path in status_paths:
        status = normalize_status(extract_path(payload, path))
        if status:
            return status, path
    return None, None


def query_args(args: argparse.Namespace) -> SimpleNamespace:
    """Build the namespace for the registered read-query boundary."""
    return SimpleNamespace(
        service=args.service,
        operation=args.operation,
        param=args.param,
        arg=args.arg,
        region=args.region,
        project_id=args.project_id,
        profile=args.profile,
        execute=True,
        timeout=args.command_timeout,
        allow_sensitive_read=False,
    )


def wait_for_job(args: argparse.Namespace) -> dict[str, Any]:
    """Poll a registered read operation until success, failure, or timeout."""
    success_statuses = {normalize_status(value) for value in args.success_status}
    failure_statuses = {normalize_status(value) for value in args.failure_status}
    status_paths = args.status_path or DEFAULT_STATUS_PATHS
    started_at = time.time()
    deadline = started_at + args.timeout
    attempts: list[dict[str, Any]] = []
    consecutive_failures = 0

    while True:
        plan = hcloud_resource_query.build_plan(query_args(args))
        execution = plan.get("result") if isinstance(plan, dict) else None
        payload = execution.get("parsed_json") if isinstance(execution, dict) else None
        status, status_path = extract_status(payload, status_paths)
        if plan.get("success"):
            consecutive_failures = 0
        else:
            consecutive_failures += 1
        classification = (
            "success"
            if status in success_statuses
            else "failure"
            if status in failure_statuses
            else "running"
            if status is not None
            else "unknown"
        )
        attempts.append(
            {
                "attempt": len(attempts) + 1,
                "query_success": bool(plan.get("success")),
                "status": status,
                "status_path": status_path,
                "classification": classification,
                "error": plan.get("error"),
            }
        )
        if classification in {"success", "failure"}:
            return {
                "success": classification == "success",
                "classification": classification,
                "service": args.service.upper(),
                "operation": args.operation,
                "attempts": attempts,
                "final_status": status,
                "final_status_path": status_path,
                "final_identifiers": hcloud_change_state.extract_identifiers(payload),
                "duration_seconds": round(time.time() - started_at, 3),
            }
        if consecutive_failures >= args.max_command_failures:
            return {
                "success": False,
                "classification": "query_failure",
                "service": args.service.upper(),
                "operation": args.operation,
                "attempts": attempts,
                "final_status": status,
                "duration_seconds": round(time.time() - started_at, 3),
            }
        if time.time() >= deadline:
            return {
                "success": False,
                "classification": "timeout",
                "service": args.service.upper(),
                "operation": args.operation,
                "attempts": attempts,
                "final_status": status,
                "duration_seconds": round(time.time() - started_at, 3),
            }
        time.sleep(args.interval)


def parse_args() -> argparse.Namespace:
    """Parse generic async convergence arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--param", action="append", default=[])
    parser.add_argument("--arg", action="append", default=[])
    parser.add_argument("--region")
    parser.add_argument("--project-id")
    parser.add_argument("--profile")
    parser.add_argument("--status-path", action="append", default=[])
    parser.add_argument("--success-status", action="append", default=[])
    parser.add_argument("--failure-status", action="append", default=[])
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--command-timeout", type=int, default=120)
    parser.add_argument("--max-command-failures", type=int, default=3)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if not args.success_status:
        args.success_status = list(DEFAULT_SUCCESS_STATUSES)
    if not args.failure_status:
        args.failure_status = list(DEFAULT_FAILURE_STATUSES)
    if args.interval <= 0 or args.timeout <= 0 or args.command_timeout <= 0:
        parser.error("polling intervals and timeouts must be greater than 0")
    if args.max_command_failures < 1:
        parser.error("--max-command-failures must be at least 1")
    return args


def main() -> int:
    """Run generic async convergence and emit structured JSON."""
    args = parse_args()
    result = wait_for_job(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
