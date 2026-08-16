#!/usr/bin/env python3
"""Plan, optionally apply, and verify guarded EIP change operations."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import hcloud_change_state
import hcloud_common
import hcloud_resource_ledger
import hcloud_resource_query
import hcloud_run_journal
import hcloud_service_change_plan

CREATE_CLEANUP_OPERATIONS = {
    "CreatePublicip": "DeletePublicip",
    "CreateSharedBandwidth": "DeleteSharedBandwidth",
    "NeutronCreateFloatingIp": "NeutronDeleteFloatingIp",
}


def execute_command(command: list[str], timeout: int) -> dict[str, Any]:
    """Run one generated safe_exec command and parse its JSON result."""
    return hcloud_common.run_json_command(command, timeout)


def append_journal_event(args: argparse.Namespace, event: dict[str, Any]) -> None:
    """Append one flow event to the configured journal when requested."""
    journal = getattr(args, "journal", None)
    if not journal:
        return
    hcloud_run_journal.append_event(Path(journal), event)


def service_plan_args(args: argparse.Namespace) -> SimpleNamespace:
    """Convert EIP flow arguments to service change planner arguments."""
    return SimpleNamespace(
        service="EIP",
        operation=args.operation,
        region=args.region,
        project_id=args.project_id,
        profile=args.profile,
        json_input_file=args.json_input_file,
        arg=args.arg,
        no_dryrun=args.no_dryrun,
        allow_unregistered=args.allow_unregistered,
    )


def find_publicip_id(value: Any) -> str | None:
    """Extract a publicip ID from a known EIP response shape."""
    if isinstance(value, dict):
        publicip = value.get("publicip")
        if isinstance(publicip, dict):
            for key in ("id", "publicip_id"):
                candidate = publicip.get(key)
                if isinstance(candidate, str) and candidate:
                    return candidate
        for key in ("publicip_id",):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for child in value.values():
            candidate = find_publicip_id(child)
            if candidate:
                return candidate
    elif isinstance(value, list):
        for child in value:
            candidate = find_publicip_id(child)
            if candidate:
                return candidate
    return None


def target_publicip_id(args: argparse.Namespace, submit_result: dict[str, Any] | None) -> str | None:
    """Return the publicip ID that should be used for post-change verification."""
    if args.publicip_id:
        return args.publicip_id
    if submit_result:
        return find_publicip_id(submit_result.get("parsed_json"))
    return None


def submit_token_payload(args: argparse.Namespace, service_plan: dict[str, Any]) -> dict[str, Any]:
    """Return the exact plan fields that must match before submit execution."""
    commands = service_plan.get("commands", {})
    return {
        "service": "EIP",
        "operation": service_plan.get("operation") or args.operation,
        "region": args.region,
        "project_id": args.project_id,
        "profile": args.profile,
        "publicip_id": args.publicip_id,
        "submit": hcloud_common.canonical_bundled_script_command(
            commands.get("submit")
        ),
        "risk": service_plan.get("risk"),
    }


def expected_submit_token(args: argparse.Namespace, service_plan: dict[str, Any]) -> str:
    """Return the confirmation token for the current EIP submit plan."""
    return hcloud_common.stable_plan_token(submit_token_payload(args, service_plan))


def lifecycle_state_context(
    args: argparse.Namespace,
    service_plan: dict[str, Any],
) -> dict[str, Any] | None:
    """Prepare durable EIP step state and optional task resource ownership."""
    operation = str(service_plan.get("operation") or args.operation)
    state_values = (
        getattr(args, "state_file", None),
        getattr(args, "workflow_id", None),
        getattr(args, "step_id", None),
    )
    ledger_values = (
        getattr(args, "ledger_file", None),
        getattr(args, "resource_role", None),
    )
    cleanup_operation = getattr(args, "cleanup_operation", None)
    expected_cleanup = CREATE_CLEANUP_OPERATIONS.get(operation)
    if expected_cleanup:
        if not all((*state_values, *ledger_values)):
            raise ValueError(
                "EIP create requires durable state and an exact task-owned resource ledger."
            )
        if cleanup_operation != expected_cleanup:
            raise ValueError(
                f"{operation} requires cleanup operation {expected_cleanup}."
            )
    elif any((*ledger_values, cleanup_operation)):
        raise ValueError(
            "Only EIP create operations can claim a new task-owned ledger resource."
        )
    if not any(state_values):
        return None
    if not all(state_values):
        raise ValueError(
            "--state-file, --workflow-id, and --step-id must be provided together."
        )
    fingerprint = hcloud_change_state.request_fingerprint(
        submit_token_payload(args, service_plan)
    )
    prepared = hcloud_change_state.prepare_step(
        Path(str(state_values[0])),
        workflow_id=str(state_values[1]),
        step_id=str(state_values[2]),
        fingerprint=fingerprint,
        request_summary={
            "service": "EIP",
            "operation": service_plan.get("operation") or args.operation,
            "region": args.region,
            "project_id": args.project_id,
            "publicip_id": args.publicip_id,
        },
    )
    lifecycle: dict[str, Any] = {
        "state_file": str(state_values[0]),
        "workflow_id": str(state_values[1]),
        "step_id": str(state_values[2]),
        "fingerprint": fingerprint,
        **prepared,
    }
    if any(ledger_values) and not all(ledger_values):
        raise ValueError("--ledger-file and --resource-role must be provided together.")
    if all(ledger_values):
        hcloud_resource_ledger.register_resource(
            Path(str(ledger_values[0])),
            workflow_id=str(state_values[1]),
            role=str(ledger_values[1]),
            service="EIP",
            region=args.region,
            project_id=args.project_id,
            expected_count=1,
            dependencies=getattr(args, "depends_on", []),
            request_fingerprint=fingerprint,
            cleanup_operation=cleanup_operation,
            identifier_parameter="publicip_id",
        )
        lifecycle["ledger_file"] = str(ledger_values[0])
        lifecycle["resource_role"] = str(ledger_values[1])
    return lifecycle


def _record_lifecycle_submit(
    lifecycle: dict[str, Any],
    submit_result: dict[str, Any],
) -> None:
    """Persist an EIP submit receipt and exact publicip identifiers."""
    identifiers = hcloud_change_state.extract_identifiers(
        submit_result.get("parsed_json")
    )
    step = hcloud_change_state.record_submit(
        Path(lifecycle["state_file"]),
        workflow_id=lifecycle["workflow_id"],
        step_id=lifecycle["step_id"],
        fingerprint=lifecycle["fingerprint"],
        success=bool(submit_result.get("success")),
        request_dispatched=submit_result.get("request_dispatched"),
        identifiers=identifiers,
        verification_params={},
    )
    lifecycle.update(
        {
            "step": step,
            "resume_action": "verify_existing",
            "can_submit": False,
        }
    )
    if lifecycle.get("ledger_file"):
        publicip_id = find_publicip_id(submit_result.get("parsed_json"))
        dispatched = submit_result.get("request_dispatched")
        hcloud_resource_ledger.record_submission(
            Path(lifecycle["ledger_file"]),
            workflow_id=lifecycle["workflow_id"],
            role=lifecycle["resource_role"],
            accepted=(
                True
                if submit_result.get("success")
                else False if dispatched is False else None
            ),
            identifiers=[publicip_id] if publicip_id else [],
        )


def _record_lifecycle_verification(
    lifecycle: dict[str, Any],
    *,
    success: bool,
    publicip_id: str | None,
) -> None:
    """Persist EIP readback convergence in step state and the resource ledger."""
    step = hcloud_change_state.record_verification(
        Path(lifecycle["state_file"]),
        workflow_id=lifecycle["workflow_id"],
        step_id=lifecycle["step_id"],
        fingerprint=lifecycle["fingerprint"],
        success=success,
    )
    lifecycle.update(
        {
            "step": step,
            "resume_action": "reuse_verified" if success else "verify_existing",
            "can_submit": False,
        }
    )
    if lifecycle.get("ledger_file"):
        hcloud_resource_ledger.record_verification(
            Path(lifecycle["ledger_file"]),
            workflow_id=lifecycle["workflow_id"],
            role=lifecycle["resource_role"],
            success=success,
            identifiers=[publicip_id] if publicip_id else [],
            details={"verification_scope": "ShowPublicip"},
        )


def lifecycle_publicip_id(lifecycle: dict[str, Any] | None) -> str | None:
    """Return the publicip ID stored in a prior EIP submit receipt."""
    if not lifecycle:
        return None
    identifiers = lifecycle.get("step", {}).get("identifiers", {})
    if isinstance(identifiers, dict):
        for path, values in identifiers.items():
            if str(path).rsplit(".", 1)[-1] not in {"id", "publicip_id", "publicipId"}:
                continue
            if isinstance(values, list) and values:
                return str(values[0])
    return None


def build_verify_plan(args: argparse.Namespace, publicip_id: str | None) -> dict[str, Any]:
    """Build an EIP ShowPublicip verification plan when a target ID is known."""
    if not publicip_id:
        return {
            "success": False,
            "service": "EIP",
            "operation": "ShowPublicip",
            "error": "Missing publicip_id for post-change verification.",
            "next_actions": [
                "Pass --publicip-id explicitly or use a submit response that contains publicip.id.",
                "For delete flows, verify absence with ListPublicips or confirm ShowPublicip returns a not_found error.",
            ],
        }

    plan = hcloud_resource_query.build_plan(
        SimpleNamespace(
            service="EIP",
            operation="ShowPublicip",
            param=[f"publicip_id={publicip_id}"],
            arg=[],
            region=args.region,
            project_id=args.project_id,
            profile=args.profile,
            execute=args.execute_verify,
            timeout=args.timeout,
            allow_sensitive_read=False,
        )
    )
    expects_absent = str(args.operation).startswith(
        ("Delete", "BatchDelete", "NeutronDelete")
    )
    plan["verification_intent"] = (
        "expect_absent" if expects_absent else "expect_present"
    )
    if args.execute_verify and expects_absent and not plan.get("success"):
        result = plan.get("result")
        if isinstance(result, dict):
            details = result.get("error_details")
            cloud_error = result.get("cloud_error")
            not_found = bool(
                isinstance(details, dict)
                and details.get("category") == "not_found"
            )
            if isinstance(cloud_error, dict):
                text = (
                    f"{cloud_error.get('code') or ''} "
                    f"{cloud_error.get('message') or ''}"
                ).lower()
                not_found = not_found or any(
                    marker in text
                    for marker in ("notfound", "not found", "does not exist")
                )
            output_text = (
                f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
            ).lower()
            not_found = not_found or any(
                marker in output_text
                for marker in ("notfound", "not found", "does not exist")
            )
            if not_found:
                plan["success"] = True
                plan["absent_state_confirmed"] = True
    return plan


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
            "reason": "EIP changes can affect billing or network reachability.",
        }
    risk = service_plan.get("risk", {})
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
            "reason": "The token binds submit execution to the exact reviewed EIP plan, target, and command.",
            "next_action": "Rebuild the plan, review it, then pass submit_guard.submit_token with --submit-token.",
        }
    return None


def _build_flow(args: argparse.Namespace) -> dict[str, Any]:
    """Build and optionally execute a guarded EIP Plan -> Apply -> Verify flow."""
    service_plan = hcloud_service_change_plan.build_service_plan(service_plan_args(args))
    result: dict[str, Any] = {
        "success": bool(service_plan.get("success")),
        "service": "EIP",
        "operation": args.operation,
        "mode": "execute" if (args.execute_dryrun or args.execute_submit or args.execute_verify) else "plan",
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
            "Only use --execute-submit --confirm-submit after explicit user approval for the specific EIP change.",
            "Run --execute-verify with --publicip-id to confirm post-change state.",
        ],
    }
    if not service_plan.get("success"):
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
        f"{submit_token} after explicit user approval for the specific EIP change."
    )

    try:
        lifecycle = lifecycle_state_context(args, service_plan)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result["success"] = False
        result["lifecycle_state_error"] = str(exc)
        return result
    if lifecycle:
        result["lifecycle_state"] = lifecycle
        if lifecycle["resume_action"] == "fingerprint_mismatch":
            result["success"] = False
            result["error"] = (
                "The persisted EIP step belongs to a different exact request."
            )
            return result

    guard_failure = submit_guard_failure(args, service_plan, submit_token)
    if guard_failure:
        result["success"] = False
        result["submit_guard_failure"] = guard_failure
        return result

    commands = service_plan.get("commands", {})
    dryrun_result: dict[str, Any] | None = None
    if args.execute_dryrun:
        dryrun_command = commands.get("dryrun_or_plan")
        if not dryrun_command:
            result["success"] = False
            result["dryrun"] = {"success": False, "error": "Service plan did not produce a dry-run command."}
            return result
        dryrun_result = execute_command(dryrun_command, args.timeout)
        result["dryrun"] = dryrun_result
        append_journal_event(
            args,
            {
                "type": "command",
                "stage": "dryrun",
                "service": "EIP",
                "operation": args.operation,
                "success": bool(dryrun_result.get("success")),
                "command": dryrun_command,
                "result": dryrun_result,
            },
        )
        if not dryrun_result.get("success"):
            result["success"] = False
            result["next_steps"].append("Dry-run failed. Inspect dryrun.error_details/advice before changing arguments.")
            return result

    submit_result: dict[str, Any] | None = None
    if args.execute_submit:
        result["planning_only"] = False
        if lifecycle and not lifecycle["can_submit"]:
            result["submit_resume"] = {
                "submit_was_not_repeated": True,
                "resume_action": lifecycle["resume_action"],
                "prior_status": lifecycle["step"].get("status"),
                "identifiers": lifecycle["step"].get("identifiers") or {},
            }
        else:
            submit_command = commands.get("submit")
            if not submit_command:
                result["success"] = False
                result["submit"] = {"success": False, "error": "Service plan did not produce a submit command."}
                return result
            submit_result = execute_command(submit_command, args.timeout)
            result["submit"] = submit_result
            append_journal_event(
                args,
                {
                    "type": "command",
                    "stage": "submit",
                    "service": "EIP",
                    "operation": args.operation,
                    "success": bool(submit_result.get("success")),
                    "command": submit_command,
                    "result": submit_result,
                },
            )
            if lifecycle:
                _record_lifecycle_submit(lifecycle, submit_result)
            if not submit_result.get("success"):
                result["success"] = False
                if submit_result.get("request_dispatched") is False:
                    result["next_steps"].append(
                        "Submit did not reach hcloud. Repair the local runtime, then retry the same exact plan."
                    )
                elif lifecycle:
                    result["next_steps"].append(
                        "Submit result is ambiguous. Read back the recorded target before any retry."
                    )
                else:
                    result["next_steps"].append("Submit failed. Inspect submit.error_details/advice before retrying.")
                return result

    publicip_id = target_publicip_id(args, submit_result) or lifecycle_publicip_id(
        lifecycle
    )
    if args.execute_verify or args.publicip_id or submit_result:
        verify_plan = build_verify_plan(args, publicip_id)
        result["verification"] = verify_plan
        if args.execute_verify:
            result["success"] = bool(verify_plan.get("success"))
            if lifecycle and str(lifecycle["step"].get("status")) in {
                "submitted",
                "submit_unknown",
                "verification_failed",
                "verified",
            }:
                _record_lifecycle_verification(
                    lifecycle,
                    success=bool(verify_plan.get("success")),
                    publicip_id=publicip_id,
                )
            append_journal_event(
                args,
                {
                    "type": "verification",
                    "stage": "verify",
                    "service": "EIP",
                    "operation": "ShowPublicip",
                    "target_id": publicip_id,
                    "success": bool(verify_plan.get("success")),
                    "result": verify_plan,
                },
            )

    if dryrun_result:
        result["dryrun_command_shell"] = shlex.join(commands.get("dryrun_or_plan", []))
    if submit_result:
        result["submit_command_shell"] = shlex.join(commands.get("submit", []))
    return result


def finalize_flow_result(result: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Attach a truthful `json_outcome_v1` status to every EIP flow result."""
    result["result_contract"] = "json_outcome_v1"
    lifecycle = result.get("lifecycle_state")
    lifecycle_status = (
        str(lifecycle.get("step", {}).get("status") or "")
        if isinstance(lifecycle, dict)
        else ""
    )
    submit_accepted = bool(
        isinstance(result.get("submit"), dict)
        and result["submit"].get("success")
    ) or bool(result.get("submit_resume"))
    verification_succeeded = bool(
        args.execute_verify
        and isinstance(result.get("verification"), dict)
        and result["verification"].get("success")
    )
    if result.get("success") and result.get("planning_only"):
        outcome_status = "succeeded"
    elif lifecycle_status == "verified" or verification_succeeded:
        outcome_status = "succeeded"
    elif submit_accepted or lifecycle_status in {
        "submitted",
        "submit_unknown",
        "verification_failed",
        "verified",
    }:
        outcome_status = "partially_succeeded"
    elif result.get("success"):
        outcome_status = "succeeded"
    else:
        outcome_status = "failed"
    result["outcome_status"] = outcome_status
    result["success"] = outcome_status == "succeeded"
    return result


