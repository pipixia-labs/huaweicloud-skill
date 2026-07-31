#!/usr/bin/env python3
"""Measure declared invariant-to-entrypoint coverage without overstating enforcement."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import hcloud_unified_baseline_audit


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EXECUTION_PATHS = ROOT_DIR / "references" / "unified-operation-execution-paths.json"
DEFAULT_INVARIANTS = ROOT_DIR / "references" / "unified-operation-invariants.json"
ENFORCEMENT_LEVELS = ("doc_only", "script_enforced", "code_enforced")


class InvariantCoverageError(ValueError):
    """Raised when invariant applicability cannot be compared to reviewed entrypoints."""


def counter_dict(values: list[str]) -> dict[str, int]:
    """Return a deterministically ordered count mapping."""
    return dict(sorted(Counter(values).items()))


def load_validated_inputs(
    execution_paths_path: Path = DEFAULT_EXECUTION_PATHS,
    invariants_path: Path = DEFAULT_INVARIANTS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load phase-0 registers using the same validation as the baseline audit."""
    paths_document = hcloud_unified_baseline_audit.load_object(execution_paths_path, "execution-path inventory")
    invariants_document = hcloud_unified_baseline_audit.load_object(invariants_path, "invariant register")
    paths = hcloud_unified_baseline_audit.validate_execution_paths(paths_document, ROOT_DIR)
    invariants = hcloud_unified_baseline_audit.validate_invariants(invariants_document, ROOT_DIR)
    return paths, invariants


def build_coverage_report(
    execution_paths_path: Path = DEFAULT_EXECUTION_PATHS,
    invariants_path: Path = DEFAULT_INVARIANTS,
) -> dict[str, Any]:
    """Build a local coverage report with explicit path-group denominators.

    The report deliberately counts only a register-declared relation.  A
    ``script_enforced`` row stays script-local, and a missing relationship is
    reported as a gap rather than inferred from file names or documentation.
    """
    try:
        path_groups, invariants = load_validated_inputs(execution_paths_path, invariants_path)
    except hcloud_unified_baseline_audit.BaselineAuditError as exc:
        raise InvariantCoverageError(str(exc)) from exc

    groups_by_id = {str(group["id"]): group for group in path_groups}
    invariant_rows: list[dict[str, Any]] = []
    declared_pairs: list[tuple[str, str]] = []
    for invariant in invariants:
        applicable = list(dict.fromkeys(str(item) for item in invariant["applicable_path_groups"]))
        unknown_groups = sorted(set(applicable) - set(groups_by_id))
        if unknown_groups:
            raise InvariantCoverageError(
                f"Invariant {invariant['id']} references unknown path groups: {', '.join(unknown_groups)}"
            )
        declared_pairs.extend((str(invariant["id"]), group_id) for group_id in applicable)
        invariant_rows.append(
            {
                "id": invariant["id"],
                "level": invariant["level"],
                "applicable_path_groups": applicable,
                "applicable_path_group_count": len(applicable),
                "enforcement_interpretation": (
                    "declared code-enforced scope" if invariant["level"] == "code_enforced"
                    else "declared script-local scope" if invariant["level"] == "script_enforced"
                    else "documented target scope only"
                ),
            }
        )

    groups_rows: list[dict[str, Any]] = []
    covered_group_ids: set[str] = set()
    for group_id, group in sorted(groups_by_id.items()):
        applicable = [row for row in invariant_rows if group_id in row["applicable_path_groups"]]
        if applicable:
            covered_group_ids.add(group_id)
        groups_rows.append(
            {
                "id": group_id,
                "effect": group["effect"],
                "current_admission": group["current_admission"],
                "declared_invariants": [
                    {"id": row["id"], "level": row["level"]}
                    for row in applicable
                ],
            }
        )

    code_enforced = [row["id"] for row in invariant_rows if row["level"] == "code_enforced"]
    return {
        "success": True,
        "schema_version": 1,
        "mode": "declared_invariant_to_entrypoint_coverage",
        "summary": {
            "reviewed_path_groups": len(path_groups),
            "invariants": len(invariants),
            "declared_invariant_path_pairs": len(declared_pairs),
            "path_groups_with_any_declared_invariant": len(covered_group_ids),
            "path_groups_without_declared_invariant": sorted(set(groups_by_id) - covered_group_ids),
            "invariants_by_enforcement_level": counter_dict([str(item["level"]) for item in invariants]),
            "code_enforced_invariant_ids": code_enforced,
            "code_enforced_invariant_count": len(code_enforced),
        },
        "invariants": invariant_rows,
        "path_groups": groups_rows,
        "limitations": [
            "A declared relation is an auditable denominator, not proof that every runtime call follows the invariant.",
            "script_enforced remains local to its stated source path and must not be reported as a global guarantee.",
            "Groups without a declared invariant are gaps in this register, not evidence that no local behavior exists.",
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the local invariant-coverage audit interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-paths", type=Path, default=DEFAULT_EXECUTION_PATHS)
    parser.add_argument("--invariants", type=Path, default=DEFAULT_INVARIANTS)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print a local coverage report without running any cloud entrypoint."""
    args = parse_args(argv)
    try:
        report = build_coverage_report(args.execution_paths, args.invariants)
    except InvariantCoverageError as exc:
        report = {"success": False, "error": str(exc)}
        exit_code = 2
    else:
        exit_code = 0
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
