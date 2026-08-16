#!/usr/bin/env python3
"""Plan and optionally execute guarded non-ECS Huawei Cloud changes."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import hcloud_async_job_wait
import hcloud_change_state
import hcloud_common
import hcloud_resource_discovery
import hcloud_resource_ledger
import hcloud_resource_query
import hcloud_run_journal
import hcloud_service_change_plan

VERIFY_PROFILES = {
    "VPC": [
        ("SecurityGroupRule", "ShowSecurityGroupRule", {"security_group_rule_id": ("security_group_rule.id", "security_group_rule_id", "rule_id", "id")}),
        ("SecurityGroup", "ShowSecurityGroup", {"security_group_id": ("security_group.id", "security_group_id", "id")}),
        ("Subnet", "ShowSubnet", {"subnet_id": ("subnet.id", "subnet_id", "id")}),
        ("Vpc", "ShowVpc", {"vpc_id": ("vpc.id", "vpc_id", "id")}),
    ],
    "ELB": [
        ("Certificate", "ShowCertificate", {"certificate_id": ("certificate.id", "certificate_id", "id")}),
        ("HealthMonitor", "ShowHealthMonitor", {"healthmonitor_id": ("healthmonitor.id", "healthmonitor_id", "id")}),
        ("LoadBalancer", "ShowLoadBalancer", {"loadbalancer_id": ("loadbalancer.id", "loadbalancer_id", "id")}),
        ("Listener", "ShowListener", {"listener_id": ("listener.id", "listener_id", "id")}),
        ("Member", "ShowMember", {"pool_id": ("pool.id", "pool_id"), "member_id": ("member.id", "member_id", "id")}),
        ("Pool", "ShowPool", {"pool_id": ("pool.id", "pool_id", "id")}),
    ],
    "EVS": [
        ("Snapshot", "ShowSnapshot", {"snapshot_id": ("snapshot.id", "snapshot_id", "id")}),
        ("Volume", "ShowVolume", {"volume_id": ("volume.id", "volume_id", "id")}),
    ],
    "NAT": [
        ("DnatRule", "ShowNatGatewayDnatRule", {"dnat_rule_id": ("dnat_rule.id", "dnat_rule_id", "id")}),
        ("SnatRule", "ShowNatGatewaySnatRule", {"snat_rule_id": ("snat_rule.id", "snat_rule_id", "id")}),
        ("NatGateway", "ShowNatGateway", {"nat_gateway_id": ("nat_gateway.id", "nat_gateway_id", "id")}),
    ],
    "RDS": [
        ("Configuration", "ShowConfiguration", {"config_id": ("configuration.id", "config_id", "id")}),
        ("BackupPolicy", "ShowBackupPolicy", {"instance_id": ("instance.id", "instance_id", "id")}),
        ("InstanceName", "ShowInstanceConfiguration", {"instance_id": ("instance.id", "instance_id", "id")}),
        ("Instance", "ShowInstanceConfiguration", {"instance_id": ("instance.id", "instance_id", "id")}),
    ],
    "CDN": [
        ("Domain", "ShowDomainDetail", {"domain_id": ("domain.id", "domain_id", "id")}),
    ],
    "DNS": [
        ("RecordSet", "ShowRecordSet", {"zone_id": ("zone.id", "zone_id"), "recordset_id": ("recordset.id", "recordset_id", "id")}),
    ],
    "SCM": [
        ("Certificate", "ShowCertificate", {"certificate_id": ("certificate.id", "certificate_id", "id")}),
    ],
}
EXPECT_ABSENT_PREFIXES = ("BatchDelete", "Delete", "Detach", "Disassociate", "Unbind")


def execute_command(command: list[str], timeout: int) -> dict[str, Any]:
    """Run one generated safe_exec command and parse its JSON result."""
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "success": False,
            "return_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "parsed_json": None,
            "parsed_json_error": "hcloud_safe_exec.py did not return valid JSON.",
        }


def append_journal_event(args: argparse.Namespace, event: dict[str, Any]) -> None:
    """Append one flow event to the configured journal when requested."""
    journal = getattr(args, "journal", None)
    if not journal:
        return
    hcloud_run_journal.append_event(Path(journal), event)


def normalize_param_name(value: str) -> str:
    """Normalize a parameter or JSON key name for matching."""
    return value.strip().lstrip("-").replace("-", "_").lower()


def parse_key_value(values: list[str], label: str) -> dict[str, str]:
    """Parse repeated KEY=VALUE arguments."""
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid {label}, expected KEY=VALUE: {value}")
        key, raw = value.split("=", 1)
        key = normalize_param_name(key)
        raw = raw.strip()
        if not key or not raw:
            raise ValueError(f"Invalid {label}, expected non-empty KEY=VALUE: {value}")
        parsed[key] = raw
    return parsed


def service_plan_args(args: argparse.Namespace) -> SimpleNamespace:
    """Convert guarded flow arguments to service change planner arguments."""
    return SimpleNamespace(
        service=args.service.upper(),
        operation=args.operation,
        region=args.region,
        project_id=args.project_id,
        profile=args.profile,
        json_input_file=args.json_input_file,
        arg=args.arg,
        no_dryrun=args.no_dryrun,
        allow_public_web=bool(getattr(args, "allow_public_web", False)),
        allow_unregistered=args.allow_unregistered,
    )


def submit_token_payload(args: argparse.Namespace, service_plan: dict[str, Any]) -> dict[str, Any]:
    """Return the exact plan fields that must match before submit execution."""
    commands = service_plan.get("commands", {})
    return {
        "service": args.service.upper(),
        "operation": service_plan.get("operation") or args.operation,
        "region": args.region,
        "project_id": args.project_id,
        "profile": args.profile,
        "allow_public_web": bool(getattr(args, "allow_public_web", False)),
        "submit": commands.get("submit"),
        "risk": service_plan.get("risk"),
    }


def expected_submit_token(args: argparse.Namespace, service_plan: dict[str, Any]) -> str:
    """Return the confirmation token for the current guarded submit plan."""
    return hcloud_common.stable_plan_token(submit_token_payload(args, service_plan))


def submit_guard_failure(
    args: argparse.Namespace,
    service_plan: dict[str, Any],
    submit_token: str,
) -> dict[str, Any] | None:
    """Return a structured guard failure when submit preconditions are not met."""
    if not args.execute_submit:
        return None
    if not args.confirm_submit:
        return {
            "success": False,
            "error": "Submit execution requires --confirm-submit.",
            "reason": "Cloud changes can affect cost, network reachability, availability, or data state.",
        }
    risk = service_plan.get("risk", {})
    if risk.get("hard_guard"):
        return {
            "success": False,
            "error": "Submit execution is blocked by a hard manual gate.",
            "reason": "This service or metadata category can affect security, identity, key, or governance state and requires a separate human-reviewed runbook or service-specific planner.",
        }
    if risk.get("dryrun_required") and not (args.execute_dryrun or args.skip_dryrun):
        return {
            "success": False,
            "error": "Submit execution requires a successful dry-run or --skip-dryrun.",
            "reason": "The planned operation is mutating and the risk gate marked dry-run as required.",
        }
    if getattr(args, "submit_token", None) != submit_token:
        return {
            "success": False,
            "error": "Submit execution requires a valid --submit-token from the current plan.",
            "reason": "The token binds submit execution to the exact reviewed cloud plan, target, and command.",
            "next_action": "Rebuild the plan, review it, then pass submit_guard.submit_token with --submit-token.",
        }
    return None


def operation_resource_name(operation: str) -> str:
    """Return the resource portion of a change operation name."""
    prefixes = (
        "BatchCreate",
        "BatchDelete",
        "BatchUpdate",
        "Disassociate",
        "Associate",
        "Create",
        "Update",
        "Delete",
        "Resize",
        "Retype",
        "Attach",
        "Detach",
        "Bind",
        "Unbind",
        "Apply",
    )
    for prefix in prefixes:
        if operation.startswith(prefix):
            return operation[len(prefix):]
    return operation


def expects_absent_after_change(operation: str) -> bool:
    """Return True when a change verification should accept an absent resource."""
    return operation.startswith(EXPECT_ABSENT_PREFIXES)


def verification_not_found(plan: dict[str, Any]) -> bool:
    """Return True when an executed verification failed because the resource is absent."""
    result = plan.get("result")
    if not isinstance(result, dict):
        return False
    details = result.get("error_details")
    if isinstance(details, dict) and details.get("category") == "not_found":
        return True
    cloud_error = result.get("cloud_error")
    if isinstance(cloud_error, dict):
        combined = f"{cloud_error.get('code') or ''} {cloud_error.get('message') or ''}".lower()
        return "notfound" in combined or "not found" in combined or "does not exist" in combined
    text = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}".lower()
    return "notfound" in text or "not found" in text or "does not exist" in text


def profile_token_matches(token: str, resource_name: str) -> bool:
    """Return whether a verify profile token matches the changed resource."""
    token_value = token.lower()
    resource_value = resource_name.lower()
    plural_token = f"{token_value}s"
    return (
        resource_value == token_value
        or resource_value == plural_token
        or resource_value.endswith(token_value)
        or resource_value.endswith(plural_token)
    )


def infer_verify_profile(service: str, operation: str) -> dict[str, Any] | None:
    """Infer a service-specific read verification operation for a change operation."""
    resource_name = operation_resource_name(operation)
    for token, verify_operation, params in VERIFY_PROFILES.get(service, []):
        if profile_token_matches(token, resource_name):
            return {
                "verify_operation": verify_operation,
                "params": params,
                "matched_token": token,
                "matched_resource": resource_name,
            }
    return None


def get_path(value: Any, dotted_path: str) -> str | None:
    """Return a string value from a nested dictionary path when present."""
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    if isinstance(current, str) and current:
        return current
    if isinstance(current, (int, float)):
        return str(current)
    return None


def find_key_value(value: Any, candidate_key: str) -> str | None:
    """Return the first string value for a matching key in a JSON-like object."""
    normalized_candidate = normalize_param_name(candidate_key)
    if isinstance(value, dict):
        for key, child in value.items():
            if normalize_param_name(str(key)) == normalized_candidate:
                if isinstance(child, str) and child:
                    return child
                if isinstance(child, (int, float)):
                    return str(child)
            found = find_key_value(child, candidate_key)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_key_value(child, candidate_key)
            if found:
                return found
    return None


def find_candidate_value(value: Any, candidates: tuple[str, ...]) -> str | None:
    """Find a candidate identifier in a JSON-like submit result."""
    for candidate in candidates:
        if "." in candidate:
            found = get_path(value, candidate)
            if found:
                return found
    for candidate in candidates:
        found = find_key_value(value, candidate)
        if found:
            return found
    return None


def extracted_verify_params(profile: dict[str, Any], submit_result: dict[str, Any] | None) -> dict[str, str]:
    """Extract verification parameters from a submit result using a verify profile."""
    if not submit_result:
        return {}
    parsed_json = submit_result.get("parsed_json")
    if parsed_json is None:
        return {}
    extracted = {}
    for param_name, candidates in profile.get("params", {}).items():
        value = find_candidate_value(parsed_json, candidates)
        if value:
            extracted[param_name] = value
    return extracted


def build_verify_plan(
    args: argparse.Namespace,
    service_plan: dict[str, Any],
    submit_result: dict[str, Any] | None,
    stored_verify_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a service-specific post-change verification plan."""
    service = args.service.upper()
    requested_operation = service_plan.get("operation") or args.operation
    explicit_params = parse_key_value(args.verify_param, "--verify-param")
    inferred = infer_verify_profile(service, str(requested_operation))

    if args.verify_operation:
        profile = {
            "verify_operation": args.verify_operation,
            "params": {key: (key,) for key in explicit_params},
            "matched_token": "explicit",
        }
    elif inferred:
        profile = inferred
    else:
        return {
            "success": False,
            "service": service,
            "operation": requested_operation,
            "error": "No service-specific verification profile is registered for this change operation.",
            "next_actions": [
                "Pass --verify-operation and --verify-param KEY=VALUE to build an explicit post-change verification query.",
                "Use the post_change_readiness_plan as a coarse service-level fallback.",
            ],
        }

    params = {
        **extracted_verify_params(profile, submit_result),
        **(stored_verify_params or {}),
        **explicit_params,
    }
    verify_args = SimpleNamespace(
        service=service,
        operation=profile["verify_operation"],
        param=[f"{key}={value}" for key, value in sorted(params.items())],
        arg=[],
        region=args.region,
        project_id=args.project_id,
        profile=args.profile,
        execute=args.execute_verify,
        timeout=args.timeout,
        allow_sensitive_read=False,
    )
    plan = hcloud_resource_query.build_plan(verify_args)
    plan["verification_profile"] = {
        "change_operation": requested_operation,
        "matched_token": profile.get("matched_token"),
        "matched_resource": profile.get("matched_resource"),
        "inferred_operation": profile["verify_operation"],
        "param_sources": {
            "explicit": sorted(explicit_params),
            "submit_result": sorted(set(params) - set(explicit_params)),
        },
        "expect_absent": expects_absent_after_change(str(requested_operation)),
    }
    if plan["verification_profile"]["expect_absent"]:
        plan["verification_profile"]["verification_intent"] = "expect_absent_or_detached_state"
        plan.setdefault("next_actions", []).append(
            "For delete, detach, disassociate, or unbind operations, a not_found response can be the expected verification outcome."
        )
        if args.execute_verify and not plan.get("success") and verification_not_found(plan):
            plan["success"] = True
            plan["absent_state_confirmed"] = True
            plan["verification_profile"]["absent_state_confirmed"] = True
    return plan


