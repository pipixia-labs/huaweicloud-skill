#!/usr/bin/env python3
"""Persist exact resources owned by one Huawei Cloud change workflow."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import hcloud_common

SCHEMA_VERSION = 1
MAX_RESOURCES = 256
MAX_IDENTIFIERS_PER_RESOURCE = 256
RESOURCE_STATES = frozenset(
    {
        "planned",
        "submit_unknown",
        "submitted",
        "verification_failed",
        "verified",
        "cleanup_planned",
        "cleanup_failed",
        "deleted",
    }
)
ROLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SERVICE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
PARAMETER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def utc_timestamp() -> str:
    """Return a stable ISO-8601 UTC timestamp for ledger records."""
    return datetime.now(UTC).isoformat()


def _empty_ledger(workflow_id: str) -> dict[str, Any]:
    now = utc_timestamp()
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "created_at": now,
        "updated_at": now,
        "resources": {},
    }


def _validate_workflow_id(workflow_id: str) -> str:
    value = str(workflow_id or "").strip()
    if not ROLE_RE.fullmatch(value):
        raise ValueError("workflow_id must be a bounded stable identifier")
    return value


def _validate_role(role: str) -> str:
    value = str(role or "").strip()
    if not ROLE_RE.fullmatch(value):
        raise ValueError("resource role must be a bounded stable identifier")
    return value


def _bounded_text(value: str | None, *, label: str, maximum: int = 256) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or len(normalized) > maximum or "\x00" in normalized:
        raise ValueError(f"{label} must be non-empty and at most {maximum} characters")
    return normalized


def _unique_text_values(values: Iterable[str] | None, *, label: str) -> list[str]:
    result: list[str] = []
    for raw_value in values or ():
        value = _bounded_text(raw_value, label=label, maximum=512)
        if value is not None and value not in result:
            result.append(value)
        if len(result) > MAX_IDENTIFIERS_PER_RESOURCE:
            raise ValueError(f"{label} exceeds the resource ledger limit")
    return result


def load_ledger(path: Path, *, workflow_id: str) -> dict[str, Any]:
    """Load and validate one workflow ledger or return a new empty document."""
    workflow_id = _validate_workflow_id(workflow_id)
    if not path.exists():
        return _empty_ledger(workflow_id)
    ledger = hcloud_common.load_json(path)
    if not isinstance(ledger, dict):
        raise ValueError("Resource ledger must be a JSON object")
    if ledger.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported resource ledger schema_version: {ledger.get('schema_version')!r}")
    if ledger.get("workflow_id") != workflow_id:
        raise ValueError("Resource ledger belongs to a different workflow_id; use a separate ledger file")
    resources = ledger.get("resources")
    if not isinstance(resources, dict) or len(resources) > MAX_RESOURCES:
        raise ValueError("Resource ledger resources must be a bounded JSON object")
    for role, resource in resources.items():
        if not ROLE_RE.fullmatch(str(role)) or not isinstance(resource, dict):
            raise ValueError("Resource ledger contains an invalid resource entry")
        if resource.get("state") not in RESOURCE_STATES:
            raise ValueError("Resource ledger contains an invalid resource state")
    return ledger


def save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    """Atomically persist a validated workflow ledger."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger["updated_at"] = utc_timestamp()
    payload = json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def _ledger_lock(path: Path):
    """Serialize same-workflow ledger mutations across local processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _mutate[T](
    path: Path,
    *,
    workflow_id: str,
    callback: Callable[[dict[str, Any]], T],
) -> T:
    with _ledger_lock(path):
        ledger = load_ledger(path, workflow_id=workflow_id)
        result = callback(ledger)
        save_ledger(path, ledger)
        return result


def register_resource(
    path: Path,
    *,
    workflow_id: str,
    role: str,
    service: str,
    region: str,
    project_id: str | None = None,
    expected_count: int = 1,
    dependencies: Sequence[str] = (),
    request_fingerprint: str | None = None,
    cleanup_operation: str | None = None,
    identifier_parameter: str | None = None,
) -> dict[str, Any]:
    """Register one logical resource role owned by the current workflow.

    Repeating the exact declaration is idempotent. Reusing a role for a
    different service, region, dependency set, request, or cleanup contract is
    rejected so a resumed task cannot accidentally take ownership of another
    resource.
    """
    workflow_id = _validate_workflow_id(workflow_id)
    role = _validate_role(role)
    normalized_service = str(service or "").strip().upper()
    if not SERVICE_RE.fullmatch(normalized_service):
        raise ValueError("service must be a bounded Huawei service identifier")
    normalized_region = _bounded_text(region, label="region", maximum=128)
    if expected_count < 1 or expected_count > MAX_IDENTIFIERS_PER_RESOURCE:
        raise ValueError("expected_count is outside the resource ledger limit")
    normalized_dependencies = sorted({_validate_role(value) for value in dependencies if value != role})
    normalized_cleanup = _bounded_text(
        cleanup_operation,
        label="cleanup_operation",
        maximum=128,
    )
    normalized_parameter = _bounded_text(
        identifier_parameter,
        label="identifier_parameter",
        maximum=64,
    )
    if bool(normalized_cleanup) != bool(normalized_parameter):
        raise ValueError("cleanup_operation and identifier_parameter must be declared together")
    if normalized_parameter and not PARAMETER_RE.fullmatch(normalized_parameter):
        raise ValueError("identifier_parameter is invalid")
    normalized_fingerprint = _bounded_text(
        request_fingerprint,
        label="request_fingerprint",
        maximum=128,
    )
    declaration = {
        "role": role,
        "service": normalized_service,
        "region": normalized_region,
        "project_id": _bounded_text(project_id, label="project_id", maximum=128),
        "expected_count": int(expected_count),
        "dependencies": normalized_dependencies,
        "request_fingerprint": normalized_fingerprint,
        "cleanup_operation": normalized_cleanup,
        "identifier_parameter": normalized_parameter,
    }

    def mutate(ledger: dict[str, Any]) -> dict[str, Any]:
        resources = ledger["resources"]
        existing = resources.get(role)
        if existing is not None:
            if any(existing.get(key) != value for key, value in declaration.items()):
                raise ValueError("resource role is already bound to a different resource declaration")
            return dict(existing)
        if len(resources) >= MAX_RESOURCES:
            raise ValueError("resource ledger exceeds its resource limit")
        now = utc_timestamp()
        resource = {
            **declaration,
            "state": "planned",
            "identifiers": [],
            "job_ids": [],
            "created_at": now,
            "updated_at": now,
        }
        resources[role] = resource
        return dict(resource)

    return _mutate(path, workflow_id=workflow_id, callback=mutate)


def _resource(ledger: dict[str, Any], role: str) -> dict[str, Any]:
    resource = ledger["resources"].get(_validate_role(role))
    if not isinstance(resource, dict):
        raise ValueError(f"Unknown resource role: {role}")
    return resource


def record_submission(
    path: Path,
    *,
    workflow_id: str,
    role: str,
    accepted: bool | None,
    identifiers: Iterable[str] | None = None,
    job_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Record a submit receipt without treating local failure as safe retry."""
    normalized_identifiers = _unique_text_values(
        identifiers,
        label="resource identifier",
    )
    normalized_job_ids = _unique_text_values(job_ids, label="job identifier")

    def mutate(ledger: dict[str, Any]) -> dict[str, Any]:
        resource = _resource(ledger, role)
        resource["state"] = "submitted" if accepted is True else "submit_unknown"
        resource["identifiers"] = _unique_text_values(
            [*resource.get("identifiers", []), *normalized_identifiers],
            label="resource identifier",
        )
        resource["job_ids"] = _unique_text_values(
            [*resource.get("job_ids", []), *normalized_job_ids],
            label="job identifier",
        )
        resource["submission"] = {
            "accepted": accepted,
            "recorded_at": utc_timestamp(),
        }
        resource["updated_at"] = utc_timestamp()
        return dict(resource)

    return _mutate(path, workflow_id=workflow_id, callback=mutate)


