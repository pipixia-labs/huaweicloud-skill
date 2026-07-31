#!/usr/bin/env python3
"""Prepare a host-controlled submit handoff without sending a cloud request.

This command is intentionally unable to execute.  It first reuses local
submission admission, then requires a service-specific adapter to be locally
ready.  Even a successful handoff remains ``plan_only`` and must be verified,
consumed once, audited, and executed by a host-specific adapter outside the
Skill.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import hcloud_controlled_adapter_registry
import hcloud_controlled_admission
import hcloud_dns_record_set_request
import hcloud_ecs_create_request
import hcloud_unified_contracts


REQUEST_MAPPERS = {
    hcloud_dns_record_set_request.MAPPING_ID: hcloud_dns_record_set_request.build_dns_a_record_request,
    hcloud_ecs_create_request.MAPPING_ID: hcloud_ecs_create_request.build_ecs_keypair_request,
}


def load_and_validate(contract: str, path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Load and validate one contract input before constructing a handoff."""
    try:
        document = hcloud_unified_contracts.load_document(path)
    except hcloud_unified_contracts.ContractValidationError as exc:
        return None, [str(exc)]
    validation = hcloud_unified_contracts.validate_contract(contract, document)
    return document if validation["success"] else None, list(validation["errors"])


def build_controlled_submit_handoff(
    action_spec: dict[str, Any],
    cloud_context: dict[str, Any],
    execution_intent: dict[str, Any],
    confirmation: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    """Build a fingerprint-bound, non-executing host handoff for one ready adapter."""
    admission = hcloud_controlled_admission.build_submission_authorization(
        action_spec,
        cloud_context,
        execution_intent,
        confirmation,
    )
    if not admission.get("success"):
        return {
            "success": False,
            "error_type": "CONTROLLED_ADMISSION_REJECTED",
            "errors": admission.get("errors", ["controlled admission was rejected"]),
            "execution_boundary": "No handoff and no cloud operation were produced.",
        }
    audit = hcloud_controlled_adapter_registry.audit_registry(registry)
    adapter = hcloud_controlled_adapter_registry.find_adapter_audit(audit, action_spec.get("id", ""))
    if adapter is None:
        errors = ["no controlled adapter is registered for this Action Spec"]
    elif adapter.get("status") != hcloud_controlled_adapter_registry.READY_STATUS:
        errors = [
            "controlled adapter is not ready for host handoff",
            *adapter.get("mapping_gaps", []),
            *adapter.get("blocking_reasons", []),
            *adapter.get("errors", []),
        ]
    else:
        errors = []
    if errors:
        return {
            "success": False,
            "error_type": "CONTROLLED_ADAPTER_NOT_READY",
            "errors": sorted(set(errors)),
            "submission_authorization": admission["submission_authorization"],
            "adapter_audit": adapter,
            "execution_authority": {
                "mode": "plan_only",
                "submission_authority": "not_implemented",
            },
            "execution_boundary": "No cloud operation was attempted; adapter readiness blocked the handoff.",
        }

    request_mapper_id = adapter.get("request_mapper")
    request_mapper = REQUEST_MAPPERS.get(request_mapper_id)
    if request_mapper is None:
        return {
            "success": False,
            "error_type": "CONTROLLED_REQUEST_MAPPER_UNAVAILABLE",
            "errors": [f"no local request mapper is registered for adapter mapper {request_mapper_id!r}"],
            "submission_authorization": admission["submission_authorization"],
            "execution_authority": {"mode": "plan_only", "submission_authority": "not_implemented"},
            "execution_boundary": "No cloud operation was attempted; the local request mapper is unavailable.",
        }
    request_result = request_mapper(execution_intent)
    if not request_result.get("success"):
        return {
            "success": False,
            "error_type": "CONTROLLED_REQUEST_MAPPING_REJECTED",
            "errors": request_result.get("errors", ["local request mapping was rejected"]),
            "submission_authorization": admission["submission_authorization"],
            "execution_authority": {"mode": "plan_only", "submission_authority": "not_implemented"},
            "execution_boundary": "No cloud operation was attempted; the local request mapping was rejected.",
        }
    prepared_request = request_result["prepared_request"]

    authorization = admission["submission_authorization"]
    handoff: dict[str, Any] = {
        "schema_version": "controlled-submit-handoff/v1",
        "adapter_ref": {
            "id": adapter["id"],
            "registry_fingerprint": audit["registry_fingerprint"],
        },
        "action_spec_ref": authorization["action_spec_ref"],
        "catalog_ref": action_spec["catalog_ref"],
        "submission_authorization_fingerprint": authorization["authorization_fingerprint"],
        "execution_intent_fingerprint": authorization["execution_intent_fingerprint"],
        "request_preparation": {
            "mapping_id": prepared_request["mapping_id"],
            "request_fingerprint": prepared_request["request_fingerprint"],
            "payload_delivery": "host_rederives_from_fingerprint_bound_execution_intent",
        },
        "host_authority_requirements": {
            "verification_location": "host_adapter",
            "requirements": list(registry["host_authority_requirements"]),
        },
        "execution_authority": {
            "mode": "plan_only",
            "submission_authority": "host_adapter_required",
            "message": "The Skill prepared a handoff candidate only; the host adapter must independently authenticate, consume approval once, audit, and execute.",
        },
    }
    handoff["handoff_fingerprint"] = hcloud_unified_contracts.fingerprint(
        handoff,
        excluded_fields={"handoff_fingerprint"},
    )
    validation = hcloud_unified_contracts.validate_contract("controlled-submit-handoff", handoff)
    if not validation["success"]:
        return {
            "success": False,
            "error_type": "CONTROLLED_HANDOFF_INVALID",
            "errors": validation["errors"],
            "execution_boundary": "Invalid local handoff was rejected before any cloud operation.",
        }
    return {
        "success": True,
        "controlled_submit_handoff": handoff,
        "execution_boundary": "Prepared a local host handoff only; no hcloud, SDK, Terraform, MaaS, subprocess, or network request was sent.",
    }


def generate_controlled_submit_handoff(
    action_spec_path: Path,
    cloud_context_path: Path,
    execution_intent_path: Path,
    confirmation_path: Path,
    registry_path: Path = hcloud_controlled_adapter_registry.REGISTRY_PATH,
) -> dict[str, Any]:
    """Load local inputs and attempt a non-executing host handoff preparation."""
    action_spec, spec_errors = load_and_validate("action-spec", action_spec_path)
    context, context_errors = load_and_validate("cloud-context", cloud_context_path)
    intent, intent_errors = load_and_validate("execution-intent", execution_intent_path)
    try:
        confirmation = hcloud_unified_contracts.load_document(confirmation_path)
        confirmation_errors: list[str] = []
    except hcloud_unified_contracts.ContractValidationError as exc:
        confirmation = None
        confirmation_errors = [str(exc)]
    try:
        registry = hcloud_controlled_adapter_registry.load_registry(registry_path)
        registry_errors: list[str] = []
    except hcloud_unified_contracts.ContractValidationError as exc:
        registry = None
        registry_errors = [str(exc)]
    errors = [*spec_errors, *context_errors, *intent_errors, *confirmation_errors, *registry_errors]
    if errors:
        return {
            "success": False,
            "error_type": "CONTROLLED_HANDOFF_INPUT_INVALID",
            "errors": sorted(set(errors)),
            "execution_boundary": "Input validation stopped before any cloud operation.",
        }
    assert action_spec is not None and context is not None and intent is not None and confirmation is not None and registry is not None
    return build_controlled_submit_handoff(action_spec, context, intent, confirmation, registry)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse audit-only or local handoff-preparation command arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-adapters", action="store_true", help="Audit adapter readiness without loading task inputs.")
    parser.add_argument("--action-spec", type=Path, help="Curated Action Spec JSON input.")
    parser.add_argument("--cloud-context", type=Path, help="Secret-free Cloud Context JSON input.")
    parser.add_argument("--execution-intent", type=Path, help="Secret-free task execution intent JSON input.")
    parser.add_argument("--confirmation", type=Path, help="Explicit confirmation JSON input.")
    parser.add_argument("--adapter-registry", type=Path, default=hcloud_controlled_adapter_registry.REGISTRY_PATH)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Audit readiness or prepare a local handoff; never invoke a cloud operation."""
    args = parse_args(argv)
    if args.audit_adapters:
        try:
            result = hcloud_controlled_adapter_registry.audit_registry(
                hcloud_controlled_adapter_registry.load_registry(args.adapter_registry),
            )
        except hcloud_unified_contracts.ContractValidationError as exc:
            result = {"success": False, "error_type": "CONTROLLED_ADAPTER_REGISTRY_INVALID", "errors": [str(exc)]}
    else:
        missing = [
            name for name in ("action_spec", "cloud_context", "execution_intent", "confirmation") if getattr(args, name) is None
        ]
        if missing:
            result = {
                "success": False,
                "error_type": "CONTROLLED_HANDOFF_INPUT_REQUIRED",
                "errors": [f"missing required arguments: {', '.join(missing)}"],
                "execution_boundary": "No cloud operation was attempted.",
            }
        else:
            result = generate_controlled_submit_handoff(
                args.action_spec,
                args.cloud_context,
                args.execution_intent,
                args.confirmation,
                args.adapter_registry,
            )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if result.get("success") else 2


if __name__ == "__main__":
    raise SystemExit(main())
