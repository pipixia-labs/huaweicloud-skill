#!/usr/bin/env python3
"""Audit service-specific controlled-adapter readiness without any cloud execution.

The registry is deliberately more restrictive than the generic execution policy:
an adapter can become ``ready_for_handoff`` only when its curated Action Spec,
generated catalog reference, semantic input bindings, and verification profile
can all be checked locally.  This module never creates an hcloud command or a
wire payload; an authenticated host adapter remains a separate future boundary.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import hcloud_action_plan
import hcloud_unified_contracts


ROOT_DIR = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT_DIR / "references" / "controlled-adapter-registry.json"
READY_STATUS = "ready_for_handoff"
BLOCKED_STATUS = "blocked"


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load the local adapter registry as a JSON object."""
    return hcloud_unified_contracts.load_document(path)


def resolve_action_spec(path_value: Any) -> tuple[dict[str, Any] | None, list[str]]:
    """Load a registry Action Spec path while preventing registry path escape."""
    if not isinstance(path_value, str) or not path_value:
        return None, ["adapter requires a non-empty action_spec_path"]
    candidate = (ROOT_DIR / path_value).resolve()
    try:
        candidate.relative_to(ROOT_DIR)
    except ValueError:
        return None, ["adapter action_spec_path must remain inside the Skill root"]
    try:
        action_spec = hcloud_unified_contracts.load_document(candidate)
    except hcloud_unified_contracts.ContractValidationError as exc:
        return None, [str(exc)]
    validation = hcloud_unified_contracts.validate_contract("action-spec", action_spec)
    return action_spec if validation["success"] else None, list(validation["errors"])


