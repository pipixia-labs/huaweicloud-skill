#!/usr/bin/env python3
"""Audit whether every reviewed mutation path has actually passed the M2.5 closure gate.

The audit reads only the execution-path inventory and the M2.5 closure ledger.
It is intentionally strict: a planned bridge, an Action Plan, or a local
confirmation contract is not counted as runtime closure until the ledger has
evidence for a bridge or an explicit ``plan_only`` downgrade.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import hcloud_unified_baseline_audit


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EXECUTION_PATHS = ROOT_DIR / "references" / "unified-operation-execution-paths.json"
DEFAULT_CLOSURE_LEDGER = ROOT_DIR / "references" / "unified-m2-5-closure-ledger.json"
CLOSED_STATUSES = {"closed_via_controlled_bridge", "closed_via_plan_only"}
OPEN_STATUSES = {"unclosed", "in_progress"}
REQUIRED_LEDGER_FIELDS = (
    "path_group_id",
    "closure_status",
    "intended_disposition",
    "preparation_status",
    "required_prerequisites",
    "required_negative_test_ids",
    "compatibility_impact",
    "closure_acceptance",
    "current_blocker",
)
CLOSED_EVIDENCE_FIELDS = ("runtime_evidence", "negative_test_evidence")


class ClosureAuditError(ValueError):
    """Raised when the M2.5 closure ledger is inconsistent with reviewed paths."""


def load_ledger(path: Path) -> dict[str, Any]:
    """Load the local closure ledger as an object without following external inputs."""
    try:
        document = hcloud_unified_baseline_audit.load_object(path, "M2.5 closure ledger")
    except hcloud_unified_baseline_audit.BaselineAuditError as exc:
        raise ClosureAuditError(str(exc)) from exc
    if document.get("schema_version") != 1 or document.get("milestone") != "M2.5":
        raise ClosureAuditError("M2.5 closure ledger has an unsupported schema_version or milestone")
    return document


def load_reviewed_mutation_groups(execution_paths_path: Path) -> dict[str, dict[str, Any]]:
    """Return reviewed, submit-capable groups from the canonical phase-0 inventory."""
    try:
        inventory = hcloud_unified_baseline_audit.load_object(execution_paths_path, "execution-path inventory")
        groups = hcloud_unified_baseline_audit.validate_execution_paths(inventory, ROOT_DIR)
    except hcloud_unified_baseline_audit.BaselineAuditError as exc:
        raise ClosureAuditError(str(exc)) from exc
    return {
        str(group["id"]): group
        for group in groups
        if group.get("effect") in hcloud_unified_baseline_audit.SUBMIT_CAPABLE_EFFECTS
    }


def validate_ledger_entries(
    ledger: dict[str, Any],
    mutation_groups: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate that exactly one closure row exists for every mutation group."""
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ClosureAuditError("M2.5 closure ledger requires a non-empty entries list")
    by_group: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ClosureAuditError("Every M2.5 closure ledger entry must be an object")
        missing = [field for field in REQUIRED_LEDGER_FIELDS if field not in entry]
        if missing:
            raise ClosureAuditError(f"M2.5 closure ledger entry is missing fields: {', '.join(missing)}")
        group_id = entry["path_group_id"]
        if not isinstance(group_id, str) or not group_id:
            raise ClosureAuditError("M2.5 closure ledger path_group_id must be a non-empty string")
        if group_id in by_group:
            raise ClosureAuditError(f"Duplicate M2.5 closure ledger entry: {group_id}")
        if group_id not in mutation_groups:
            raise ClosureAuditError(f"M2.5 closure ledger references a non-mutation or unknown group: {group_id}")
        group = mutation_groups[group_id]
        status = entry["closure_status"]
        if status not in CLOSED_STATUSES | OPEN_STATUSES:
            raise ClosureAuditError(f"M2.5 closure ledger has unsupported status for {group_id}: {status}")
        for field in ("required_prerequisites", "required_negative_test_ids"):
            values = entry[field]
            if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
                raise ClosureAuditError(f"M2.5 closure ledger {group_id} field {field} must be a string list")
        if status in CLOSED_STATUSES:
            for field in CLOSED_EVIDENCE_FIELDS:
                evidence_paths = entry.get(field)
                if not isinstance(evidence_paths, list) or not evidence_paths or not all(
                    isinstance(item, str) and item for item in evidence_paths
                ):
                    raise ClosureAuditError(
                        f"Closed M2.5 ledger entry {group_id} requires non-empty {field} evidence paths"
                    )
                for evidence_path in evidence_paths:
                    resolved = hcloud_unified_baseline_audit.resolve_skill_path(
                        ROOT_DIR,
                        evidence_path,
                        f"M2.5 closure evidence for {group_id}",
                    )
                    if not resolved.is_file():
                        raise ClosureAuditError(
                            f"M2.5 closure evidence is missing for {group_id}: {evidence_path}"
                        )
        if status == "closed_via_plan_only" and group["current_admission"] not in {
            "runtime_plan_only",
            "catalog_read_only_or_runtime_plan_only",
        }:
            raise ClosureAuditError(
                f"M2.5 plan-only closure for {group_id} disagrees with current admission "
                f"{group['current_admission']!r}"
            )
        by_group[group_id] = entry

    missing_groups = sorted(set(mutation_groups) - set(by_group))
    if missing_groups:
        raise ClosureAuditError(f"M2.5 closure ledger misses reviewed mutation groups: {', '.join(missing_groups)}")
    return [by_group[group_id] for group_id in sorted(by_group)]