def lifecycle_state_context(
    args: argparse.Namespace,
    service_plan: dict[str, Any],
) -> dict[str, Any] | None:
    """Prepare durable state for one exact guarded-flow step when configured."""
    state_file = getattr(args, "state_file", None)
    workflow_id = getattr(args, "workflow_id", None)
    step_id = getattr(args, "step_id", None)
    if not any((state_file, workflow_id, step_id)):
        return None
    if not all((state_file, workflow_id, step_id)):
        raise ValueError(
            "--state-file, --workflow-id, and --step-id must be provided together."
        )
    fingerprint_payload = submit_token_payload(args, service_plan)
    fingerprint = hcloud_change_state.request_fingerprint(fingerprint_payload)
    prepared = hcloud_change_state.prepare_step(
        Path(state_file),
        workflow_id=str(workflow_id),
        step_id=str(step_id),
        fingerprint=fingerprint,
        request_summary={
            "service": args.service.upper(),
            "operation": service_plan.get("operation") or args.operation,
            "region": args.region,
            "project_id": args.project_id,
            "profile": args.profile,
        },
    )
    lifecycle = {
        "state_file": str(state_file),
        "workflow_id": str(workflow_id),
        "step_id": str(step_id),
        "fingerprint": fingerprint,
        **prepared,
    }
    ledger_values = (
        getattr(args, "ledger_file", None),
        getattr(args, "resource_role", None),
    )
    if any(ledger_values) and not all(ledger_values):
        raise ValueError("--ledger-file and --resource-role must be provided together.")
    if all(ledger_values):
        cleanup_operation = getattr(args, "cleanup_operation", None)
        identifier_parameter = getattr(args, "identifier_parameter", None)
        hcloud_resource_ledger.register_resource(
            Path(str(ledger_values[0])),
            workflow_id=str(workflow_id),
            role=str(ledger_values[1]),
            service=args.service.upper(),
            region=args.region,
            project_id=args.project_id,
            expected_count=int(getattr(args, "expected_count", 1)),
            dependencies=getattr(args, "depends_on", []),
            request_fingerprint=fingerprint,
            cleanup_operation=cleanup_operation,
            identifier_parameter=identifier_parameter,
        )
        lifecycle["ledger_file"] = str(ledger_values[0])
        lifecycle["resource_role"] = str(ledger_values[1])
        lifecycle["identifier_parameter"] = identifier_parameter
    return lifecycle


