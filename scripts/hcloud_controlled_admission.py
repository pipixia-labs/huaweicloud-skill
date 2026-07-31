#!/usr/bin/env python3
"""Prepare a fingerprint-bound submission record without executing any cloud operation.

This module is deliberately an admission *preparation* layer.  It validates a
curated Action Spec, Cloud Context, Execution Intent, and explicit confirmation
as one immutable tuple, then emits ``submission-authorization/v1``.  A future
Skill-controlled entry must revalidate that record immediately before a real
submission; this command has no executor and accepts no raw command fragments.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import hcloud_action_plan
import hcloud_unified_contracts


def load_and_validate(contract: str, path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Load and validate one input contract, returning local diagnostics on failure."""
    try:
        document = hcloud_unified_contracts.load_document(path)
    except hcloud_unified_contracts.ContractValidationError as exc:
        return None, [str(exc)]
    validation = hcloud_unified_contracts.validate_contract(contract, document)
    return document if validation["success"] else None, list(validation["errors"])


def validate_execution_intent_binding(
    action_spec: dict[str, Any],
    cloud_context: dict[str, Any],
    execution_intent: dict[str, Any],
) -> list[str]:
    """Ensure an Execution Intent is an exact, scoped input for one Action Spec.

    The check intentionally compares complete references rather than deriving a
    command.  For hcloud it also requires the intent to carry the same exact
    generated-catalog reference as the reviewed semantic Action Spec.
    """
    errors: list[str] = []
    expected_ref = {
        "id": action_spec.get("id"),
        "lifecycle": action_spec.get("lifecycle"),
        "fingerprint": hcloud_unified_contracts.fingerprint(action_spec),
    }
    if execution_intent.get("execution_family") != action_spec.get("execution_family"):
        errors.append("execution intent family does not match the Action Spec")
    if execution_intent.get("action_spec_ref") != expected_ref:
        errors.append("execution intent Action Spec reference is stale or does not match the reviewed Action Spec")

    context_scope = cloud_context.get("scope")
    intent_scope = execution_intent.get("scope")
    if isinstance(context_scope, dict) and isinstance(intent_scope, dict):
        for field in ("region", "project_id"):
            context_value = context_scope.get(field)
            intent_value = intent_scope.get(field)
            if not isinstance(intent_value, str) or not intent_value:
                errors.append(f"execution intent scope requires {field}")
            elif isinstance(context_value, str) and context_value and intent_value != context_value:
                errors.append(f"execution intent scope {field} does not match Cloud Context")
    else:
        errors.append("Cloud Context and Execution Intent require object scopes")

    if action_spec.get("execution_family") == "hcloud":
        if execution_intent.get("catalog_ref") != action_spec.get("catalog_ref"):
            errors.append("execution intent catalog reference is stale or does not match the Action Spec")
    preflight = action_spec.get("preflight")
    required_inputs = preflight.get("required_inputs") if isinstance(preflight, dict) else []
    parameters = execution_intent.get("parameters")
    if isinstance(required_inputs, list) and isinstance(parameters, dict):
        for input_name in required_inputs:
            value = parameters.get(input_name) if isinstance(input_name, str) else None
            if value is None or value == "" or value == [] or value == {}:
                errors.append(f"execution intent misses required input {input_name}")
    return errors