def record_verification(
    path: Path,
    *,
    workflow_id: str,
    role: str,
    success: bool,
    identifiers: Iterable[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record exact resource convergence and enforce the declared count."""
    normalized_identifiers = _unique_text_values(
        identifiers,
        label="resource identifier",
    )

    def mutate(ledger: dict[str, Any]) -> dict[str, Any]:
        resource = _resource(ledger, role)
        if normalized_identifiers:
            resource["identifiers"] = _unique_text_values(
                [*resource.get("identifiers", []), *normalized_identifiers],
                label="resource identifier",
            )
        expected_count = int(resource["expected_count"])
        observed_count = len(resource.get("identifiers", []))
        count_matches = observed_count == expected_count
        verified = bool(success) and count_matches
        verification: dict[str, Any] = {
            "success": verified,
            "observed_success": bool(success),
            "expected_count": expected_count,
            "observed_count": observed_count,
            "recorded_at": utc_timestamp(),
        }
        if success and not count_matches:
            verification["error_code"] = "RESOURCE_COUNT_MISMATCH"
        if details:
            secrets = hcloud_common.collect_json_secrets(details)
            verification["details"] = hcloud_common.redact_json(details, secrets)
        resource["verification"] = verification
        resource["state"] = "verified" if verified else "verification_failed"
        resource["updated_at"] = utc_timestamp()
        return dict(resource)

    return _mutate(path, workflow_id=workflow_id, callback=mutate)


def record_cleanup(
    path: Path,
    *,
    workflow_id: str,
    role: str,
    success: bool,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record whether exact task-owned resource cleanup completed."""

    def mutate(ledger: dict[str, Any]) -> dict[str, Any]:
        resource = _resource(ledger, role)
        cleanup: dict[str, Any] = {
            "success": bool(success),
            "recorded_at": utc_timestamp(),
        }
        if details:
            secrets = hcloud_common.collect_json_secrets(details)
            cleanup["details"] = hcloud_common.redact_json(details, secrets)
        resource["cleanup"] = cleanup
        resource["state"] = "deleted" if success else "cleanup_failed"
        resource["updated_at"] = utc_timestamp()
        return dict(resource)

    return _mutate(path, workflow_id=workflow_id, callback=mutate)


def _dependency_order(resources: dict[str, Any]) -> list[str]:
    order: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(role: str) -> None:
        if role in visited:
            return
        if role in visiting:
            raise ValueError("resource ledger contains a dependency cycle")
        visiting.add(role)
        resource = resources[role]
        for dependency in sorted(resource.get("dependencies", [])):
            if dependency not in resources:
                raise ValueError(f"resource dependency {dependency!r} is not registered")
            visit(dependency)
        visiting.remove(role)
        visited.add(role)
        order.append(role)

    for role in sorted(resources):
        visit(role)
    return order


def build_cleanup_plan(path: Path, *, workflow_id: str) -> dict[str, Any]:
    """Build an all-or-nothing cleanup plan from exact owned identifiers.

    No resource discovery is performed. Resources are ordered in reverse
    dependency order so dependants are removed before the resources they use.
    """
    ledger = load_ledger(path, workflow_id=workflow_id)
    resources = ledger["resources"]
    actions: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for role in reversed(_dependency_order(resources)):
        resource = resources[role]
        if resource.get("state") == "deleted":
            continue
        identifiers = list(resource.get("identifiers") or [])
        operation = resource.get("cleanup_operation")
        parameter = resource.get("identifier_parameter")
        if not operation or not parameter:
            blocked.append(
                {
                    "role": role,
                    "error_code": "CLEANUP_CONTRACT_MISSING",
                    "message": "No cleanup operation is registered for this resource role.",
                }
            )
            continue
        if not identifiers:
            blocked.append(
                {
                    "role": role,
                    "error_code": "RESOURCE_IDENTIFIER_MISSING",
                    "message": "Cleanup cannot proceed without a task-owned resource identifier.",
                }
            )
            continue
        actions.append(
            {
                "role": role,
                "service": resource["service"],
                "operation": operation,
                "region": resource["region"],
                "project_id": resource.get("project_id"),
                "identifier_parameter": parameter,
                "identifiers": identifiers,
                "dependencies": list(resource.get("dependencies") or []),
            }
        )
    return {
        "schema_version": 1,
        "workflow_id": ledger["workflow_id"],
        "ready": not blocked,
        "actions": actions if not blocked else [],
        "blocked": blocked,
        "resource_count": len(resources),
    }


def parse_args() -> argparse.Namespace:
    """Parse the inspection-only command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-file", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument(
        "--operation",
        choices=("inspect", "cleanup-plan"),
        default="inspect",
    )
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Inspect a workflow ledger or derive its exact cleanup plan."""
    args = parse_args()
    path = Path(args.ledger_file)
    if args.operation == "cleanup-plan":
        result = build_cleanup_plan(path, workflow_id=args.workflow_id)
    else:
        result = load_ledger(path, workflow_id=args.workflow_id)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
