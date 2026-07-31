#!/usr/bin/env python3
"""Compare one legacy entrypoint with a unified plan without invoking either path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import hcloud_action_plan
import hcloud_metadata_read_plan
import hcloud_unified_contracts


ROOT_DIR = Path(__file__).resolve().parents[1]
EXECUTION_PATHS = ROOT_DIR / "references" / "unified-operation-execution-paths.json"
MUTATION_EFFECTS = {"cloud_mutation_possible", "cloud_mutation", "terraform_state_change", "external_cost_or_side_effect"}
READ_EFFECTS = {"cloud_read"}


class ShadowAuditError(ValueError):
    """Raised when a requested legacy source is absent from the reviewed inventory."""


def load_inventory(path: Path = EXECUTION_PATHS) -> list[dict[str, Any]]:
    """Load the reviewed local entrypoint inventory without inspecting a live runtime."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ShadowAuditError(f"Cannot read execution-path inventory: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ShadowAuditError(f"Invalid execution-path inventory: {path}: {exc}") from exc
    groups = document.get("path_groups") if isinstance(document, dict) else None
    if not isinstance(groups, list):
        raise ShadowAuditError("Execution-path inventory has no path_groups list.")
    return [group for group in groups if isinstance(group, dict)]


def find_entrypoint_group(source_path: str, groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the one reviewed group containing an exact skill-relative source path."""
    matches = [group for group in groups if source_path in group.get("source_paths", [])]
    if not matches:
        raise ShadowAuditError(f"Source path is not a reviewed entrypoint: {source_path}")
    if len(matches) != 1:
        raise ShadowAuditError(f"Source path appears in multiple reviewed entrypoint groups: {source_path}")
    return matches[0]


def build_unified_plan(action_spec_path: Path, cloud_context_path: Path) -> dict[str, Any]:
    """Build the appropriate local unified plan for an already-reviewed Action Spec."""
    action_spec, errors = hcloud_action_plan.load_and_validate("action-spec", action_spec_path)
    if errors or action_spec is None:
        return {"success": False, "errors": errors, "kind": "unavailable"}
    if action_spec.get("execution_family") == "hcloud" and action_spec.get("effect") == "read":
        result = hcloud_metadata_read_plan.generate_metadata_read_plan(action_spec_path, cloud_context_path)
        return {"kind": "metadata_read_plan", **result}
    result = hcloud_action_plan.generate_action_plan(action_spec_path, cloud_context_path)
    return {"kind": "action_plan", **result}


def unified_authority(plan_result: dict[str, Any]) -> str:
    """Return the unified plan's explicit authority state, never inferring permission."""
    if not plan_result.get("success"):
        return "unavailable"
    if plan_result.get("kind") == "metadata_read_plan":
        plan = plan_result.get("metadata_read_plan")
        if isinstance(plan, dict):
            authority = plan.get("execution_authority")
            if isinstance(authority, dict):
                return str(authority.get("metadata_read_authority") or "unavailable")
    plan = plan_result.get("action_plan")
    if isinstance(plan, dict):
        authority = plan.get("execution_authority")
        if isinstance(authority, dict):
            return str(authority.get("submission_authority") or "unavailable")
    return "unavailable"


def comparison_findings(group: dict[str, Any], plan_result: dict[str, Any]) -> list[dict[str, str]]:
    """Describe legacy-versus-unified differences without claiming a migration is complete."""
    findings: list[dict[str, str]] = []
    effect = str(group.get("effect") or "unknown")
    admission = str(group.get("current_admission") or "unknown")
    authority = unified_authority(plan_result)
    if effect in MUTATION_EFFECTS and authority != "implemented":
        if admission in {"runtime_plan_only", "catalog_read_only_or_runtime_plan_only"}:
            findings.append(
                {
                    "id": "legacy_mutation_path_closed_plan_only",
                    "severity": "info",
                    "message": "Legacy mutation path is code-enforced plan_only and cannot submit until a Skill-controlled entry exists.",
                }
            )
        else:
            findings.append(
                {
                    "id": "legacy_mutation_path_not_yet_bridged",
                    "severity": "high",
                    "message": "Legacy mutation-capable path remains outside the unified submit authority; M2.5 closure is still required.",
                }
            )
    if effect in READ_EFFECTS and authority != "implemented":
        findings.append(
            {
                "id": "legacy_read_path_not_yet_bridged",
                "severity": "medium",
                "message": "Legacy read path is not yet executed by the unified metadata-read authority.",
            }
        )
    if admission in {"no_general_mutation_gate", "dry_run_opt_in"}:
        findings.append(
            {
                "id": "legacy_admission_is_not_a_unified_contract",
                "severity": "high",
                "message": "Legacy admission does not currently bind a reviewed Action Spec and Action Plan to the operation.",
            }
        )
    if not plan_result.get("success"):
        findings.append(
            {
                "id": "unified_plan_unavailable",
                "severity": "high",
                "message": "The selected unified plan could not be built; do not infer a compatible migration path.",
            }
        )
    return findings


def build_shadow_report(source_path: str, action_spec_path: Path, cloud_context_path: Path) -> dict[str, Any]:
    """Return an offline comparison report for one reviewed legacy source path."""
    group = find_entrypoint_group(source_path, load_inventory())
    unified_plan = build_unified_plan(action_spec_path, cloud_context_path)
    action_spec, action_spec_errors = hcloud_action_plan.load_and_validate("action-spec", action_spec_path)
    context, context_errors = hcloud_action_plan.load_and_validate("cloud-context", cloud_context_path)
    if action_spec_errors or context_errors or action_spec is None or context is None:
        raise ShadowAuditError("Cannot fingerprint invalid shadow inputs.")
    return {
        "schema_version": "entrypoint-shadow-report/v1",
        "source_path": source_path,
        "legacy_entrypoint": {
            "group_id": group.get("id"),
            "effect": group.get("effect"),
            "current_admission": group.get("current_admission"),
            "current_enforcement": group.get("current_enforcement"),
            "target_disposition": group.get("target_disposition"),
        },
        "unified_input": {
            "action_spec_id": action_spec.get("id"),
            "action_spec_fingerprint": hcloud_unified_contracts.fingerprint(action_spec),
            "context_fingerprint": hcloud_unified_contracts.fingerprint(context),
        },
        "unified_plan": unified_plan,
        "comparison": {
            "unified_authority": unified_authority(unified_plan),
            "findings": comparison_findings(group, unified_plan),
            "migration_status": (
                "runtime_plan_only_closed_pending_skill_controlled_entry"
                if group.get("current_admission") in {"runtime_plan_only", "catalog_read_only_or_runtime_plan_only"}
                else "shadow_only_not_runtime_bridge"
            ),
        },
        "execution_boundary": "Offline comparison only; the legacy entrypoint and unified plan were not executed.",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse an offline entrypoint-shadow comparison request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-path", required=True, help="Exact reviewed skill-relative script source path.")
    parser.add_argument("--action-spec", type=Path, required=True, help="Action Spec JSON used for the comparison.")
    parser.add_argument("--cloud-context", type=Path, required=True, help="Cloud Context JSON used for the comparison.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print a shadow report without invoking cloud or legacy entrypoint code paths."""
    args = parse_args(argv)
    try:
        result = build_shadow_report(args.source_path, args.action_spec, args.cloud_context)
    except ShadowAuditError as exc:
        result = {"success": False, "error": str(exc), "execution_boundary": "No entrypoint was invoked."}
        exit_code = 2
    else:
        result["success"] = True
        exit_code = 0
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