def catalog_operation(action_spec: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Return referenced generated operation facts after catalog drift validation."""
    errors = hcloud_action_plan.validate_hcloud_catalog_reference(action_spec)
    if errors:
        return None, errors
    catalog_ref = action_spec.get("catalog_ref")
    assert isinstance(catalog_ref, dict)
    catalog_path = ROOT_DIR / "references" / "hcloud-service-catalog" / f"{catalog_ref['service'].lower()}.json"
    try:
        catalog = hcloud_unified_contracts.load_document(catalog_path)
    except hcloud_unified_contracts.ContractValidationError as exc:
        return None, [str(exc)]
    operations = catalog.get("operations")
    operation = operations.get(catalog_ref["operation"]) if isinstance(operations, dict) else None
    if not isinstance(operation, dict):
        return None, ["referenced generated catalog operation is unavailable"]
    return operation, []


def audit_adapter(adapter: Any, registry_requirements: list[str]) -> dict[str, Any]:
    """Audit one adapter entry and expose every local readiness gap.

    The result separates registry validity from readiness.  A blocked adapter is
    an expected safe state, while malformed evidence is a registry error.
    """
    if not isinstance(adapter, dict):
        return {"id": None, "status": "invalid", "errors": ["adapter entry must be an object"], "mapping_gaps": []}
    adapter_id = adapter.get("id")
    errors: list[str] = []
    if not isinstance(adapter_id, str) or not adapter_id:
        errors.append("adapter requires a non-empty id")
    status = adapter.get("status")
    if status not in {BLOCKED_STATUS, READY_STATUS}:
        errors.append(f"adapter status must be {BLOCKED_STATUS} or {READY_STATUS}")

    action_spec, action_spec_errors = resolve_action_spec(adapter.get("action_spec_path"))
    errors.extend(action_spec_errors)
    operation: dict[str, Any] | None = None
    if action_spec is not None:
        if action_spec.get("lifecycle") != "curated":
            errors.append("controlled adapter requires a curated Action Spec")
        if action_spec.get("execution_family") != "hcloud":
            errors.append("controlled adapter currently supports only hcloud Action Specs")
        if action_spec.get("effect") == "read":
            errors.append("controlled adapter cannot target a read Action Spec")
        operation, catalog_errors = catalog_operation(action_spec)
        errors.extend(catalog_errors)
        if isinstance(operation, dict) and operation.get("read_only") is True:
            errors.append("controlled adapter cannot target a catalog read_only operation")

    mapping = adapter.get("request_mapping")
    mapping_gaps: list[str] = []
    candidate_bindings: list[Any] = []
    blocking_reasons: list[Any] = []
    if not isinstance(mapping, dict):
        errors.append("adapter requires a request_mapping object")
    else:
        if mapping.get("status") not in {BLOCKED_STATUS, READY_STATUS}:
            errors.append(f"request_mapping.status must be {BLOCKED_STATUS} or {READY_STATUS}")
        candidate_bindings = mapping.get("candidate_bindings", [])
        blocking_reasons = mapping.get("blocking_reasons", [])
        if not isinstance(candidate_bindings, list):
            errors.append("request_mapping.candidate_bindings must be a list")
            candidate_bindings = []
        if not isinstance(blocking_reasons, list) or not all(isinstance(item, str) and item for item in blocking_reasons):
            errors.append("request_mapping.blocking_reasons must be a list of non-empty strings")
            blocking_reasons = []

    binding_sources: set[str] = set()
    binding_targets: set[str] = set()
    catalog_parameters: set[str] = set()
    required_catalog_parameters: set[str] = set()
    if isinstance(operation, dict):
        params = operation.get("params")
        if isinstance(params, list):
            catalog_parameters = {
                item["name"] for item in params if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]
            }
        optional = operation.get("optional_params")
        if isinstance(optional, list):
            catalog_parameters.update(item for item in optional if isinstance(item, str) and item)
        required = operation.get("required_params")
        if isinstance(required, list):
            required_catalog_parameters = {item for item in required if isinstance(item, str) and item}
    for binding in candidate_bindings:
        if not isinstance(binding, dict):
            errors.append("each candidate binding must be an object")
            continue
        semantic_input = binding.get("semantic_input")
        catalog_parameter = binding.get("catalog_parameter")
        if not isinstance(semantic_input, str) or not semantic_input:
            errors.append("candidate binding requires semantic_input")
            continue
        if not isinstance(catalog_parameter, str) or not catalog_parameter:
            errors.append("candidate binding requires catalog_parameter")
            continue
        binding_sources.add(semantic_input)
        binding_targets.add(catalog_parameter)
        if catalog_parameters and catalog_parameter not in catalog_parameters:
            mapping_gaps.append(f"candidate binding targets unknown catalog parameter {catalog_parameter}")
    if action_spec is not None:
        preflight = action_spec.get("preflight")
        required_inputs = preflight.get("required_inputs") if isinstance(preflight, dict) else []
        if isinstance(required_inputs, list):
            for input_name in required_inputs:
                if isinstance(input_name, str) and input_name and input_name not in binding_sources:
                    mapping_gaps.append(f"required semantic input lacks a catalog binding: {input_name}")
    for parameter in sorted(required_catalog_parameters - binding_targets):
        mapping_gaps.append(f"required catalog parameter lacks a semantic binding: {parameter}")
    mapping_gaps = sorted(set(mapping_gaps))

    mapping_status = mapping.get("status") if isinstance(mapping, dict) else None
    if status == READY_STATUS and mapping_status == READY_STATUS:
        request_mapper = mapping.get("request_mapper")
        if not isinstance(request_mapper, str) or not request_mapper:
            errors.append("ready adapter requires a request_mapping.request_mapper")
        if blocking_reasons:
            errors.append("ready adapter must not retain blocking_reasons")
        if mapping_gaps:
            errors.append("ready adapter has unresolved request mapping gaps")
    elif status == BLOCKED_STATUS:
        if not blocking_reasons:
            errors.append("blocked adapter must explain its blocking_reasons")

    verification_profile = adapter.get("verification_profile")
    if action_spec is not None and verification_profile != action_spec.get("verification_profile"):
        errors.append("adapter verification_profile must match its Action Spec")
    if len(registry_requirements) < 4 or not all(isinstance(item, str) and item for item in registry_requirements):
        errors.append("registry host_authority_requirements must contain at least four non-empty strings")

    readiness = READY_STATUS if not errors and not mapping_gaps and status == READY_STATUS else BLOCKED_STATUS
    return {
        "id": adapter_id if isinstance(adapter_id, str) else None,
        "status": readiness,
        "declared_status": status,
        "action_spec_id": action_spec.get("id") if action_spec else None,
        "mapping_gaps": mapping_gaps,
        "request_mapper": mapping.get("request_mapper") if isinstance(mapping, dict) else None,
        "blocking_reasons": blocking_reasons,
        "errors": sorted(set(errors)),
    }


def audit_registry(registry: dict[str, Any]) -> dict[str, Any]:
    """Audit all adapter readiness without reading credentials or calling cloud tools."""
    root_errors: list[str] = []
    if registry.get("schema_version") != 1:
        root_errors.append("schema_version must be 1")
    for field in ("id", "version", "description"):
        if not isinstance(registry.get(field), str) or not registry[field]:
            root_errors.append(f"registry requires a non-empty {field}")
    requirements = registry.get("host_authority_requirements")
    if not isinstance(requirements, list):
        root_errors.append("host_authority_requirements must be a list")
        requirements = []
    adapters = registry.get("adapters")
    if not isinstance(adapters, list) or not adapters:
        root_errors.append("registry requires a non-empty adapters list")
        adapters = []
    results = [audit_adapter(adapter, requirements) for adapter in adapters]
    identifiers = [result["id"] for result in results if result["id"]]
    if len(identifiers) != len(set(identifiers)):
        root_errors.append("adapter ids must be unique")
    ready = [result["id"] for result in results if result["status"] == READY_STATUS]
    malformed = [result["id"] for result in results if result["errors"]]
    return {
        "success": not root_errors and not malformed,
        "schema_version": "controlled-adapter-audit/v1",
        "registry_id": registry.get("id"),
        "registry_fingerprint": hcloud_unified_contracts.fingerprint(registry),
        "controlled_submit_status": "ready_for_selected_handoffs" if ready else "no_adapter_ready",
        "adapter_count": len(results),
        "ready_for_handoff": ready,
        "blocked_adapter_ids": [result["id"] for result in results if result["status"] != READY_STATUS],
        "root_errors": sorted(set(root_errors)),
        "adapters": results,
        "execution_boundary": "Local readiness audit only; no cloud tool, subprocess, credential, or network request was used.",
    }


def find_adapter_audit(report: dict[str, Any], action_spec_id: str) -> dict[str, Any] | None:
    """Return the one audited adapter associated with an Action Spec ID."""
    matches = [item for item in report.get("adapters", []) if item.get("action_spec_id") == action_spec_id]
    return copy.deepcopy(matches[0]) if len(matches) == 1 else None
