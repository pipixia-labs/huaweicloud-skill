#!/usr/bin/env python3
"""Evaluate portable unified-operation risk and error policies without cloud calls."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
RISK_POLICY_PATH = ROOT_DIR / "references" / "unified-risk-policy.json"
ERROR_POLICY_PATH = ROOT_DIR / "references" / "unified-error-policy.json"
STAGE_ORDER = {"discover": 0, "plan": 1, "dry_run": 2, "submit": 3, "verify": 4}
MUTATING_EFFECTS = {"create", "update", "attach", "detach", "delete", "remote_execute", "external_generation"}


class UnifiedPolicyError(ValueError):
    """Raised when a local policy document is malformed or unavailable."""


def load_policy(path: Path) -> dict[str, Any]:
    """Load one machine-readable local policy document as a JSON object."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise UnifiedPolicyError(f"Cannot read policy document: {path}") from exc
    except json.JSONDecodeError as exc:
        raise UnifiedPolicyError(f"Invalid JSON policy document: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise UnifiedPolicyError(f"Policy document must be a JSON object: {path}")
    return value


def stage_at_most(left: str, right: str) -> str:
    """Return the earlier lifecycle stage, treating an unknown stage as plan-only."""
    left_order = STAGE_ORDER.get(left, STAGE_ORDER["plan"])
    right_order = STAGE_ORDER.get(right, STAGE_ORDER["plan"])
    return left if left_order <= right_order else right


def action_maturity(action_spec: dict[str, Any]) -> tuple[str, list[str]]:
    """Resolve a conservative maturity from lifecycle and optional semantic maturity."""
    lifecycle = str(action_spec.get("lifecycle") or "generated")
    maturity = action_spec.get("maturity")
    reasons: list[str] = []
    if not isinstance(maturity, str) or not maturity:
        return lifecycle, reasons
    resolved = stage_at_most_maturity(lifecycle, maturity)
    if lifecycle != maturity:
        reasons.append(
            "Action Spec lifecycle and maturity differ; the more restrictive value was used for planning."
        )
    return resolved, reasons


def stage_at_most_maturity(left: str, right: str) -> str:
    """Return the more restrictive known maturity, falling back to generated."""
    order = {"generated": 0, "reviewed": 1, "curated": 2, "deprecated": -1}
    left_order = order.get(left, 0)
    right_order = order.get(right, 0)
    if left_order <= right_order:
        return left if left in order else "generated"
    return right if right in order else "generated"


def list_of_strings(value: Any) -> list[str]:
    """Return non-empty strings from a value while preserving first-seen order."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item and item not in result:
            result.append(item)
    return result


def spec_preflight_requirements(action_spec: dict[str, Any]) -> tuple[list[str], bool | None]:
    """Extract semantic requirements without copying request parameters from the catalog."""
    preflight = action_spec.get("preflight")
    if not isinstance(preflight, dict):
        return [], None
    requirements = list_of_strings(preflight.get("required_inputs"))
    for item in list_of_strings(preflight.get("required_facts")):
        if item not in requirements:
            requirements.append(item)
    supports_dry_run = preflight.get("supports_dry_run")
    return requirements, supports_dry_run if isinstance(supports_dry_run, bool) else None


def requirement_items(ids: list[str], source: str) -> list[dict[str, str]]:
    """Create de-duplicated pending requirement items for an Action Plan."""
    return [{"id": item, "source": source, "status": "pending"} for item in dict.fromkeys(ids)]


def evaluate_action_spec(
    action_spec: dict[str, Any],
    cloud_context: dict[str, Any],
    *,
    risk_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic Action Plan policy decision without authorizing execution.

    The result deliberately separates a proposed next stage from execution authority.  In
    this implementation phase the latter is always ``not_implemented``; callers may use
    the result to render a plan but must not treat it as a submit permit.
    """
    policy = risk_policy or load_policy(RISK_POLICY_PATH)
    effect = str(action_spec.get("effect") or "update")
    maturity, maturity_reasons = action_maturity(action_spec)
    effect_policy = policy.get("effect_defaults", {}).get(effect, {"stage": "plan", "verification_required": True})
    ceiling = policy.get("maturity_stage_ceiling", {}).get(maturity, "plan")
    allowed_stage = stage_at_most(str(effect_policy.get("stage") or "plan"), str(ceiling))
    risk_policy_by_tag = policy.get("risk_tags", {})
    tags = list_of_strings(action_spec.get("risk_tags"))
    unknown_tags: list[str] = []
    risk_summary: list[dict[str, Any]] = []
    preflight_ids: list[str] = []
    verification_ids: list[str] = []
    output_ids: list[str] = [str(action_spec.get("output_policy") or "structured_summary")]
    manual_gate = False
    confirmation_mode: str | None = None

    for tag in tags:
        tag_policy = risk_policy_by_tag.get(tag)
        if not isinstance(tag_policy, dict):
            unknown_tags.append(tag)
            tag_policy = policy.get("unknown_tag_policy", {})
            allowed_stage = stage_at_most(allowed_stage, str(tag_policy.get("stage_cap") or "plan"))
        severity = str(tag_policy.get("severity") or "medium")
        tag_manual_gate = bool(tag_policy.get("manual_gate"))
        tag_confirmation = tag_policy.get("confirmation")
        if tag_manual_gate:
            manual_gate = True
            allowed_stage = "plan"
        if isinstance(tag_confirmation, str) and tag_confirmation:
            confirmation_mode = tag_confirmation if confirmation_mode is None else confirmation_mode
        preflight_ids.extend(list_of_strings(tag_policy.get("preflight")))
        verification_ids.extend(list_of_strings(tag_policy.get("verification")))
        output_ids.extend(list_of_strings(tag_policy.get("output")))
        risk_summary.append(
            {
                "tag": tag,
                "severity": severity,
                "status": "manual_gate" if tag_manual_gate else "needs_review",
            }
        )

    semantic_preflight, supports_dry_run = spec_preflight_requirements(action_spec)
    preflight_ids.extend(semantic_preflight)
    if effect in MUTATING_EFFECTS:
        preflight_ids.append("target_scope_review")
        confirmation_mode = confirmation_mode or "required_before_submit"
    if effect_policy.get("verification_required"):
        verification_ids.append(str(action_spec.get("verification_profile") or "service_readback"))

    if allowed_stage == "dry_run" and supports_dry_run is not True:
        allowed_stage = "plan"
        preflight_ids.append("dry_run_support_confirmation")
    missing_inputs = list_of_strings(cloud_context.get("missing_inputs"))
    required_missing = [item for item in semantic_preflight if item in missing_inputs]
    if required_missing and effect in MUTATING_EFFECTS:
        allowed_stage = "plan"

    if manual_gate:
        decision = "manual_gate"
    elif unknown_tags:
        decision = "plan_only_unknown_risk"
    elif allowed_stage == "discover":
        decision = "discovery_proposed"
    elif allowed_stage == "dry_run":
        decision = "dry_run_proposed"
    else:
        decision = "plan_only"

    confirmation_required = bool(confirmation_mode)
    if confirmation_required:
        confirmation = {
            "required": True,
            "mode": confirmation_mode,
            "status": "not_requested",
            "binding": "No confirmation token is issued in the plan-only policy phase.",
        }
    else:
        confirmation = {"required": False, "status": "not_required"}

    boundary = copy.deepcopy(policy.get("current_execution_boundary", {}))
    return {
        "policy_id": policy.get("id"),
        "policy_version": policy.get("version"),
        "decision": decision,
        "allowed_stage": allowed_stage,
        "execution_authority": boundary,
        "risk_summary": risk_summary,
        "unknown_risk_tags": unknown_tags,
        "maturity": maturity,
        "reasons": maturity_reasons,
        "missing_inputs": missing_inputs,
        "preflight": requirement_items(preflight_ids, "unified_risk_policy"),
        "confirmation": confirmation,
        "verification": requirement_items(verification_ids, "unified_risk_policy"),
        "output": requirement_items(output_ids, "unified_risk_policy"),
    }


def classify_operation_error(
    *,
    error_type: str | None = None,
    cloud_error_code: str | None = None,
    cloud_error_message: str | None = None,
    stage: str | None = None,
    error_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify an already-redacted operation error into a conservative next action."""
    policy = error_policy or load_policy(ERROR_POLICY_PATH)
    signal = " ".join(item for item in (cloud_error_code, cloud_error_message) if item).lower()
    result: dict[str, Any] = copy.deepcopy(policy.get("defaults", {}))
    source = "default"
    for rule in policy.get("cloud_code_patterns", []):
        if not isinstance(rule, dict) or not isinstance(rule.get("pattern"), str):
            continue
        if signal and re.search(rule["pattern"], signal, flags=re.IGNORECASE):
            result = {key: value for key, value in rule.items() if key != "pattern"}
            source = "cloud_code_pattern"
            break
    else:
        if error_type and isinstance(policy.get("error_types", {}).get(error_type), dict):
            result = copy.deepcopy(policy["error_types"][error_type])
            source = "error_type"

    stage_override = policy.get("stage_overrides", {}).get(stage or "", {}).get(result.get("category"))
    if isinstance(stage_override, dict):
        result.update(stage_override)
        source = f"{source}_with_stage_override"
    result.update(
        {
            "policy_id": policy.get("id"),
            "policy_version": policy.get("version"),
            "source": source,
            "stage": stage or "unknown",
            "automatic_retry_allowed": False,
        }
    )
    return result