def build_closure_report(
    execution_paths_path: Path = DEFAULT_EXECUTION_PATHS,
    closure_ledger_path: Path = DEFAULT_CLOSURE_LEDGER,
) -> dict[str, Any]:
    """Build an evidence-oriented M2.5 status report without executing any path."""
    mutation_groups = load_reviewed_mutation_groups(execution_paths_path)
    entries = validate_ledger_entries(load_ledger(closure_ledger_path), mutation_groups)
    status_counts = dict(sorted(Counter(str(entry["closure_status"]) for entry in entries).items()))
    open_entries = [entry for entry in entries if entry["closure_status"] not in CLOSED_STATUSES]
    rows = []
    for entry in entries:
        group = mutation_groups[entry["path_group_id"]]
        rows.append(
            {
                "path_group_id": entry["path_group_id"],
                "effect": group["effect"],
                "current_admission": group["current_admission"],
                "closure_status": entry["closure_status"],
                "intended_disposition": entry["intended_disposition"],
                "preparation_status": entry["preparation_status"],
                "required_negative_test_ids": entry["required_negative_test_ids"],
                "runtime_evidence": entry.get("runtime_evidence", []),
                "negative_test_evidence": entry.get("negative_test_evidence", []),
                "current_blocker": entry["current_blocker"],
            }
        )
    return {
        "success": True,
        "schema_version": 1,
        "milestone": "M2.5",
        "closure_status": "ready" if not open_entries else "not_ready",
        "summary": {
            "reviewed_mutation_path_groups": len(mutation_groups),
            "ledger_entries": len(entries),
            "status_counts": status_counts,
            "open_path_group_ids": [entry["path_group_id"] for entry in open_entries],
        },
        "paths": rows,
        "limitations": [
            "A prepared Action Plan or Submission Authorization remains preparation evidence; it is not permission for a real cloud request.",
            "ready means every reviewed legacy mutation path is either a Skill-controlled entry or code-enforced plan_only; it does not mean controlled submit is implemented.",
            "This audit reads local governance records and never imports, invokes, or changes an execution entrypoint.",
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the local M2.5 closure-audit command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-paths", type=Path, default=DEFAULT_EXECUTION_PATHS)
    parser.add_argument("--closure-ledger", type=Path, default=DEFAULT_CLOSURE_LEDGER)
    parser.add_argument("--fail-on-open", action="store_true", help="Return non-zero while any mutation path remains open.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print the M2.5 closure state without contacting Huawei Cloud or other APIs."""
    args = parse_args(argv)
    try:
        report = build_closure_report(args.execution_paths, args.closure_ledger)
    except ClosureAuditError as exc:
        report = {"success": False, "error": str(exc)}
        exit_code = 2
    else:
        exit_code = 3 if args.fail_on_open and report["closure_status"] != "ready" else 0
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