def build_flow(args: argparse.Namespace) -> dict[str, Any]:
    """Build the EIP flow and return its declared machine outcome."""
    return finalize_flow_result(_build_flow(args), args)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", required=True, help="Registered EIP change operation, for example UpdatePublicip.")
    parser.add_argument("--publicip-id", help="Target publicip_id for post-change ShowPublicip verification.")
    parser.add_argument("--region", help="Explicit cli-region for generated commands.")
    parser.add_argument("--project-id", help="Optional project_id for generated commands.")
    parser.add_argument("--profile", help="Optional cli-profile for generated commands.")
    parser.add_argument("--json-input-file", help="Optional JSON body file for the EIP change operation.")
    parser.add_argument("--arg", action="append", default=[], help="Additional raw hcloud argument token.")
    parser.add_argument("--no-dryrun", action="store_true", help="Do not add --dryrun to the generated dry-run command.")
    parser.add_argument("--allow-unregistered", action="store_true", help="Allow an EIP change operation not listed in the registry.")
    parser.add_argument("--execute-dryrun", action="store_true", help="Execute the generated dry-run command.")
    parser.add_argument("--execute-submit", action="store_true", help="Execute the generated submit command.")
    parser.add_argument("--confirm-submit", action="store_true", help="Required with --execute-submit.")
    parser.add_argument("--submit-token", help="Current plan token required with --execute-submit --confirm-submit.")
    parser.add_argument("--skip-dryrun", action="store_true", help="Allow submit without running dry-run first.")
    parser.add_argument("--execute-verify", action="store_true", help="Execute ShowPublicip verification.")
    parser.add_argument("--journal", help="Optional JSONL journal path for executed dry-run/submit/verify events.")
    parser.add_argument("--state-file", help="Durable change state file.")
    parser.add_argument("--ledger-file", help="Task-owned resource ledger file.")
    parser.add_argument("--workflow-id", help="Stable workflow identifier.")
    parser.add_argument("--step-id", help="Stable EIP step identifier.")
    parser.add_argument("--resource-role", help="Logical task-owned EIP role.")
    parser.add_argument("--depends-on", action="append", default=[], help="Task resource role this EIP depends on.")
    parser.add_argument("--cleanup-operation", help="Exact cleanup operation for task-owned EIP creation.")
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
    return args


def main() -> int:
    """Build and optionally execute the guarded EIP change flow."""
    args = parse_args()
    result = build_flow(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