def identifier_values(
    identifiers: dict[str, list[str]] | None,
    *keys: str,
) -> list[str]:
    """Return unique receipt values whose terminal key matches one of `keys`."""
    normalized_keys = {
        key.strip().replace("-", "_").lower()
        for key in keys
        if key and key.strip()
    }
    values: list[str] = []
    for path, candidates in (identifiers or {}).items():
        tail = str(path).rsplit(".", 1)[-1].replace("-", "_").lower()
        if tail not in normalized_keys:
            continue
        for candidate in candidates:
            if candidate and candidate not in values:
                values.append(candidate)
    return values


def lifecycle_verification_params(
    args: argparse.Namespace,
    service_plan: dict[str, Any],
    submit_result: dict[str, Any],
) -> dict[str, str]:
    """Return target parameters worth retaining after an accepted submit."""
    requested_operation = service_plan.get("operation") or args.operation
    profile = infer_verify_profile(args.service.upper(), str(requested_operation))
    extracted = extracted_verify_params(profile, submit_result) if profile else {}
    try:
        return {
            **extracted,
            **parse_key_value(args.verify_param, "--verify-param"),
        }
    except ValueError:
        return extracted


def _record_lifecycle_submit(
    lifecycle: dict[str, Any],
    *,
    submit_result: dict[str, Any],
    verification_params: dict[str, str],
) -> None:
    """Persist one submit receipt without retaining the complete response."""
    parsed_json = submit_result.get("parsed_json")
    identifiers = hcloud_change_state.extract_identifiers(parsed_json)
    step = hcloud_change_state.record_submit(
        Path(lifecycle["state_file"]),
        workflow_id=lifecycle["workflow_id"],
        step_id=lifecycle["step_id"],
        fingerprint=lifecycle["fingerprint"],
        success=bool(submit_result.get("success")),
        identifiers=identifiers,
        verification_params=verification_params,
    )
    lifecycle["step"] = step
    lifecycle["resume_action"] = "verify_existing"
    lifecycle["can_submit"] = False
    if lifecycle.get("ledger_file"):
        identifier_parameter = lifecycle.get("identifier_parameter")
        resource_ids = []
        if identifier_parameter and verification_params.get(identifier_parameter):
            resource_ids.append(verification_params[identifier_parameter])
        hcloud_resource_ledger.record_submission(
            Path(lifecycle["ledger_file"]),
            workflow_id=lifecycle["workflow_id"],
            role=lifecycle["resource_role"],
            accepted=True if submit_result.get("success") else None,
            identifiers=resource_ids,
            job_ids=identifier_values(
                identifiers,
                "job_id",
                "job_ids",
                "jobId",
                "jobIds",
            ),
        )


