#!/usr/bin/env python3
"""Build a restricted, non-executing metadata-read plan from reviewed semantics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import hcloud_action_plan
import hcloud_catalog
import hcloud_output_policy
import hcloud_unified_contracts
import hcloud_unified_policy


SAFE_OUTPUT_MODES = {"summary", "file-only"}


def list_of_strings(value: Any) -> list[str]:
    """Return unique non-empty strings while preserving their input order."""
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(item for item in value if isinstance(item, str) and item))


def semantic_input_names(action_spec: dict[str, Any]) -> list[str]:
    """Extract reviewed input names without copying catalog request definitions."""
    preflight = action_spec.get("preflight")
    if not isinstance(preflight, dict):
        return []
    return list_of_strings(preflight.get("required_inputs"))


def catalog_read_only(action_spec: dict[str, Any]) -> tuple[bool, str | None]:
    """Verify the referenced operation remains generated-catalog read-only."""
    catalog_ref = action_spec.get("catalog_ref")
    if not isinstance(catalog_ref, dict):
        return False, "Action Spec has no usable catalog reference."
    catalog = hcloud_catalog.load_catalog()
    service = hcloud_catalog.resolve_service(catalog, str(catalog_ref.get("service") or ""))
    if service is None:
        return False, "Referenced service is absent from the generated catalog."
    operation = hcloud_catalog.resolve_operation(service, str(catalog_ref.get("operation") or ""))
    if operation is None:
        return False, "Referenced operation is absent from the generated catalog."
    if not hcloud_catalog.is_read_only(operation):
        return False, "Referenced catalog operation is not read-only."
    return True, None


def resolve_output_boundary(action_spec: dict[str, Any], input_names: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Resolve the runtime output policy and reject any unbounded/raw fallback."""
    catalog_ref = action_spec.get("catalog_ref") or {}
    service = str(catalog_ref.get("service") or "")
    operation = str(catalog_ref.get("operation") or "")
    semantic_policy = str(action_spec.get("output_policy") or "")
    output = hcloud_output_policy.resolve_output_policy(
        service,
        operation,
        requested_mode="auto",
        provided_params=set(input_names),
        allow_large_output=False,
    )
    boundary = {
        "semantic_policy": semantic_policy,
        "policy_id": output.get("policy_id"),
        "policy_source": output.get("policy_source"),
        "effective_mode": output.get("effective_mode"),
        "risk_class": output.get("risk_class"),
        "required_all": output.get("required_all"),
        "missing_required": output.get("missing_required"),
        "default_limit": output.get("default_limit"),
    }
    reasons: list[str] = []
    if semantic_policy not in {"redacted_summary", "bounded_redacted_summary"}:
        reasons.append("Reviewed Action Spec does not declare a redacted summary output policy.")
    if not output.get("policy_id"):
        reasons.append("No exact or family hcloud output policy is registered for this metadata read.")
    if output.get("blocked"):
        reasons.append(f"Output policy is blocked: {output.get('blocked_reason')}.")
    if output.get("effective_mode") not in SAFE_OUTPUT_MODES:
        reasons.append("Output policy does not resolve to a bounded summary or file-only mode.")
    return boundary, reasons


