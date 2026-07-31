#!/usr/bin/env python3
"""Validate portable unified-operation contracts without executing cloud APIs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "references" / "contracts"
CONTRACT_NAMES = (
    "cloud-context",
    "action-spec",
    "action-plan",
    "execution-intent",
    "metadata-read-plan",
    "operation-result",
    "submission-authorization",
    "controlled-submit-handoff",
)
LIFECYCLES = {"generated", "reviewed", "curated", "deprecated"}
EXECUTION_FAMILIES = {"hcloud", "sdk", "terraform", "maas", "local"}
EFFECTS = {"read", "create", "update", "attach", "detach", "delete", "remote_execute", "external_generation"}
STAGES = {"discover", "plan", "dry_run", "submit", "verify", "govern"}
OUTCOMES = {"succeeded", "partially_succeeded", "blocked", "failed", "unknown"}
FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SECRET_KEY_EXACT = {
    "ak",
    "sk",
    "api_key",
    "apikey",
    "access_key",
    "secret_key",
    "access_token",
    "auth_token",
    "authorization",
    "security_token",
    "password",
    "passwd",
    "private_key",
    "credential",
    "credentials",
}
SECRET_KEY_PARTS = ("client_secret", "privatekey", "secretaccesskey", "bearertoken")
FORBIDDEN_ACTION_SPEC_FACT_FIELDS = {"method", "http_method", "path", "params", "request_params", "response_schema"}


class ContractValidationError(ValueError):
    """Raised when a contract input cannot be loaded as a JSON object."""


def canonical_json(value: Any) -> str:
    """Serialize a JSON-compatible value in the contract fingerprint format."""
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any, *, excluded_fields: set[str] | None = None) -> str:
    """Return a SHA-256 fingerprint without mutating the supplied value."""
    normalized = copy.deepcopy(value)
    if isinstance(normalized, dict):
        for field in excluded_fields or set():
            normalized.pop(field, None)
    return f"sha256:{hashlib.sha256(canonical_json(normalized).encode('utf-8')).hexdigest()}"


def is_secret_key(key: str) -> bool:
    """Detect keys that are not allowed to carry secret values in contracts."""
    normalized = key.strip().lower().replace("-", "_")
    compact = normalized.replace("_", "")
    return normalized in SECRET_KEY_EXACT or compact in SECRET_KEY_EXACT or any(part in compact for part in SECRET_KEY_PARTS)


def secret_field_paths(value: Any, prefix: str = "") -> list[str]:
    """Return paths with prohibited secret-bearing field names."""
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            is_redaction_marker = isinstance(child, str) and child == "***"
            if is_secret_key(str(key)) and child is not None and not is_redaction_marker:
                findings.append(path)
            findings.extend(secret_field_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(secret_field_paths(child, f"{prefix}[{index}]"))
    return findings


def load_document(path: Path) -> dict[str, Any]:
    """Load one JSON contract document as an object."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContractValidationError(f"Cannot read contract input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractValidationError(f"Invalid JSON contract input: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractValidationError("Contract input must be a JSON object.")
    return value


def expect_type(value: dict[str, Any], field: str, expected: type[Any], errors: list[str]) -> None:
    """Append a standard error when one required field has an unexpected type."""
    if field not in value:
        errors.append(f"missing required field: {field}")
    elif not isinstance(value[field], expected):
        errors.append(f"field {field} must be {expected.__name__}")


def expect_string(value: dict[str, Any], field: str, errors: list[str]) -> None:
    """Require one non-empty string field."""
    expect_type(value, field, str, errors)
    if isinstance(value.get(field), str) and not value[field].strip():
        errors.append(f"field {field} must not be empty")


def validate_cloud_context(document: dict[str, Any]) -> list[str]:
    """Validate the portable context shape and its no-secret boundary."""
    errors: list[str] = []
    if document.get("schema_version") != "cloud-context/v1":
        errors.append("schema_version must be cloud-context/v1")
    expect_string(document, "intent", errors)
    expect_type(document, "scope", dict, errors)
    for field in ("constraints",):
        if field in document and not isinstance(document[field], dict):
            errors.append(f"field {field} must be dict when present")
    for field in ("discovery_facts", "missing_inputs"):
        if field in document and not isinstance(document[field], list):
            errors.append(f"field {field} must be list when present")
    return errors


def validate_catalog_ref(catalog_ref: Any, errors: list[str]) -> None:
    """Validate the exact non-duplicating catalog reference used by an Action Spec."""
    if not isinstance(catalog_ref, dict):
        errors.append("catalog_ref must be an object")
        return
    for field in ("catalog_fingerprint", "service", "operation", "version"):
        expect_string(catalog_ref, field, errors)
    fingerprint_value = catalog_ref.get("catalog_fingerprint")
    if isinstance(fingerprint_value, str) and not FINGERPRINT_RE.fullmatch(fingerprint_value):
        errors.append("catalog_ref.catalog_fingerprint must be a sha256 fingerprint")
    extras = sorted(set(catalog_ref) - {"catalog_fingerprint", "service", "operation", "version"})
    if extras:
        errors.append(f"catalog_ref contains unsupported fields: {', '.join(extras)}")


def validate_action_spec(document: dict[str, Any]) -> list[str]:
    """Validate Action Spec semantics while forbidding copied API request facts."""
    errors: list[str] = []
    if document.get("schema_version") != "action-spec/v1":
        errors.append("schema_version must be action-spec/v1")
    expect_string(document, "id", errors)
    if isinstance(document.get("id"), str) and not re.fullmatch(r"[a-z0-9][a-z0-9._-]+", document["id"]):
        errors.append("id must use lowercase letters, digits, dot, underscore, or hyphen")
    lifecycle = document.get("lifecycle")
    if lifecycle not in LIFECYCLES:
        errors.append(f"lifecycle must be one of: {', '.join(sorted(LIFECYCLES))}")
    execution_family = document.get("execution_family")
    if execution_family not in EXECUTION_FAMILIES:
        errors.append(f"execution_family must be one of: {', '.join(sorted(EXECUTION_FAMILIES))}")
    effect = document.get("effect")
    if effect not in EFFECTS:
        errors.append(f"effect must be one of: {', '.join(sorted(EFFECTS))}")
    risk_tags = document.get("risk_tags")
    if not isinstance(risk_tags, list) or not all(isinstance(tag, str) and tag for tag in risk_tags):
        errors.append("risk_tags must be a list of non-empty strings")
    elif len(risk_tags) != len(set(risk_tags)):
        errors.append("risk_tags must not contain duplicates")
    tool_candidates = document.get("tool_candidates")
    if not isinstance(tool_candidates, list) or not tool_candidates:
        errors.append("tool_candidates must be a non-empty list")
    elif any(tool not in EXECUTION_FAMILIES for tool in tool_candidates):
        errors.append("tool_candidates contains an unsupported tool family")
    elif execution_family in EXECUTION_FAMILIES and execution_family not in tool_candidates:
        errors.append("tool_candidates must include execution_family")
    for field in ("preflight", "execution"):
        if field in document and not isinstance(document[field], dict):
            errors.append(f"field {field} must be an object when present")
    expect_string(document, "verification_profile", errors)
    expect_string(document, "output_policy", errors)
    if execution_family == "hcloud":
        if "catalog_ref" not in document:
            errors.append("hcloud Action Spec requires catalog_ref")
        else:
            validate_catalog_ref(document["catalog_ref"], errors)
    elif "catalog_ref" in document:
        validate_catalog_ref(document["catalog_ref"], errors)
    forbidden = sorted(FORBIDDEN_ACTION_SPEC_FACT_FIELDS & set(document))
    if forbidden:
        errors.append(f"Action Spec must reference rather than copy API facts: {', '.join(forbidden)}")
    return errors


def validate_action_plan(document: dict[str, Any]) -> list[str]:
    """Validate a task-specific Action Plan without treating it as authorization."""
    errors: list[str] = []
    if document.get("schema_version") != "action-plan/v1":
        errors.append("schema_version must be action-plan/v1")
    action_spec_ref = document.get("action_spec_ref")
    if not isinstance(action_spec_ref, dict):
        errors.append("action_spec_ref must be an object")
    else:
        expect_string(action_spec_ref, "id", errors)
        if action_spec_ref.get("lifecycle") not in LIFECYCLES:
            errors.append("action_spec_ref.lifecycle must be a valid lifecycle")
        plan_ref_fingerprint = action_spec_ref.get("fingerprint")
        if not isinstance(plan_ref_fingerprint, str) or not FINGERPRINT_RE.fullmatch(plan_ref_fingerprint):
            errors.append("action_spec_ref.fingerprint must be a sha256 fingerprint")
    for field in ("context_fingerprint",):
        value = document.get(field)
        if not isinstance(value, str) or not FINGERPRINT_RE.fullmatch(value):
            errors.append(f"{field} must be a sha256 fingerprint")
    allowed_stage = document.get("allowed_stage")
    if allowed_stage not in STAGES - {"govern"}:
        errors.append("allowed_stage must be discover, plan, dry_run, submit, or verify")
    for field in ("risk_summary", "missing_inputs", "preflight", "verification"):
        if not isinstance(document.get(field), list):
            errors.append(f"field {field} must be a list")
    if "confirmation" in document and not isinstance(document["confirmation"], dict):
        errors.append("confirmation must be an object when present")
    if "output" in document and not isinstance(document["output"], list):
        errors.append("output must be a list when present")
    for field in ("policy", "execution_authority"):
        if field in document and not isinstance(document[field], dict):
            errors.append(f"{field} must be an object when present")
    if "plan_fingerprint" in document:
        value = document["plan_fingerprint"]
        if not isinstance(value, str) or not FINGERPRINT_RE.fullmatch(value):
            errors.append("plan_fingerprint must be a sha256 fingerprint")
    if allowed_stage == "submit" and isinstance(action_spec_ref, dict):
        if action_spec_ref.get("lifecycle") != "curated":
            errors.append("submit stage requires a curated Action Spec reference")
        if not isinstance(document.get("confirmation"), dict):
            errors.append("submit stage requires a confirmation requirement object")
    return errors


def validate_operation_result(document: dict[str, Any]) -> list[str]:
    """Validate the shared result envelope and stage/outcome enumerations."""
    errors: list[str] = []
    if document.get("schema_version") != "operation-result/v1":
        errors.append("schema_version must be operation-result/v1")
    if document.get("stage") not in STAGES:
        errors.append("stage must be a supported lifecycle stage")
    if document.get("outcome") not in OUTCOMES:
        errors.append("outcome must be a supported outcome")
    for field in ("facts", "evidence", "risks", "gaps", "next_actions"):
        if not isinstance(document.get(field), list):
            errors.append(f"field {field} must be a list")
    if not isinstance(document.get("user_summary"), str):
        errors.append("user_summary must be a string")
    return errors


def validate_metadata_read_plan(document: dict[str, Any]) -> list[str]:
    """Validate a restricted read plan without treating it as execution authority."""
    errors: list[str] = []
    if document.get("schema_version") != "metadata-read-plan/v1":
        errors.append("schema_version must be metadata-read-plan/v1")
    action_spec_ref = document.get("action_spec_ref")
    if not isinstance(action_spec_ref, dict):
        errors.append("action_spec_ref must be an object")
    else:
        expect_string(action_spec_ref, "id", errors)
        if action_spec_ref.get("lifecycle") not in {"reviewed", "curated"}:
            errors.append("metadata read requires a reviewed or curated Action Spec reference")
        fingerprint_value = action_spec_ref.get("fingerprint")
        if not isinstance(fingerprint_value, str) or not FINGERPRINT_RE.fullmatch(fingerprint_value):
            errors.append("action_spec_ref.fingerprint must be a sha256 fingerprint")
    context_fingerprint = document.get("context_fingerprint")
    if not isinstance(context_fingerprint, str) or not FINGERPRINT_RE.fullmatch(context_fingerprint):
        errors.append("context_fingerprint must be a sha256 fingerprint")
    validate_catalog_ref(document.get("catalog_ref"), errors)
    admission = document.get("admission")
    if not isinstance(admission, dict):
        errors.append("admission must be an object")
    else:
        if admission.get("status") not in {"blocked", "eligible_for_future_adapter"}:
            errors.append("admission.status must be blocked or eligible_for_future_adapter")
        if not isinstance(admission.get("reasons"), list):
            errors.append("admission.reasons must be a list")
    if not isinstance(document.get("query_requirements"), list):
        errors.append("query_requirements must be a list")
    for field in ("output_policy", "execution_authority"):
        if not isinstance(document.get(field), dict):
            errors.append(f"{field} must be an object")
    plan_fingerprint = document.get("plan_fingerprint")
    if plan_fingerprint is not None and (
        not isinstance(plan_fingerprint, str) or not FINGERPRINT_RE.fullmatch(plan_fingerprint)
    ):
        errors.append("plan_fingerprint must be a sha256 fingerprint when present")
    return errors


def validate_action_spec_ref(value: Any, errors: list[str], label: str, *, curated_only: bool = False) -> None:
    """Validate a fingerprinted Action Spec reference reused by admission contracts."""
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return
    expect_string(value, "id", errors)
    lifecycle = value.get("lifecycle")
    if lifecycle not in LIFECYCLES:
        errors.append(f"{label}.lifecycle must be a valid lifecycle")
    elif curated_only and lifecycle != "curated":
        errors.append(f"{label}.lifecycle must be curated")
    fingerprint_value = value.get("fingerprint")
    if not isinstance(fingerprint_value, str) or not FINGERPRINT_RE.fullmatch(fingerprint_value):
        errors.append(f"{label}.fingerprint must be a sha256 fingerprint")


def validate_execution_intent(document: dict[str, Any]) -> list[str]:
    """Validate a secret-free task execution intent without interpreting it as a command."""
    errors: list[str] = []
    if document.get("schema_version") != "execution-intent/v1":
        errors.append("schema_version must be execution-intent/v1")
    family = document.get("execution_family")
    if family not in EXECUTION_FAMILIES:
        errors.append("execution_family must be a supported tool family")
    validate_action_spec_ref(document.get("action_spec_ref"), errors, "action_spec_ref")
    if not isinstance(document.get("scope"), dict):
        errors.append("scope must be an object")
    if not isinstance(document.get("parameters"), dict):
        errors.append("parameters must be an object")
    if "idempotency" in document and not isinstance(document["idempotency"], dict):
        errors.append("idempotency must be an object when present")
    if family == "hcloud":
        validate_catalog_ref(document.get("catalog_ref"), errors)
    elif "catalog_ref" in document:
        validate_catalog_ref(document.get("catalog_ref"), errors)
    return errors


def validate_submission_authorization(document: dict[str, Any]) -> list[str]:
    """Validate a prepared confirmation binding without granting runtime execution."""
    errors: list[str] = []
    if document.get("schema_version") != "submission-authorization/v1":
        errors.append("schema_version must be submission-authorization/v1")
    validate_action_spec_ref(document.get("action_spec_ref"), errors, "action_spec_ref", curated_only=True)
    for field in ("action_plan_fingerprint", "execution_intent_fingerprint"):
        value = document.get(field)
        if not isinstance(value, str) or not FINGERPRINT_RE.fullmatch(value):
            errors.append(f"{field} must be a sha256 fingerprint")
    confirmation = document.get("confirmation")
    if not isinstance(confirmation, dict):
        errors.append("confirmation must be an object")
    else:
        if confirmation.get("status") != "confirmed":
            errors.append("confirmation.status must be confirmed")
        expect_string(confirmation, "approval_id", errors)
        for field in (
            "reviewed_action_plan_fingerprint",
            "reviewed_execution_intent_fingerprint",
            "preflight_evidence_fingerprint",
        ):
            value = confirmation.get(field)
            if not isinstance(value, str) or not FINGERPRINT_RE.fullmatch(value):
                errors.append(f"confirmation.{field} must be a sha256 fingerprint")
    for field in ("admission", "execution_authority"):
        if not isinstance(document.get(field), dict):
            errors.append(f"{field} must be an object")
    if "authorization_fingerprint" in document:
        value = document["authorization_fingerprint"]
        if not isinstance(value, str) or not FINGERPRINT_RE.fullmatch(value):
            errors.append("authorization_fingerprint must be a sha256 fingerprint when present")
    return errors


def validate_controlled_submit_handoff(document: dict[str, Any]) -> list[str]:
    """Validate a host handoff candidate without treating it as a submit permit."""
    errors: list[str] = []
    if document.get("schema_version") != "controlled-submit-handoff/v1":
        errors.append("schema_version must be controlled-submit-handoff/v1")
    adapter_ref = document.get("adapter_ref")
    if not isinstance(adapter_ref, dict):
        errors.append("adapter_ref must be an object")
    else:
        expect_string(adapter_ref, "id", errors)
        registry_fingerprint = adapter_ref.get("registry_fingerprint")
        if not isinstance(registry_fingerprint, str) or not FINGERPRINT_RE.fullmatch(registry_fingerprint):
            errors.append("adapter_ref.registry_fingerprint must be a sha256 fingerprint")
    validate_action_spec_ref(document.get("action_spec_ref"), errors, "action_spec_ref", curated_only=True)
    validate_catalog_ref(document.get("catalog_ref"), errors)
    for field in ("submission_authorization_fingerprint", "execution_intent_fingerprint"):
        value = document.get(field)
        if not isinstance(value, str) or not FINGERPRINT_RE.fullmatch(value):
            errors.append(f"{field} must be a sha256 fingerprint")
    request_preparation = document.get("request_preparation")
    if not isinstance(request_preparation, dict):
        errors.append("request_preparation must be an object")
    else:
        expect_string(request_preparation, "mapping_id", errors)
        request_fingerprint = request_preparation.get("request_fingerprint")
        if not isinstance(request_fingerprint, str) or not FINGERPRINT_RE.fullmatch(request_fingerprint):
            errors.append("request_preparation.request_fingerprint must be a sha256 fingerprint")
        if request_preparation.get("payload_delivery") != "host_rederives_from_fingerprint_bound_execution_intent":
            errors.append("request_preparation.payload_delivery must require host re-derivation from Execution Intent")
    host_requirements = document.get("host_authority_requirements")
    if not isinstance(host_requirements, dict):
        errors.append("host_authority_requirements must be an object")
    else:
        if host_requirements.get("verification_location") != "host_adapter":
            errors.append("host_authority_requirements.verification_location must be host_adapter")
        requirements = host_requirements.get("requirements")
        if not isinstance(requirements, list) or len(requirements) < 4:
            errors.append("host_authority_requirements.requirements must contain at least four requirements")
        elif not all(isinstance(item, str) and item for item in requirements):
            errors.append("host_authority_requirements.requirements must contain non-empty strings")
        elif len(requirements) != len(set(requirements)):
            errors.append("host_authority_requirements.requirements must not contain duplicates")
    execution_authority = document.get("execution_authority")
    if not isinstance(execution_authority, dict):
        errors.append("execution_authority must be an object")
    else:
        if execution_authority.get("mode") != "plan_only":
            errors.append("controlled submit handoff must retain execution_authority.mode=plan_only")
        if execution_authority.get("submission_authority") != "host_adapter_required":
            errors.append("controlled submit handoff requires host_adapter_required submission authority")
    if "handoff_fingerprint" in document:
        value = document["handoff_fingerprint"]
        if not isinstance(value, str) or not FINGERPRINT_RE.fullmatch(value):
            errors.append("handoff_fingerprint must be a sha256 fingerprint when present")
        elif value != fingerprint(document, excluded_fields={"handoff_fingerprint"}):
            errors.append("handoff_fingerprint does not match the handoff content")
    return errors


VALIDATORS = {
    "cloud-context": validate_cloud_context,
    "action-spec": validate_action_spec,
    "action-plan": validate_action_plan,
    "execution-intent": validate_execution_intent,
    "metadata-read-plan": validate_metadata_read_plan,
    "operation-result": validate_operation_result,
    "submission-authorization": validate_submission_authorization,
    "controlled-submit-handoff": validate_controlled_submit_handoff,
}


def validate_contract(contract: str, document: dict[str, Any]) -> dict[str, Any]:
    """Validate one named contract and return portable structured diagnostics."""
    if contract not in VALIDATORS:
        raise ContractValidationError(f"Unsupported contract: {contract}")
    errors = VALIDATORS[contract](document)
    secret_paths = secret_field_paths(document)
    errors.extend(f"secret-bearing field is not allowed in contracts: {path}" for path in secret_paths)
    errors = sorted(set(errors))
    excluded = {"plan_fingerprint"} if contract == "action-plan" else set()
    return {
        "success": not errors,
        "contract": contract,
        "errors": errors,
        "canonical_fingerprint": fingerprint(document, excluded_fields=excluded),
        "validation_boundary": "Schema and pure semantic validation only; this result does not grant execution permission.",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the pure contract-validation command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, choices=CONTRACT_NAMES)
    parser.add_argument("--input", type=Path, required=True, help="JSON document to validate.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Validate one contract document without contacting any external system."""
    args = parse_args(argv)
    try:
        result = validate_contract(args.contract, load_document(args.input))
    except ContractValidationError as exc:
        result = {"success": False, "contract": args.contract, "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