def _record_lifecycle_verification(
    lifecycle: dict[str, Any],
    *,
    success: bool,
    identifiers: list[str] | None = None,
) -> None:
    """Persist the resource verification result for a submitted step."""
    step = hcloud_change_state.record_verification(
        Path(lifecycle["state_file"]),
        workflow_id=lifecycle["workflow_id"],
        step_id=lifecycle["step_id"],
        fingerprint=lifecycle["fingerprint"],
        success=success,
    )
    lifecycle["step"] = step
    lifecycle["resume_action"] = "reuse_verified" if success else "verify_existing"
    lifecycle["can_submit"] = False
    if lifecycle.get("ledger_file"):
        hcloud_resource_ledger.record_verification(
            Path(lifecycle["ledger_file"]),
            workflow_id=lifecycle["workflow_id"],
            role=lifecycle["resource_role"],
            success=success,
            identifiers=identifiers or [],
            details={"verification_scope": "registered_resource_query"},
        )


def lifecycle_job_ids(lifecycle: dict[str, Any] | None) -> list[str]:
    """Return exact job identifiers retained for a prior submit."""
    if not lifecycle:
        return []
    identifiers = lifecycle.get("step", {}).get("identifiers")
    return identifier_values(
        identifiers if isinstance(identifiers, dict) else {},
        "job_id",
        "job_ids",
        "jobId",
        "jobIds",
    )


