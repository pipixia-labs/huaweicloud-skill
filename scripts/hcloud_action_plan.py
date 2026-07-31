#!/usr/bin/env python3
"""Generate a portable, non-executing Action Plan from an Action Spec and Cloud Context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import hcloud_unified_contracts
import hcloud_unified_policy


ROOT_DIR = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT_DIR / "references" / "hcloud-service-catalog"


def load_and_validate(contract: str, path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Load and validate a contract document, returning portable diagnostics on failure."""
    try:
        document = hcloud_unified_contracts.load_document(path)
    except hcloud_unified_contracts.ContractValidationError as exc:
        return None, [str(exc)]
    result = hcloud_unified_contracts.validate_contract(contract, document)
    return document if result["success"] else None, list(result["errors"])


def validate_hcloud_catalog_reference(action_spec: dict[str, Any]) -> list[str]:
    """Verify that an hcloud Action Spec still points at the generated catalog facts.

    Only the service document fingerprint, operation name, and selected/advertised
    version are checked.  Request methods, paths, and parameters remain owned by
    the generated catalog and are deliberately not copied into the Action Spec.
    """
    if action_spec.get("execution_family") != "hcloud":
        return []
    catalog_ref = action_spec.get("catalog_ref")
    if not isinstance(catalog_ref, dict):
        return ["hcloud Action Spec has no usable catalog_ref"]
    service = catalog_ref.get("service")
    operation = catalog_ref.get("operation")
    version = catalog_ref.get("version")
    expected_fingerprint = catalog_ref.get("catalog_fingerprint")
    if not all(isinstance(item, str) and item for item in (service, operation, version, expected_fingerprint)):
        return ["hcloud Action Spec catalog_ref is incomplete"]
    catalog_path = CATALOG_DIR / f"{service.lower()}.json"
    try:
        catalog_document = hcloud_unified_contracts.load_document(catalog_path)
    except hcloud_unified_contracts.ContractValidationError as exc:
        return [f"cannot resolve generated catalog for {service}: {exc}"]
    current_fingerprint = hcloud_unified_contracts.fingerprint(catalog_document)
    if current_fingerprint != expected_fingerprint:
        return [f"catalog fingerprint drift for {service}; regenerate or review the Action Spec before planning"]
    operations = catalog_document.get("operations")
    if isinstance(operations, dict):
        matched = operations.get(operation)
    elif isinstance(operations, list):
        matched = next((item for item in operations if isinstance(item, dict) and item.get("name") == operation), None)
    else:
        return [f"generated catalog for {service} has no operations collection"]
    if not isinstance(matched, dict):
        matched = None
    if matched is None:
        return [f"operation {service}/{operation} is not present in the generated catalog"]
    selected_version = matched.get("selected_version")
    versions = matched.get("versions")
    if version != selected_version and (not isinstance(versions, list) or version not in versions):
        return [f"operation {service}/{operation} does not advertise version {version}"]
    return []


def build_action_plan(action_spec: dict[str, Any], cloud_context: dict[str, Any]) -> dict[str, Any]:
    """Build one Action Plan without invoking hcloud, SDK, Terraform, or MaaS.

    The returned value conforms to ``action-plan/v1``.  Its ``execution_authority``
    records the current plan-only boundary so the value cannot honestly be used as a
    real submit permit by an adapter.
    """
    policy_decision = hcloud_unified_policy.evaluate_action_spec(action_spec, cloud_context)
    action_spec_fingerprint = hcloud_unified_contracts.fingerprint(action_spec)
    context_fingerprint = hcloud_unified_contracts.fingerprint(cloud_context)
    plan: dict[str, Any] = {
        "schema_version": "action-plan/v1",
        "action_spec_ref": {
            "id": action_spec["id"],
            "lifecycle": action_spec["lifecycle"],
            "fingerprint": action_spec_fingerprint,
        },
        "context_fingerprint": context_fingerprint,
        "allowed_stage": policy_decision["allowed_stage"],
        "risk_summary": policy_decision["risk_summary"],
        "missing_inputs": policy_decision["missing_inputs"],
        "preflight": policy_decision["preflight"],
        "confirmation": policy_decision["confirmation"],
        "verification": policy_decision["verification"],
        "output": policy_decision["output"],
        "policy": {
            "id": policy_decision["policy_id"],
            "version": policy_decision["policy_version"],
            "decision": policy_decision["decision"],
            "maturity": policy_decision["maturity"],
            "unknown_risk_tags": policy_decision["unknown_risk_tags"],
            "reasons": policy_decision["reasons"],
        },
        "execution_authority": policy_decision["execution_authority"],
    }
    plan["plan_fingerprint"] = hcloud_unified_contracts.fingerprint(plan, excluded_fields={"plan_fingerprint"})
    return plan


def generate_action_plan(action_spec_path: Path, cloud_context_path: Path) -> dict[str, Any]:
    """Validate two inputs and return either one plan or structured local failures."""
    action_spec, action_spec_errors = load_and_validate("action-spec", action_spec_path)
    cloud_context, cloud_context_errors = load_and_validate("cloud-context", cloud_context_path)
    errors = [*action_spec_errors, *cloud_context_errors]
    if errors:
        return {
            "success": False,
            "errors": sorted(set(errors)),
            "execution_boundary": "No plan or cloud operation was produced.",
        }
    assert action_spec is not None and cloud_context is not None
    catalog_errors = validate_hcloud_catalog_reference(action_spec)
    if catalog_errors:
        return {
            "success": False,
            "errors": catalog_errors,
            "execution_boundary": "Catalog reference was rejected before any cloud operation.",
        }
    plan = build_action_plan(action_spec, cloud_context)
    plan_validation = hcloud_unified_contracts.validate_contract("action-plan", plan)
    if not plan_validation["success"]:
        return {
            "success": False,
            "errors": plan_validation["errors"],
            "execution_boundary": "Generated plan was rejected before any cloud operation.",
        }
    return {
        "success": True,
        "action_plan": plan,
        "execution_boundary": "Plan generation only; no hcloud, SDK, Terraform, or MaaS request was sent.",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the local Action Plan generator command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-spec", type=Path, required=True, help="Reviewed Action Spec JSON input.")
    parser.add_argument("--cloud-context", type=Path, required=True, help="Secret-free Cloud Context JSON input.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Generate one non-executing Action Plan and print structured JSON."""
    args = parse_args(argv)
    result = generate_action_plan(args.action_spec, args.cloud_context)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