def validate_confirmation_binding(
    confirmation: dict[str, Any],
    action_plan: dict[str, Any],
    execution_intent: dict[str, Any],
) -> list[str]:
    """Require explicit confirmation of the exact plan, intent, and preflight set."""
    errors: list[str] = []
    if confirmation.get("status") != "confirmed":
        errors.append("confirmation status must be confirmed")
    approval_id = confirmation.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id.strip():
        errors.append("confirmation requires a non-empty approval_id")

    plan_fingerprint = action_plan.get("plan_fingerprint")
    intent_fingerprint = hcloud_unified_contracts.fingerprint(execution_intent)
    if confirmation.get("reviewed_action_plan_fingerprint") != plan_fingerprint:
        errors.append("confirmation does not bind the current Action Plan fingerprint")
    if confirmation.get("reviewed_execution_intent_fingerprint") != intent_fingerprint:
        errors.append("confirmation does not bind the current Execution Intent fingerprint")

    evidence = confirmation.get("preflight_evidence")
    if not isinstance(evidence, list):
        errors.append("confirmation requires preflight_evidence as a list")
        return errors
    evidence_by_id: dict[str, str] = {}
    for item in evidence:
        if not isinstance(item, dict):
            errors.append("each preflight evidence item must be an object")
            continue
        item_id = item.get("id")
        status = item.get("status")
        if not isinstance(item_id, str) or not item_id:
            errors.append("each preflight evidence item requires a non-empty id")
            continue
        if not isinstance(status, str) or not status:
            errors.append(f"preflight evidence {item_id} requires a status")
            continue
        if item_id in evidence_by_id:
            errors.append(f"preflight evidence {item_id} is duplicated")
            continue
        evidence_by_id[item_id] = status

    preflight = action_plan.get("preflight")
    if isinstance(preflight, list):
        for requirement in preflight:
            requirement_id = requirement.get("id") if isinstance(requirement, dict) else None
            if not isinstance(requirement_id, str) or not requirement_id:
                errors.append("Action Plan contains an invalid preflight requirement")
            elif evidence_by_id.get(requirement_id) != "passed":
                errors.append(f"preflight requirement {requirement_id} is not confirmed as passed")
    else:
        errors.append("Action Plan preflight requirements are unavailable")
    return errors


def validate_action_plan_readiness(action_plan: dict[str, Any]) -> list[str]:
    """Reject prepared submission records when the current plan still names gaps.

    Execution Intent is the concrete input record, but it cannot silently repair
    a stale Cloud Context.  The caller must refresh the plan after collecting
    every listed missing input, so the confirmation always reviews one coherent
    context, plan, and intent tuple.
    """
    errors: list[str] = []
    missing_inputs = action_plan.get("missing_inputs")
    if not isinstance(missing_inputs, list):
        errors.append("Action Plan missing_inputs are unavailable")
    elif missing_inputs:
        values = ", ".join(str(item) for item in missing_inputs)
        errors.append(f"Action Plan still has unresolved missing inputs: {values}")
    policy = action_plan.get("policy")
    decision = policy.get("decision") if isinstance(policy, dict) else None
    if decision in {"manual_gate", "plan_only_unknown_risk"}:
        errors.append(f"Action Plan policy decision {decision} cannot prepare a controlled submission")
    return errors