def async_wait_args(
    args: argparse.Namespace,
    *,
    job_id: str,
) -> SimpleNamespace:
    """Build generic async waiter arguments from guarded-flow options."""
    job_parameter = str(getattr(args, "async_job_param", "job_id") or "job_id")
    return SimpleNamespace(
        service=getattr(args, "async_service", None) or args.service,
        operation=args.async_operation,
        param=[
            *getattr(args, "async_param", []),
            f"{job_parameter}={job_id}",
        ],
        arg=[],
        region=args.region,
        project_id=args.project_id,
        profile=args.profile,
        status_path=getattr(args, "async_status_path", []),
        success_status=(
            getattr(args, "async_success_status", [])
            or list(hcloud_async_job_wait.DEFAULT_SUCCESS_STATUSES)
        ),
        failure_status=(
            getattr(args, "async_failure_status", [])
            or list(hcloud_async_job_wait.DEFAULT_FAILURE_STATUSES)
        ),
        interval=float(getattr(args, "async_interval", 10.0)),
        timeout=float(getattr(args, "async_timeout", 600.0)),
        command_timeout=args.timeout,
        max_command_failures=int(getattr(args, "max_command_failures", 3)),
    )


def _build_flow(args: argparse.Namespace) -> dict[str, Any]:
    """Build and optionally execute a guarded change flow."""
    service = args.service.upper()
    service_plan = hcloud_service_change_plan.build_service_plan(service_plan_args(args))
    result: dict[str, Any] = {
        "success": bool(service_plan.get("success")),
        "service": service,
        "operation": args.operation,
        "mode": "execute" if (args.execute_dryrun or args.execute_submit or args.execute_readiness or args.execute_verify or getattr(args, "execute_wait", False)) else "plan",
        "planning_only": True,
        "service_plan": service_plan,
        "submit_guard": {
            "execute_submit": args.execute_submit,
            "confirm_submit": args.confirm_submit,
            "skip_dryrun": args.skip_dryrun,
        },
        "next_steps": [
            "Review the service_plan risk, dry-run command, target project, and rollback expectations.",
            "Run --execute-dryrun first when the operation supports dry-run.",
            "Only use --execute-submit --confirm-submit after explicit user approval for this exact cloud change.",
            "Run --execute-verify with --verify-param when a service-specific target ID is known.",
            "Run --execute-readiness after submit to execute the read-only post-change smoke plan.",
        ],
    }
    if not service_plan.get("success"):
        return result
    if service_plan.get("delegated_planner"):
        result["success"] = False
        result["error"] = "This service uses a dedicated planner; use delegated_planner instead of the generic guarded flow."
        return result

    commands = service_plan.get("commands", {})
    if not commands.get("dryrun_or_plan") or not commands.get("submit"):
        result["success"] = False
        result["error"] = "Service plan did not produce dry-run/submit commands."
        return result

    try:
        lifecycle = lifecycle_state_context(args, service_plan)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result["success"] = False
        result["lifecycle_state_error"] = str(exc)
        return result
    if lifecycle:
        result["lifecycle_state"] = lifecycle
        if lifecycle["resume_action"] == "fingerprint_mismatch":
            result["success"] = False
            result["error"] = (
                "The persisted step belongs to a different cloud request. "
                "Use a new step_id or restore the original exact plan."
            )
            return result

    submit_token = expected_submit_token(args, service_plan)
    result["submit_guard"].update(
        {
            "submit_token": submit_token,
            "submit_token_required": True,
            "submit_token_provided": bool(getattr(args, "submit_token", None)),
        }
    )
    result["next_steps"][2] = (
        "Only use --execute-submit --confirm-submit --submit-token "
        f"{submit_token} after explicit user approval for this exact cloud change."
    )

    guard_failure = submit_guard_failure(args, service_plan, submit_token)
    if guard_failure:
        result["success"] = False
        result["submit_guard_failure"] = guard_failure
        return result

    dryrun_result: dict[str, Any] | None = None
    if args.execute_dryrun:
        dryrun_result = execute_command(commands["dryrun_or_plan"], args.timeout)
        result["dryrun"] = dryrun_result
        result["dryrun_command_shell"] = shlex.join(commands["dryrun_or_plan"])
        append_journal_event(
            args,
            {
                "type": "command",
                "stage": "dryrun",
                "service": service,
                "operation": args.operation,
                "success": bool(dryrun_result.get("success")),
                "command": commands["dryrun_or_plan"],
                "result": dryrun_result,
            },
        )
        if not dryrun_result.get("success"):
            result["success"] = False
            result["next_steps"].append("Dry-run failed. Inspect dryrun.error_details/advice before changing arguments.")
            return result

    submit_result: dict[str, Any] | None = None
    stored_verify_params: dict[str, str] = {}
    if args.execute_submit:
        result["planning_only"] = False
        if lifecycle and not lifecycle["can_submit"]:
            step = lifecycle["step"]
            stored_verify_params = dict(step.get("verification_params") or {})
            result["submit_resume"] = {
                "submit_was_not_repeated": True,
                "resume_action": lifecycle["resume_action"],
                "prior_status": step.get("status"),
                "identifiers": step.get("identifiers") or {},
            }
        else:
            submit_result = execute_command(commands["submit"], args.timeout)
            result["submit"] = submit_result
            result["submit_command_shell"] = shlex.join(commands["submit"])
            append_journal_event(
                args,
                {
                    "type": "command",
                    "stage": "submit",
                    "service": service,
                    "operation": args.operation,
                    "success": bool(submit_result.get("success")),
                    "command": commands["submit"],
                    "result": submit_result,
                },
            )
            if lifecycle:
                stored_verify_params = lifecycle_verification_params(
                    args,
                    service_plan,
                    submit_result,
                )
                _record_lifecycle_submit(
                    lifecycle,
                    submit_result=submit_result,
                    verification_params=stored_verify_params,
                )
            if not submit_result.get("success"):
                result["success"] = False
                if lifecycle:
                    result["next_steps"].append(
                        "Submit result is ambiguous. Read back the recorded target or scope before any retry."
                    )
                else:
                    result["next_steps"].append("Submit failed. Inspect submit.error_details/advice before retrying.")
                return result

    if getattr(args, "execute_wait", False):
        if not getattr(args, "async_operation", None):
            result["success"] = False
            result["async_wait"] = {
                "success": False,
                "classification": "configuration_error",
                "error": "--execute-wait requires --async-operation.",
            }
            return result
        job_ids = lifecycle_job_ids(lifecycle)
        if not job_ids:
            result["success"] = False
            result["async_wait"] = {
                "success": False,
                "classification": "identifier_missing",
                "error": "No exact submit job_id is available for async convergence.",
            }
            return result
        async_result = hcloud_async_job_wait.wait_for_job(
            async_wait_args(args, job_id=job_ids[0])
        )
        result["async_wait"] = async_result
        if lifecycle and lifecycle.get("ledger_file"):
            final_identifiers = async_result.get("final_identifiers")
            identifier_parameter = lifecycle.get("identifier_parameter")
            hcloud_resource_ledger.record_submission(
                Path(lifecycle["ledger_file"]),
                workflow_id=lifecycle["workflow_id"],
                role=lifecycle["resource_role"],
                accepted=True,
                identifiers=identifier_values(
                    final_identifiers if isinstance(final_identifiers, dict) else {},
                    str(identifier_parameter or ""),
                ),
                job_ids=job_ids,
            )
        if not async_result.get("success"):
            result["success"] = False
            return result

    try:
        verify_plan = build_verify_plan(
            args,
            service_plan,
            submit_result,
            stored_verify_params,
        )
    except ValueError as exc:
        result["success"] = False
        result["post_change_verification"] = {"success": False, "error": str(exc)}
        return result
    result["post_change_verification"] = verify_plan
    if args.execute_verify:
        result["success"] = bool(verify_plan.get("success"))
        if lifecycle and str(lifecycle["step"].get("status")) in {
            "submitted",
            "submit_unknown",
            "verification_failed",
            "verified",
        }:
            identifier_parameter = lifecycle.get("identifier_parameter")
            verified_identifiers = []
            if identifier_parameter and stored_verify_params.get(
                identifier_parameter
            ):
                verified_identifiers.append(
                    stored_verify_params[identifier_parameter]
                )
            _record_lifecycle_verification(
                lifecycle,
                success=bool(verify_plan.get("success")),
                identifiers=verified_identifiers,
            )
        append_journal_event(
            args,
            {
                "type": "verification",
                "stage": "verify",
                "service": service,
                "operation": verify_plan.get("operation"),
                "success": bool(verify_plan.get("success")),
                "result": verify_plan,
            },
        )
        if not result["success"]:
            return result

    readiness_plan = service_plan.get("read_only_smoke_plan")
    if readiness_plan:
        result["post_change_readiness_plan"] = readiness_plan
        if args.execute_readiness:
            readiness_result = hcloud_resource_discovery.execute_plan(readiness_plan, args.timeout)
            result["post_change_readiness"] = readiness_result
            result["success"] = bool(readiness_result.get("success"))
            append_journal_event(
                args,
                {
                    "type": "verification",
                    "stage": "readiness",
                    "service": service,
                    "operation": "read_only_smoke_plan",
                    "success": bool(readiness_result.get("success")),
                    "result": readiness_result,
                },
            )
    elif args.execute_readiness:
        result["success"] = False
        result["post_change_readiness"] = {
            "success": False,
            "error": "Service plan did not include a read-only smoke plan.",
        }
    return result