def build_metadata_read_plan(action_spec: dict[str, Any], cloud_context: dict[str, Any]) -> dict[str, Any]:
    """Build a deny-by-default metadata-read plan without forming a CLI command.

    A plan can be marked eligible only for a future executor after reviewed
    semantics, an exact catalog reference, read-only metadata, bounded output,
    scope, and input declarations are all present.  This function intentionally
    has no ``--execute`` equivalent and cannot accept raw command fragments.
    """
    reasons: list[str] = []
    if action_spec.get("execution_family") != "hcloud":
        reasons.append("Restricted metadata read is currently defined only for hcloud Action Specs.")
    if action_spec.get("effect") != "read":
        reasons.append("Restricted metadata read accepts only Action Specs with effect=read.")
    if action_spec.get("lifecycle") not in {"reviewed", "curated"}:
        reasons.append("Restricted metadata read requires a reviewed or curated Action Spec.")
    reasons.extend(hcloud_action_plan.validate_hcloud_catalog_reference(action_spec))
    read_only, read_only_error = catalog_read_only(action_spec)
    if not read_only and read_only_error:
        reasons.append(read_only_error)

    policy_decision = hcloud_unified_policy.evaluate_action_spec(action_spec, cloud_context)
    if policy_decision["decision"] in {"manual_gate", "plan_only_unknown_risk"}:
        reasons.append(f"Unified risk policy decision is {policy_decision['decision']}.")

    scope = cloud_context.get("scope") if isinstance(cloud_context.get("scope"), dict) else {}
    scope_summary = {
        key: scope[key]
        for key in ("region", "project_id", "enterprise_project_id", "resource_refs")
        if key in scope
    }
    for field in ("region", "project_id"):
        if not isinstance(scope.get(field), str) or not scope[field].strip():
            reasons.append(f"Cloud Context is missing scoped {field} for this metadata read.")

    input_names = semantic_input_names(action_spec)
    missing_inputs = list_of_strings(cloud_context.get("missing_inputs"))
    query_requirements = [
        {
            "id": name,
            "status": "missing" if name in missing_inputs else "declared_for_future_binding",
            "value_transport": "future_controlled_adapter_only",
        }
        for name in input_names
    ]
    missing_query_inputs = [name for name in input_names if name in missing_inputs]
    if missing_query_inputs:
        reasons.append("Cloud Context still lists required metadata-read inputs as missing.")
    if not input_names:
        reasons.append("Reviewed Action Spec has no explicit bounded query inputs.")

    output_boundary, output_reasons = resolve_output_boundary(action_spec, input_names)
    reasons.extend(output_reasons)
    status = "blocked" if reasons else "eligible_for_future_adapter"
    plan: dict[str, Any] = {
        "schema_version": "metadata-read-plan/v1",
        "action_spec_ref": {
            "id": action_spec["id"],
            "lifecycle": action_spec["lifecycle"],
            "fingerprint": hcloud_unified_contracts.fingerprint(action_spec),
        },
        "context_fingerprint": hcloud_unified_contracts.fingerprint(cloud_context),
        "catalog_ref": action_spec.get("catalog_ref"),
        "scope": scope_summary,
        "admission": {
            "status": status,
            "reasons": reasons or ["All planning prerequisites are present; no executor is implemented yet."],
            "risk_policy_decision": policy_decision["decision"],
            "risk_policy_version": policy_decision["policy_version"],
        },
        "query_requirements": query_requirements,
        "output_policy": output_boundary,
        "execution_authority": {
            "mode": "plan_only",
            "metadata_read_authority": "not_implemented",
            "prohibited_inputs": ["raw_command_part", "skip_version_resolution", "unbounded_output_override"],
            "message": "This plan cannot invoke hcloud. A future Skill-controlled read entry must bind declared inputs and re-check this fingerprint.",
        },
    }
    plan["plan_fingerprint"] = hcloud_unified_contracts.fingerprint(plan, excluded_fields={"plan_fingerprint"})
    return plan


def generate_metadata_read_plan(action_spec_path: Path, cloud_context_path: Path) -> dict[str, Any]:
    """Load validated contracts and produce a local metadata-read plan."""
    action_spec, spec_errors = hcloud_action_plan.load_and_validate("action-spec", action_spec_path)
    cloud_context, context_errors = hcloud_action_plan.load_and_validate("cloud-context", cloud_context_path)
    errors = [*spec_errors, *context_errors]
    if errors:
        return {
            "success": False,
            "errors": sorted(set(errors)),
            "execution_boundary": "No metadata read plan or cloud request was produced.",
        }
    assert action_spec is not None and cloud_context is not None
    plan = build_metadata_read_plan(action_spec, cloud_context)
    validation = hcloud_unified_contracts.validate_contract("metadata-read-plan", plan)
    if not validation["success"]:
        return {
            "success": False,
            "errors": validation["errors"],
            "execution_boundary": "Local metadata-read plan was rejected before any cloud request.",
        }
    return {
        "success": True,
        "metadata_read_plan": plan,
        "execution_boundary": "Plan generation only; no hcloud command, SDK call, Terraform action, or MaaS request was sent.",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the non-executing metadata-read plan command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-spec", type=Path, required=True, help="Reviewed hcloud read Action Spec JSON.")
    parser.add_argument("--cloud-context", type=Path, required=True, help="Secret-free Cloud Context JSON.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Generate a restricted local metadata-read plan without any cloud call."""
    args = parse_args(argv)
    result = generate_metadata_read_plan(args.action_spec, args.cloud_context)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