def build_submission_authorization(
    action_spec: dict[str, Any],
    cloud_context: dict[str, Any],
    execution_intent: dict[str, Any],
    confirmation: dict[str, Any],
) -> dict[str, Any]:
    """Build a prepared authorization after every local binding check succeeds.

    This function never invokes hcloud, an SDK, Terraform, MaaS, subprocesses,
    or the network.  Its result deliberately retains ``not_implemented`` as the
    only execution authority until a Skill-controlled entry is designed and tested.
    """
    catalog_errors = hcloud_action_plan.validate_hcloud_catalog_reference(action_spec)
    if catalog_errors:
        return {"success": False, "errors": catalog_errors}
    action_plan = hcloud_action_plan.build_action_plan(action_spec, cloud_context)
    plan_validation = hcloud_unified_contracts.validate_contract("action-plan", action_plan)
    if not plan_validation["success"]:
        return {"success": False, "errors": list(plan_validation["errors"])}
    if action_spec.get("lifecycle") != "curated":
        return {"success": False, "errors": ["controlled submission preparation requires a curated Action Spec"]}
    if action_spec.get("effect") == "read":
        return {"success": False, "errors": ["controlled submission preparation is for non-read effects only"]}

    errors = [
        *validate_action_plan_readiness(action_plan),
        *validate_execution_intent_binding(action_spec, cloud_context, execution_intent),
        *validate_confirmation_binding(confirmation, action_plan, execution_intent),
    ]
    secret_paths = hcloud_unified_contracts.secret_field_paths(confirmation)
    errors.extend(f"confirmation contains a secret-bearing field: {path}" for path in secret_paths)
    if errors:
        return {"success": False, "errors": sorted(set(errors)), "action_plan": action_plan}

    action_spec_ref = copy.deepcopy(action_plan["action_spec_ref"])
    confirmation_record = {
        "status": "confirmed",
        "approval_id": confirmation["approval_id"],
        "reviewed_action_plan_fingerprint": action_plan["plan_fingerprint"],
        "reviewed_execution_intent_fingerprint": hcloud_unified_contracts.fingerprint(execution_intent),
        "preflight_evidence_fingerprint": hcloud_unified_contracts.fingerprint(
            confirmation["preflight_evidence"],
        ),
    }
    authorization: dict[str, Any] = {
        "schema_version": "submission-authorization/v1",
        "action_spec_ref": action_spec_ref,
        "action_plan_fingerprint": action_plan["plan_fingerprint"],
        "execution_intent_fingerprint": hcloud_unified_contracts.fingerprint(execution_intent),
        "confirmation": confirmation_record,
        "admission": {
            "status": "prepared_for_future_adapter",
            "binding": "Action Plan, Execution Intent, and confirmation fingerprints were locally rechecked together.",
            "preflight": "Every Action Plan preflight requirement has a passed confirmation evidence item.",
            "replay_protection": "The future Skill-controlled entry must reject stale or mismatched plan/intent/confirmation bindings. This local record does not prove authenticated identity, one-time use, or durable audit retention.",
        },
        "execution_authority": {
            "mode": "plan_only",
            "submission_authority": "not_implemented",
            "message": "This prepared record is not a submit permit and cannot invoke a cloud operation.",
        },
    }
    authorization["authorization_fingerprint"] = hcloud_unified_contracts.fingerprint(
        authorization,
        excluded_fields={"authorization_fingerprint"},
    )
    validation = hcloud_unified_contracts.validate_contract("submission-authorization", authorization)
    if not validation["success"]:
        return {"success": False, "errors": list(validation["errors"]), "action_plan": action_plan}
    return {"success": True, "action_plan": action_plan, "submission_authorization": authorization}


def generate_submission_authorization(
    action_spec_path: Path,
    cloud_context_path: Path,
    execution_intent_path: Path,
    confirmation_path: Path,
) -> dict[str, Any]:
    """Load local inputs and prepare a submission record without any cloud call."""
    action_spec, action_spec_errors = load_and_validate("action-spec", action_spec_path)
    cloud_context, context_errors = load_and_validate("cloud-context", cloud_context_path)
    execution_intent, intent_errors = load_and_validate("execution-intent", execution_intent_path)
    try:
        confirmation = hcloud_unified_contracts.load_document(confirmation_path)
    except hcloud_unified_contracts.ContractValidationError as exc:
        confirmation = None
        confirmation_errors = [str(exc)]
    else:
        confirmation_errors = []
    errors = [*action_spec_errors, *context_errors, *intent_errors, *confirmation_errors]
    if errors:
        return {
            "success": False,
            "errors": sorted(set(errors)),
            "execution_boundary": "Admission preparation stopped before any cloud operation.",
        }
    assert action_spec is not None and cloud_context is not None and execution_intent is not None and confirmation is not None
    result = build_submission_authorization(action_spec, cloud_context, execution_intent, confirmation)
    result["execution_boundary"] = (
        "Pure local admission preparation only; no hcloud, SDK, Terraform, MaaS, subprocess, or network request was sent."
    )
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the strictly local controlled-admission command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-spec", type=Path, required=True, help="Curated Action Spec JSON input.")
    parser.add_argument("--cloud-context", type=Path, required=True, help="Secret-free Cloud Context JSON input.")
    parser.add_argument("--execution-intent", type=Path, required=True, help="Secret-free task-specific intent JSON input.")
    parser.add_argument("--confirmation", type=Path, required=True, help="Explicit host-provided confirmation JSON input.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Prepare a non-executing submission authorization and print structured JSON."""
    args = parse_args(argv)
    result = generate_submission_authorization(
        args.action_spec,
        args.cloud_context,
        args.execution_intent,
        args.confirmation,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