def finalize_flow_result(
    result: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Attach the platform's declared JSON outcome contract to every result."""
    result["result_contract"] = "json_outcome_v1"
    lifecycle = result.get("lifecycle_state")
    lifecycle_status = (
        str(lifecycle.get("step", {}).get("status") or "")
        if isinstance(lifecycle, dict)
        else ""
    )
    accepted_submit = bool(
        isinstance(result.get("submit"), dict)
        and result["submit"].get("success")
    ) or bool(result.get("submit_resume"))
    verification = result.get("post_change_verification")
    verification_succeeded = bool(
        getattr(args, "execute_verify", False)
        and isinstance(verification, dict)
        and verification.get("success")
    )
    if result.get("success"):
        if result.get("planning_only"):
            outcome_status = "succeeded"
        elif lifecycle_status == "verified" or verification_succeeded:
            outcome_status = "succeeded"
        elif getattr(args, "execute_submit", False) and accepted_submit:
            outcome_status = "partially_succeeded"
        else:
            outcome_status = "succeeded"
    elif accepted_submit or lifecycle_status in {
        "submitted",
        "submit_unknown",
        "verification_failed",
        "verified",
    }:
        outcome_status = "partially_succeeded"
    else:
        outcome_status = "failed"
    result["outcome_status"] = outcome_status
    return result


def build_flow(args: argparse.Namespace) -> dict[str, Any]:
    """Build the guarded flow and expose a declared machine-readable outcome."""
    return finalize_flow_result(_build_flow(args), args)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, help="Registered service name, for example VPC or ELB.")
    parser.add_argument("--operation", required=True, help="Registered change operation name.")
    parser.add_argument("--region", help="Explicit cli-region for generated commands.")
    parser.add_argument("--project-id", help="Optional project_id for generated commands.")
    parser.add_argument("--profile", help="Optional cli-profile for generated commands.")
    parser.add_argument("--json-input-file", help="Optional JSON body file for the change operation.")
    parser.add_argument("--arg", action="append", default=[], help="Additional raw hcloud argument token.")
    parser.add_argument("--no-dryrun", action="store_true", help="Do not add --dryrun to the generated dry-run command.")
    parser.add_argument(
        "--allow-public-web",
        action="store_true",
        help=(
            "Allow exact TCP 80/443 ingress from 0.0.0.0/0 for a user-confirmed public website plan. "
            "This does not replace --confirm-submit or --submit-token."
        ),
    )
    parser.add_argument("--allow-unregistered", action="store_true", help="Allow an operation not listed in the registry.")
    parser.add_argument("--execute-dryrun", action="store_true", help="Execute the generated dry-run command.")
    parser.add_argument("--execute-submit", action="store_true", help="Execute the generated submit command.")
    parser.add_argument("--confirm-submit", action="store_true", help="Required with --execute-submit.")
    parser.add_argument("--submit-token", help="Current plan token required with --execute-submit --confirm-submit.")
    parser.add_argument("--skip-dryrun", action="store_true", help="Allow submit without running dry-run first.")
    parser.add_argument("--execute-readiness", action="store_true", help="Execute the read-only post-change smoke plan.")
    parser.add_argument("--verify-operation", help="Explicit read operation for post-change resource verification.")
    parser.add_argument("--verify-param", action="append", default=[], help="Post-change verification parameter as KEY=VALUE. Can be repeated.")
    parser.add_argument("--execute-verify", action="store_true", help="Execute the post-change resource verification query.")
    parser.add_argument("--journal", help="Optional JSONL journal path for executed dry-run/submit/verify events.")
    parser.add_argument(
        "--state-file",
        help="Optional durable JSON state file; requires --workflow-id and --step-id.",
    )
    parser.add_argument(
        "--workflow-id",
        help="Stable task/workflow identifier used with --state-file.",
    )
    parser.add_argument(
        "--step-id",
        help="Stable logical change-step identifier used with --state-file.",
    )
    parser.add_argument("--ledger-file", help="Optional task-owned resource ledger file.")
    parser.add_argument("--resource-role", help="Logical resource role used with --ledger-file.")
    parser.add_argument("--expected-count", type=int, default=1)
    parser.add_argument("--depends-on", action="append", default=[])
    parser.add_argument("--cleanup-operation")
    parser.add_argument("--identifier-parameter")
    parser.add_argument("--execute-wait", action="store_true")
    parser.add_argument("--async-service")
    parser.add_argument("--async-operation")
    parser.add_argument("--async-job-param", default="job_id")
    parser.add_argument("--async-param", action="append", default=[])
    parser.add_argument("--async-status-path", action="append", default=[])
    parser.add_argument("--async-success-status", action="append", default=[])
    parser.add_argument("--async-failure-status", action="append", default=[])
    parser.add_argument("--async-interval", type=float, default=10.0)
    parser.add_argument("--async-timeout", type=float, default=600.0)
    parser.add_argument("--max-command-failures", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=120, help="Timeout for executed safe_exec commands.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be greater than 0.")
    state_values = (args.state_file, args.workflow_id, args.step_id)
    if any(state_values) and not all(state_values):
        parser.error("--state-file, --workflow-id, and --step-id must be provided together.")
    ledger_values = (args.ledger_file, args.resource_role)
    if any(ledger_values) and not all(ledger_values):
        parser.error("--ledger-file and --resource-role must be provided together.")
    if any(ledger_values) and not all(state_values):
        parser.error("--ledger-file requires durable workflow state arguments.")
    if bool(args.cleanup_operation) != bool(args.identifier_parameter):
        parser.error("--cleanup-operation and --identifier-parameter must be provided together.")
    if args.expected_count < 1:
        parser.error("--expected-count must be greater than 0.")
    if args.async_interval <= 0 or args.async_timeout <= 0:
        parser.error("async interval and timeout must be greater than 0.")
    if args.max_command_failures < 1:
        parser.error("--max-command-failures must be at least 1.")
    return args


def main() -> int:
    """Build and optionally execute the guarded change flow."""
    args = parse_args()
    result = build_flow(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
