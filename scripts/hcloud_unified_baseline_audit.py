#!/usr/bin/env python3
"""Audit phase-0 assets, execution paths, and global safety invariants.

This tool is deliberately read-only.  It turns the phase-0 registers into a
small, reproducible baseline report without claiming that a documented or
script-local control is already a universal admission gate.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
REFERENCES_DIR = ROOT_DIR / "references"
DEFAULT_ASSET_REGISTER = REFERENCES_DIR / "unified-operation-asset-register.json"
DEFAULT_EXECUTION_PATHS = REFERENCES_DIR / "unified-operation-execution-paths.json"
DEFAULT_INVARIANTS = REFERENCES_DIR / "unified-operation-invariants.json"
DEFAULT_MIGRATION_MAP = REFERENCES_DIR / "unified-operation-migration-map.json"
SERVICE_REGISTRY_PATH = REFERENCES_DIR / "service-registry.json"
CURATION_PROFILES_PATH = REFERENCES_DIR / "service-curation-profiles.json"
LIVE_VALIDATION_PROFILES_PATH = REFERENCES_DIR / "live-validation-profiles.json"
SCENARIO_ROUTER_PATH = REFERENCES_DIR / "scenario-router.json"
TRIAL_ACTION_SEMANTICS_DIR = REFERENCES_DIR / "action-semantics" / "trial"

ENFORCEMENT_LEVELS = ("doc_only", "script_enforced", "code_enforced")
REQUIRED_ASSET_FIELDS = (
    "id",
    "path",
    "path_kind",
    "classification",
    "current_responsibility",
    "consumers",
    "refresh_source",
    "target_disposition",
    "target_layer",
)
REQUIRED_PATH_GROUP_FIELDS = (
    "id",
    "source_paths",
    "path_kind",
    "effect",
    "current_admission",
    "current_enforcement",
    "target_disposition",
    "review_status",
    "notes",
)
REQUIRED_INVARIANT_FIELDS = ("id", "statement", "level", "scope", "applicable_path_groups", "evidence", "gap", "target")
SUBMIT_CAPABLE_EFFECTS = {"cloud_mutation_possible", "cloud_mutation", "terraform_state_change", "external_cost_or_side_effect"}
UNCONTROLLED_ADMISSIONS = {"no_general_mutation_gate", "dry_run_opt_in"}


class BaselineAuditError(ValueError):
    """Raised when a phase-0 baseline register is malformed or incomplete."""


def load_object(path: Path, label: str) -> dict[str, Any]:
    """Load one JSON object and reject non-object documents."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BaselineAuditError(f"Cannot read {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BaselineAuditError(f"Invalid JSON in {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BaselineAuditError(f"{label} must be a JSON object: {path}")
    return value


def require_fields(entry: dict[str, Any], fields: tuple[str, ...], label: str) -> None:
    """Raise a focused error when a registry entry omits required fields."""
    missing = [field for field in fields if field not in entry]
    if missing:
        entry_id = entry.get("id", "<unknown>")
        raise BaselineAuditError(f"{label} entry {entry_id!r} is missing fields: {', '.join(missing)}")


def resolve_skill_path(root_dir: Path, relative_path: str, label: str) -> Path:
    """Resolve one skill-relative path and reject absolute or escaping paths."""
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise BaselineAuditError(f"{label} must be relative to the skill root: {relative_path}")
    root = root_dir.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise BaselineAuditError(f"{label} escapes the skill root: {relative_path}") from exc
    return resolved


def validate_asset_register(register: dict[str, Any], root_dir: Path) -> list[dict[str, Any]]:
    """Validate asset records and return them after checking their local paths."""
    assets = register.get("assets")
    if not isinstance(assets, list) or not assets:
        raise BaselineAuditError("Asset register must contain a non-empty assets list.")

    seen_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise BaselineAuditError("Every asset register item must be an object.")
        require_fields(asset, REQUIRED_ASSET_FIELDS, "asset register")
        asset_id = asset["id"]
        if not isinstance(asset_id, str) or not asset_id:
            raise BaselineAuditError("Asset ids must be non-empty strings.")
        if asset_id in seen_ids:
            raise BaselineAuditError(f"Duplicate asset id: {asset_id}")
        seen_ids.add(asset_id)
        if asset["path_kind"] not in {"file", "directory"}:
            raise BaselineAuditError(f"Asset {asset_id} has invalid path_kind: {asset['path_kind']!r}")
        if not isinstance(asset["consumers"], list) or not asset["consumers"]:
            raise BaselineAuditError(f"Asset {asset_id} must declare at least one consumer.")

        path = resolve_skill_path(root_dir, str(asset["path"]), f"Asset {asset_id}")
        exists = path.is_file() if asset["path_kind"] == "file" else path.is_dir()
        if not exists:
            raise BaselineAuditError(f"Asset {asset_id} path is missing or has the wrong kind: {asset['path']}")
        validated.append(asset)
    return validated


def validate_execution_paths(inventory: dict[str, Any], root_dir: Path) -> list[dict[str, Any]]:
    """Validate reviewed execution-path groups and their source files."""
    groups = inventory.get("path_groups")
    if not isinstance(groups, list) or not groups:
        raise BaselineAuditError("Execution-path inventory must contain a non-empty path_groups list.")

    seen_ids: set[str] = set()
    seen_sources: set[str] = set()
    validated: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            raise BaselineAuditError("Every execution-path group must be an object.")
        require_fields(group, REQUIRED_PATH_GROUP_FIELDS, "execution-path")
        group_id = group["id"]
        if not isinstance(group_id, str) or not group_id:
            raise BaselineAuditError("Execution-path ids must be non-empty strings.")
        if group_id in seen_ids:
            raise BaselineAuditError(f"Duplicate execution-path id: {group_id}")
        seen_ids.add(group_id)
        if group["review_status"] != "reviewed":
            raise BaselineAuditError(f"Execution-path group {group_id} is not marked reviewed.")

        source_paths = group["source_paths"]
        if not isinstance(source_paths, list) or not source_paths:
            raise BaselineAuditError(f"Execution-path group {group_id} must declare source_paths.")
        for source_path in source_paths:
            if not isinstance(source_path, str) or not source_path:
                raise BaselineAuditError(f"Execution-path group {group_id} has an invalid source path.")
            if source_path in seen_sources:
                raise BaselineAuditError(f"Source path appears in more than one execution-path group: {source_path}")
            seen_sources.add(source_path)
            resolved = resolve_skill_path(root_dir, source_path, f"Execution-path group {group_id}")
            if not resolved.is_file():
                raise BaselineAuditError(f"Execution-path source is missing: {source_path}")
        validated.append(group)
    return validated


def validate_invariants(register: dict[str, Any], root_dir: Path) -> list[dict[str, Any]]:
    """Validate invariant records and their evidence paths."""
    invariants = register.get("invariants")
    if not isinstance(invariants, list) or not invariants:
        raise BaselineAuditError("Invariant register must contain a non-empty invariants list.")

    seen_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for invariant in invariants:
        if not isinstance(invariant, dict):
            raise BaselineAuditError("Every invariant must be an object.")
        require_fields(invariant, REQUIRED_INVARIANT_FIELDS, "invariant")
        invariant_id = invariant["id"]
        if not isinstance(invariant_id, str) or not invariant_id:
            raise BaselineAuditError("Invariant ids must be non-empty strings.")
        if invariant_id in seen_ids:
            raise BaselineAuditError(f"Duplicate invariant id: {invariant_id}")
        seen_ids.add(invariant_id)
        if invariant["level"] not in ENFORCEMENT_LEVELS:
            raise BaselineAuditError(f"Invariant {invariant_id} has invalid level: {invariant['level']!r}")
        applicable = invariant["applicable_path_groups"]
        if not isinstance(applicable, list) or not all(isinstance(item, str) and item for item in applicable):
            raise BaselineAuditError(f"Invariant {invariant_id} must declare non-empty applicable_path_groups.")
        evidence = invariant["evidence"]
        if not isinstance(evidence, list) or not evidence:
            raise BaselineAuditError(f"Invariant {invariant_id} must declare evidence paths.")
        for evidence_path in evidence:
            resolved = resolve_skill_path(root_dir, str(evidence_path), f"Invariant {invariant_id} evidence")
            if not resolved.exists():
                raise BaselineAuditError(f"Invariant {invariant_id} evidence is missing: {evidence_path}")
        validated.append(invariant)
    return validated


def counter_dict(values: list[str]) -> dict[str, int]:
    """Return a deterministically ordered counter for JSON reporting."""
    return dict(sorted(Counter(values).items()))


def normalize_service_id(value: Any) -> str:
    """Normalize service labels from existing service-level assets."""
    return re.sub(r"[\s_\-]+", "", str(value).upper())


def load_service_entries(path: Path, label: str) -> dict[str, dict[str, Any]]:
    """Load an existing service-keyed JSON register without creating a new catalog."""
    value = load_object(path, label)
    services = value.get("services")
    if not isinstance(services, dict):
        raise BaselineAuditError(f"{label} must contain a services object.")
    return {
        normalize_service_id(service): entry
        for service, entry in services.items()
        if isinstance(entry, dict)
    }


def registry_operation_count(entry: dict[str, Any]) -> int:
    """Count current registry operation declarations without inferring API coverage."""
    fields = ("query_operations", "resource_query_operations", "change_operations")
    return sum(len(entry.get(field, [])) for field in fields if isinstance(entry.get(field), list))


def load_trial_action_specs(root_dir: Path) -> dict[str, list[str]]:
    """Return trial Action Spec ids grouped by service without treating them as authorization."""
    trial_dir = root_dir / "references" / "action-semantics" / "trial"
    if not trial_dir.is_dir():
        return {}
    by_service: dict[str, list[str]] = {}
    for path in sorted(trial_dir.glob("*.json")):
        document = load_object(path, f"trial Action Spec {path.name}")
        spec_id = document.get("id")
        if not isinstance(spec_id, str) or not spec_id:
            raise BaselineAuditError(f"Trial Action Spec has no id: {path}")
        catalog_ref = document.get("catalog_ref")
        if isinstance(catalog_ref, dict) and isinstance(catalog_ref.get("service"), str):
            service = normalize_service_id(catalog_ref["service"])
        else:
            service = normalize_service_id(document.get("execution_family") or "UNKNOWN")
        by_service.setdefault(service, []).append(spec_id)
    return {service: sorted(spec_ids) for service, spec_ids in sorted(by_service.items())}


def build_service_maturity_matrix(root_dir: Path) -> list[dict[str, Any]]:
    """Join existing service-level assets into an auditable maturity matrix.

    The matrix deliberately does not introduce operation-level Action Specs.  It
    makes the current service-level sources visible so M1 can bridge them to a
    reviewed semantic layer instead of treating them as a second fact catalog.
    """
    references_dir = root_dir / "references"
    registry = load_service_entries(references_dir / SERVICE_REGISTRY_PATH.name, "service registry")
    curation = load_service_entries(references_dir / CURATION_PROFILES_PATH.name, "service curation profiles")
    validation = load_service_entries(references_dir / LIVE_VALIDATION_PROFILES_PATH.name, "live validation profiles")
    router = load_object(references_dir / SCENARIO_ROUTER_PATH.name, "scenario router")
    scenarios = router.get("scenarios")
    if not isinstance(scenarios, list):
        raise BaselineAuditError("scenario router must contain a scenarios list.")

    scenarios_by_service: dict[str, list[str]] = {}
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        scenario_id = scenario.get("id")
        if not isinstance(scenario_id, str) or not scenario_id:
            continue
        for service in scenario.get("services", []):
            normalized = normalize_service_id(service)
            scenarios_by_service.setdefault(normalized, []).append(scenario_id)

    trial_specs_by_service = load_trial_action_specs(root_dir)
    service_ids = sorted(set(registry) | set(curation) | set(validation) | set(scenarios_by_service) | set(trial_specs_by_service))
    rows: list[dict[str, Any]] = []
    for service_id in service_ids:
        curation_entry = curation.get(service_id, {})
        validation_entry = validation.get(service_id, {})
        registry_entry = registry.get(service_id, {})
        rows.append(
            {
                "service": service_id,
                "in_service_registry": service_id in registry,
                "registered_operation_count": registry_operation_count(registry_entry),
                "curation_status": curation_entry.get("status"),
                "has_live_validation_profile": service_id in validation,
                "live_validation_status": validation_entry.get("current_status"),
                "router_scenarios": sorted(scenarios_by_service.get(service_id, [])),
                "trial_action_spec_ids": trial_specs_by_service.get(service_id, []),
                "action_spec_status": (
                    "trial_action_specs_present_not_execution_authorization"
                    if service_id in trial_specs_by_service
                    else "no_trial_action_spec"
                ),
            }
        )
    return rows


def summarize_service_maturity_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize the service matrix without turning it into a coverage claim."""
    return {
        "services": len(rows),
        "registered_services": sum(bool(row["in_service_registry"]) for row in rows),
        "services_with_curation_profile": sum(row["curation_status"] is not None for row in rows),
        "services_with_live_validation_profile": sum(bool(row["has_live_validation_profile"]) for row in rows),
        "services_with_router_scenario": sum(bool(row["router_scenarios"]) for row in rows),
        "curation_statuses": counter_dict([str(row["curation_status"]) for row in rows if row["curation_status"] is not None]),
        "services_with_trial_action_spec": sum(bool(row["trial_action_spec_ids"]) for row in rows),
        "trial_action_spec_count": sum(len(row["trial_action_spec_ids"]) for row in rows),
        "action_spec_status": "trial_action_specs_present_not_execution_authorization",
        "interpretation": "Service-level profiles, scenario routes, and trial Action Specs are planning evidence; none is operation-level execution authorization.",
    }


def validate_migration_map(register: dict[str, Any], asset_ids: set[str]) -> dict[str, int]:
    """Validate field migration records and conflict ownership against known assets."""
    required_sections = ("context_fields", "result_fields", "action_spec_fields")
    counts: dict[str, int] = {}
    for section in required_sections:
        entries = register.get(section)
        if not isinstance(entries, list) or not entries:
            raise BaselineAuditError(f"Migration map must contain a non-empty {section} list.")
        for entry in entries:
            if not isinstance(entry, dict):
                raise BaselineAuditError(f"Migration map {section} entries must be objects.")
            require_fields(entry, ("target_field", "source_assets", "migration_rule"), f"migration map {section}")
            sources = entry["source_assets"]
            if not isinstance(sources, list) or not sources:
                raise BaselineAuditError(f"Migration map {section} entry must declare source_assets.")
            unknown = sorted(set(str(source) for source in sources) - asset_ids)
            if unknown:
                raise BaselineAuditError(f"Migration map {section} references unknown assets: {', '.join(unknown)}")
        counts[section] = len(entries)

    conflicts = register.get("rule_conflicts")
    if not isinstance(conflicts, list) or not conflicts:
        raise BaselineAuditError("Migration map must contain a non-empty rule_conflicts list.")
    conflict_ids: set[str] = set()
    for conflict in conflicts:
        if not isinstance(conflict, dict):
            raise BaselineAuditError("Migration map rule_conflicts entries must be objects.")
        require_fields(conflict, ("id", "source_assets", "current_difference", "resolution", "acceptance"), "migration conflict")
        conflict_id = conflict["id"]
        if not isinstance(conflict_id, str) or not conflict_id or conflict_id in conflict_ids:
            raise BaselineAuditError(f"Migration map has an invalid or duplicate conflict id: {conflict_id!r}")
        conflict_ids.add(conflict_id)
        unknown = sorted(set(str(source) for source in conflict["source_assets"]) - asset_ids)
        if unknown:
            raise BaselineAuditError(f"Migration conflict {conflict_id} references unknown assets: {', '.join(unknown)}")
    counts["rule_conflicts"] = len(conflicts)
    return counts


def build_baseline(
    *,
    root_dir: Path = ROOT_DIR,
    asset_register_path: Path = DEFAULT_ASSET_REGISTER,
    execution_paths_path: Path = DEFAULT_EXECUTION_PATHS,
    invariants_path: Path = DEFAULT_INVARIANTS,
    migration_map_path: Path = DEFAULT_MIGRATION_MAP,
    include_service_matrix: bool = False,
) -> dict[str, Any]:
    """Build a deterministic phase-0 baseline report from local registers."""
    assets = validate_asset_register(load_object(asset_register_path, "asset register"), root_dir)
    paths = validate_execution_paths(load_object(execution_paths_path, "execution-path inventory"), root_dir)
    invariants = validate_invariants(load_object(invariants_path, "invariant register"), root_dir)
    migration_map = load_object(migration_map_path, "migration map")
    migration_counts = validate_migration_map(migration_map, {str(asset["id"]) for asset in assets})

    source_paths = sorted(source for group in paths for source in group["source_paths"])
    submit_capable = [group for group in paths if group["effect"] in SUBMIT_CAPABLE_EFFECTS]
    uncontrolled = [
        group["id"]
        for group in submit_capable
        if group["current_admission"] in UNCONTROLLED_ADMISSIONS
    ]
    code_enforced = [invariant["id"] for invariant in invariants if invariant["level"] == "code_enforced"]
    service_matrix = build_service_maturity_matrix(root_dir)
    if uncontrolled:
        baseline_status = "audit_only_not_ready_for_mutation_path_closure"
        next_gate = "close every uncontrolled mutation path by a controlled bridge or runtime plan_only"
    else:
        baseline_status = "mutation_paths_closed_plan_only_controlled_submit_not_ready"
        next_gate = "build ECS/DNS Skill-internal controlled entries with plan-bound confirmation, fresh pre-submit facts, and post-submit readback"

    report = {
        "success": True,
        "schema_version": 1,
        "mode": "phase_0_baseline_audit",
        "asset_register": {
            "total": len(assets),
            "by_classification": counter_dict([str(asset["classification"]) for asset in assets]),
            "by_target_disposition": counter_dict([str(asset["target_disposition"]) for asset in assets]),
            "all_paths_present": True,
        },
        "execution_paths": {
            "groups": len(paths),
            "source_paths": len(source_paths),
            "by_effect": counter_dict([str(group["effect"]) for group in paths]),
            "by_current_admission": counter_dict([str(group["current_admission"]) for group in paths]),
            "submit_capable_groups": [group["id"] for group in submit_capable],
            "uncontrolled_submit_capable_groups": uncontrolled,
            "all_reviewed_sources_present": True,
        },
        "invariants": {
            "total": len(invariants),
            "by_enforcement_level": counter_dict([str(invariant["level"]) for invariant in invariants]),
            "code_enforced_ids": code_enforced,
        },
        "service_maturity_matrix": summarize_service_maturity_matrix(service_matrix),
        "migration_map": migration_counts,
        "baseline_status": baseline_status,
        "next_gate": next_gate,
        "limitations": [
            "The registers describe reviewed source groups, not every possible host runtime or user-installed tool.",
            "script_enforced means only the stated script scope; it does not imply a global guarantee.",
            "This audit does not execute cloud, MaaS, Terraform, or network probe commands.",
            "A controlled-submit claim requires a service-specific Skill-controlled entry, plan-bound explicit confirmation, fresh pre-submit facts, and post-submit readback; current M2.5 status only closes legacy paths to plan_only."
        ],
    }
    if include_service_matrix:
        report["service_maturity_matrix"]["services_detail"] = service_matrix
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse baseline-audit command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-register", type=Path, default=DEFAULT_ASSET_REGISTER)
    parser.add_argument("--execution-paths", type=Path, default=DEFAULT_EXECUTION_PATHS)
    parser.add_argument("--invariants", type=Path, default=DEFAULT_INVARIANTS)
    parser.add_argument("--migration-map", type=Path, default=DEFAULT_MIGRATION_MAP)
    parser.add_argument(
        "--include-service-matrix",
        action="store_true",
        help="Include the service-level maturity matrix instead of only its summary.",
    )
    parser.add_argument(
        "--fail-on-gaps",
        action="store_true",
        help="Exit non-zero when a submit-capable group still lacks a general mutation gate.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the read-only phase-0 baseline audit."""
    args = parse_args(argv)
    try:
        report = build_baseline(
            asset_register_path=args.asset_register,
            execution_paths_path=args.execution_paths,
            invariants_path=args.invariants,
            migration_map_path=args.migration_map,
            include_service_matrix=args.include_service_matrix,
        )
    except BaselineAuditError as exc:
        report = {"success": False, "error": str(exc)}
        print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    if args.fail_on_gaps and report["execution_paths"]["uncontrolled_submit_capable_groups"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
