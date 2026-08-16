#!/usr/bin/env python3
"""Run a resumable ECS create, async job wait, and ACTIVE verification flow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import hcloud_change_state
import hcloud_common
import hcloud_ecs_create_plan
import hcloud_ecs_verify_active
import hcloud_ecs_wait_job
import hcloud_resource_ledger


MANAGED_STATE_ROOT = Path(".cloud-claw") / "guarded-changes"
_ACTION_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def execute_command(command: list[str], timeout: int) -> dict[str, Any]:
    """Run one generated safe-exec command and parse its JSON envelope."""
    return hcloud_common.run_json_command(command, timeout)


def planner_args(args: argparse.Namespace, *, mode: str) -> SimpleNamespace:
    """Build the namespace expected by the existing ECS create planner."""
    return SimpleNamespace(
        json_input_file=args.json_input_file,
        security_group_evidence_file=args.security_group_evidence_file,
        operation=args.operation,
        region=args.region,
        profile=args.profile,
        mode=mode,
        confirm_submit=mode == "submit",
        allow_placeholders=args.allow_placeholders,
        max_count=args.max_count,
        allow_large_count=args.allow_large_count,
        allow_public_web=args.allow_public_web,
        journal=getattr(args, "journal", None),
    )


def _server_request(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    body = payload.get("body")
    if not isinstance(body, dict):
        return {}
    server = body.get("server")
    return server if isinstance(server, dict) else {}


def _expected_count(payload: Any) -> int:
    value = _server_request(payload).get("count", 1)
    return value if isinstance(value, int) and not isinstance(value, bool) else 1


def _server_names(payload: Any) -> list[str]:
    value = _server_request(payload).get("name")
    return [value] if isinstance(value, str) and value.strip() else []


def _identifier_values(
    identifiers: dict[str, list[str]] | None,
    *,
    suffixes: Iterable[str],
) -> list[str]:
    normalized_suffixes = {suffix.replace("-", "_").replace(".", "_").lower() for suffix in suffixes}
    values: list[str] = []
    for path, candidates in (identifiers or {}).items():
        tail = path.rsplit(".", 1)[-1].replace("-", "_").lower()
        if tail not in normalized_suffixes:
            continue
        for candidate in candidates:
            if candidate and candidate not in values:
                values.append(candidate)
    return values


def _job_ids(identifiers: dict[str, list[str]] | None) -> list[str]:
    return _identifier_values(
        identifiers,
        suffixes=("job_id", "job_ids", "jobId", "jobIds"),
    )


def _server_ids(identifiers: dict[str, list[str]] | None) -> list[str]:
    return _identifier_values(
        identifiers,
        suffixes=("server_id", "server_ids", "serverId", "serverIds"),
    )


def _matched_server_ids(verification: dict[str, Any]) -> list[str]:
    final = verification.get("final")
    if not isinstance(final, dict):
        return []
    values: list[str] = []
    for item in final.get("matched", []):
        if not isinstance(item, dict):
            continue
        value = item.get("id")
        if value is not None and str(value).strip() and str(value) not in values:
            values.append(str(value))
    return values


def submit_token_payload(
    args: argparse.Namespace,
    payload: Any,
    submit_plan: dict[str, Any],
) -> dict[str, Any]:
    """Return the exact reviewed ECS request fields bound by confirmation."""
    return {
        "service": "ECS",
        "operation": args.operation,
        "region": args.region,
        "project_id": args.project_id,
        "request": payload,
        "submit": _portable_submit_command(
            submit_plan.get("commands", {}).get("safe_exec")
        ),
        "workflow_id": args.workflow_id,
        "step_id": args.step_id,
        "resource_role": args.resource_role,
    }


def _portable_submit_command(command: Any) -> list[str]:
    """Return a canonical submit command without workspace path spelling.

    The canonical request JSON is already included in the fingerprint payload.
    Replacing its local filename keeps an identical request stable when the
    proposal runtime projects an artifact under a different workspace path.
    """

    canonical = hcloud_common.canonical_bundled_script_command(command)
    portable: list[str] = []
    replace_next = False
    for item in canonical:
        if replace_next:
            portable.append("<request-artifact>")
            replace_next = False
        elif item == "--json-input-file":
            portable.append(item)
            replace_next = True
        elif item.startswith("--json-input-file="):
            portable.append("--json-input-file=<request-artifact>")
        else:
            portable.append(item)
    return portable


def _managed_scope(args: argparse.Namespace) -> str | None:
    """Configure stable internal lifecycle files for an approved proposal.

    Managed workflow mode is reserved for the guarded action executor. It
    derives durable bookkeeping from the user/conversation scope and logical
    resource role, so callers do not need to copy opaque tokens or filenames.
    """

    if not getattr(args, "managed_workflow", False):
        return None

    action_hash = os.getenv("CLOUD_CLAW_ACTION_HASH", "").strip().lower()
    authorized = os.getenv("CLOUD_CLAW_ACTION_AUTHORIZED", "").strip().lower()
    user_id = os.getenv("CLOUD_CLAW_ACTION_USER_ID", "").strip()
    conversation_id = os.getenv("CLOUD_CLAW_ACTION_CONVERSATION_ID", "").strip()
    execution_id = os.getenv("CLOUD_CLAW_ACTION_EXECUTION_ID", "").strip()
    if (
        authorized != "true"
        or not _ACTION_HASH_PATTERN.fullmatch(action_hash)
        or not user_id
        or not conversation_id
        or not execution_id
    ):
        return "Managed ECS execution requires an approved CloudClaw action context."

    scope = hashlib.sha256(f"{user_id}\0{conversation_id}".encode()).hexdigest()[:16]
    role_text = str(args.resource_role).strip()
    role_slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", role_text).strip("-.") or "server"
    role_digest = hashlib.sha256(role_text.encode()).hexdigest()[:10]
    configured_state_root = os.getenv("CLOUD_CLAW_CAPABILITY_STATE_ROOT", "").strip()
    state_root = Path(configured_state_root) if configured_state_root else MANAGED_STATE_ROOT
    state_root /= scope
    args.state_file = str(state_root / "ecs-create-state.json")
    args.ledger_file = str(state_root / "resource-ledger.json")
    args.workflow_id = f"managed-{scope}"
    args.step_id = f"ecs-create-{role_slug[:72]}-{role_digest}"
    return None


def _failure_result(
    result: dict[str, Any],
    *,
    error_code: str,
    message: str,
    partial: bool = False,
) -> dict[str, Any]:
    result.update(
        {
            "success": False,
            "outcome_status": "partially_succeeded" if partial else "failed",
            "error_code": error_code,
            "error_message": message,
        }
    )
    return result


def _ledger_resource(args: argparse.Namespace) -> dict[str, Any]:
    ledger = hcloud_resource_ledger.load_ledger(
        Path(args.ledger_file),
        workflow_id=args.workflow_id,
    )
    resource = ledger["resources"].get(args.resource_role)
    return resource if isinstance(resource, dict) else {}


def _wait_job_args(
    args: argparse.Namespace,
    *,
    job_id: str,
    server_ids: list[str],
    server_names: list[str],
) -> SimpleNamespace:
    return SimpleNamespace(
        job_id=job_id,
        region=args.region,
        project_id=args.project_id,
        profile=args.profile,
        server_id=server_ids,
        server_name=server_names,
        interval=args.interval,
        timeout=args.timeout,
        command_timeout=args.command_timeout,
        max_command_failures=args.max_command_failures,
        print_command_only=False,
    )


def _verify_active_args(
    args: argparse.Namespace,
    *,
    server_ids: list[str],
    server_names: list[str],
) -> SimpleNamespace:
    return SimpleNamespace(
        server_id=server_ids,
        server_name=server_names,
        region=args.region,
        project_id=args.project_id,
        profile=args.profile,
        limit=100,
        interval=args.interval,
        timeout=args.timeout,
        command_timeout=args.command_timeout,
        max_command_failures=args.max_command_failures,
        print_command_only=False,
    )


def build_flow(args: argparse.Namespace) -> dict[str, Any]:
    """Plan or execute one idempotent ECS create-to-ACTIVE lifecycle."""
    managed_error = _managed_scope(args)
    if managed_error:
        return {
            "success": False,
            "outcome_status": "failed",
            "error_code": "ECS_MANAGED_EXECUTION_UNAUTHORIZED",
            "error_message": managed_error,
        }

    try:
        payload = hcloud_common.load_json(Path(args.json_input_file))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "success": False,
            "outcome_status": "failed",
            "error_code": "ECS_CREATE_INPUT_INVALID",
            "error_message": str(exc),
        }

    submit_plan = hcloud_ecs_create_plan.build_result(planner_args(args, mode="submit"))
    result: dict[str, Any] = {
        "success": bool(submit_plan.get("success")),
        "outcome_status": "succeeded" if submit_plan.get("success") else "failed",
        "service": "ECS",
        "operation": args.operation,
        "planning_only": True,
        "service_plan": submit_plan,
    }
    if not submit_plan.get("success") or not submit_plan.get("ready_to_run"):
        return _failure_result(
            result,
            error_code="ECS_CREATE_PLAN_INVALID",
            message="The ECS create input did not produce a runnable submit plan.",
        )

    fingerprint_payload = submit_token_payload(args, payload, submit_plan)
    fingerprint = hcloud_change_state.request_fingerprint(fingerprint_payload)
    submit_token = hcloud_common.stable_plan_token(fingerprint_payload)
    if getattr(args, "managed_workflow", False):
        result["submit_guard"] = {
            "managed_by_runtime": True,
            "submit_token_required": False,
            "proposal_authorized": True,
        }
    else:
        result["submit_guard"] = {
            "submit_token": submit_token,
            "submit_token_required": True,
            "submit_token_provided": bool(args.submit_token),
            "confirm_submit": bool(args.confirm_submit),
        }

    try:
        hcloud_resource_ledger.register_resource(
            Path(args.ledger_file),
            workflow_id=args.workflow_id,
            role=args.resource_role,
            service="ECS",
            region=args.region,
            project_id=args.project_id,
            expected_count=_expected_count(payload),
            dependencies=args.depends_on,
            request_fingerprint=fingerprint,
            cleanup_operation="DeleteServers",
            identifier_parameter="server_id",
        )
        prepared = hcloud_change_state.prepare_step(
            Path(args.state_file),
            workflow_id=args.workflow_id,
            step_id=args.step_id,
            fingerprint=fingerprint,
            request_summary={
                "service": "ECS",
                "operation": args.operation,
                "region": args.region,
                "project_id": args.project_id,
                "resource_role": args.resource_role,
                "expected_count": _expected_count(payload),
            },
        )
    except (OSError, TypeError, ValueError) as exc:
        return _failure_result(
            result,
            error_code="ECS_CHANGE_STATE_INVALID",
            message=str(exc),
        )
    result["resume_action"] = prepared["resume_action"]
    result["lifecycle_status"] = prepared["step"].get("status")
    if prepared["resume_action"] == "fingerprint_mismatch":
        return _failure_result(
            result,
            error_code="ECS_CHANGE_FINGERPRINT_MISMATCH",
            message="The workflow step is already bound to a different ECS request.",
        )

    if not any(
        (
            args.execute_dryrun,
            args.execute_submit,
            args.execute_wait,
            args.execute_verify,
        )
    ):
        return result

    if args.execute_dryrun:
        dryrun_plan = hcloud_ecs_create_plan.build_result(planner_args(args, mode="dryrun"))
        command = dryrun_plan.get("commands", {}).get("safe_exec")
        if not command:
            return _failure_result(
                result,
                error_code="ECS_DRYRUN_PLAN_INVALID",
                message="The ECS planner did not produce a dry-run command.",
            )
        dryrun = execute_command(command, args.command_timeout)
        result["dryrun"] = dryrun
        if not dryrun.get("success"):
            return _failure_result(
                result,
                error_code="ECS_DRYRUN_FAILED",
                message="The ECS create dry-run did not succeed.",
            )

    if args.execute_submit:
        token_matches = (
            getattr(args, "managed_workflow", False)
            or args.submit_token == submit_token
        )
        if not args.confirm_submit or not token_matches:
            return _failure_result(
                result,
                error_code="ECS_SUBMIT_CONFIRMATION_INVALID",
                message=("ECS submit requires --confirm-submit and the token from the exact current plan."),
            )
        if prepared["can_submit"]:
            submit_command = submit_plan["commands"]["safe_exec"]
            submit = execute_command(submit_command, args.command_timeout)
            result["submit"] = submit
            result["planning_only"] = False
            identifiers = hcloud_change_state.extract_identifiers(submit.get("parsed_json"))
            dispatched = submit.get("request_dispatched")
            accepted = (
                True
                if submit.get("success")
                else False if dispatched is False else None
            )
            step = hcloud_change_state.record_submit(
                Path(args.state_file),
                workflow_id=args.workflow_id,
                step_id=args.step_id,
                fingerprint=fingerprint,
                success=bool(submit.get("success")),
                request_dispatched=dispatched,
                identifiers=identifiers,
                verification_params={
                    "region": args.region,
                    "project_id": args.project_id or "",
                },
            )
            hcloud_resource_ledger.record_submission(
                Path(args.ledger_file),
                workflow_id=args.workflow_id,
                role=args.resource_role,
                accepted=accepted,
                identifiers=_server_ids(identifiers),
                job_ids=_job_ids(identifiers),
            )
            result["lifecycle_status"] = step["status"]
            if not submit.get("success"):
                definitely_failed = dispatched is False
                return _failure_result(
                    result,
                    error_code=(
                        "ECS_SUBMIT_NOT_DISPATCHED"
                        if definitely_failed
                        else "SUBMIT_OUTCOME_REQUIRES_READBACK"
                    ),
                    message=(
                        "The ECS submit did not reach hcloud. Repair the local runtime, then retry the same exact plan."
                        if definitely_failed
                        else "The local submit result is ambiguous. The exact workflow must be read back before any retry."
                    ),
                    partial=not definitely_failed,
                )
        else:
            result["planning_only"] = False

    step = hcloud_change_state.load_state(
        Path(args.state_file),
        workflow_id=args.workflow_id,
    )["steps"][args.step_id]
    lifecycle_identifiers = step.get("identifiers") or {}
    ledger_resource = _ledger_resource(args)
    job_ids = _job_ids(lifecycle_identifiers)
    for value in ledger_resource.get("job_ids", []):
        if value not in job_ids:
            job_ids.append(value)
    server_ids = _server_ids(lifecycle_identifiers)
    for value in ledger_resource.get("identifiers", []):
        if value not in server_ids:
            server_ids.append(value)
    server_names = _server_names(payload)

    if step.get("status") == "submit_unknown" and not args.execute_wait and not args.execute_verify:
        return _failure_result(
            result,
            error_code="SUBMIT_OUTCOME_REQUIRES_READBACK",
            message=("The prior ECS submit remains ambiguous. Request job or resource readback; do not replay submit."),
            partial=True,
        )

    if args.execute_wait:
        if not job_ids:
            return _failure_result(
                result,
                error_code="ASYNC_JOB_ID_MISSING",
                message="No task-owned ECS job_id is available for async convergence.",
                partial=True,
            )
        job_result = hcloud_ecs_wait_job.wait_for_job(
            _wait_job_args(
                args,
                job_id=job_ids[0],
                server_ids=server_ids,
                server_names=server_names,
            )
        )
        result["job_wait"] = job_result
        job_identifiers = job_result.get("final_identifiers")
        for value in _server_ids(job_identifiers):
            if value not in server_ids:
                server_ids.append(value)
        hcloud_resource_ledger.record_submission(
            Path(args.ledger_file),
            workflow_id=args.workflow_id,
            role=args.resource_role,
            accepted=True,
            identifiers=server_ids,
            job_ids=job_ids,
        )
        if not job_result.get("success"):
            return _failure_result(
                result,
                error_code="ECS_ASYNC_JOB_NOT_CONVERGED",
                message="The ECS async job did not reach a successful terminal state.",
                partial=True,
            )

    if args.execute_verify:
        if not server_ids and not server_names:
            return _failure_result(
                result,
                error_code="ECS_VERIFY_TARGET_MISSING",
                message="No task-owned ECS identifier is available for ACTIVE verification.",
                partial=True,
            )
        verification = hcloud_ecs_verify_active.wait_for_active(
            _verify_active_args(
                args,
                server_ids=server_ids,
                server_names=[] if server_ids else server_names,
            )
        )
        result["verification"] = verification
        verified_ids = _matched_server_ids(verification)
        lifecycle = hcloud_change_state.record_verification(
            Path(args.state_file),
            workflow_id=args.workflow_id,
            step_id=args.step_id,
            fingerprint=fingerprint,
            success=bool(verification.get("success")),
        )
        resource = hcloud_resource_ledger.record_verification(
            Path(args.ledger_file),
            workflow_id=args.workflow_id,
            role=args.resource_role,
            success=bool(verification.get("success")),
            identifiers=verified_ids,
            details={
                "verification_scope": "resource_active",
                "matched": verification.get("final", {}).get("matched", []),
            },
        )
        result["lifecycle_status"] = lifecycle["status"]
        if lifecycle["status"] == "verified" and resource["state"] == "verified":
            result.update(
                {
                    "success": True,
                    "outcome_status": "succeeded",
                    "outcome_known": True,
                    "planning_only": False,
                }
            )
            return result
        return _failure_result(
            result,
            error_code="ECS_ACTIVE_VERIFICATION_FAILED",
            message="The requested ECS resources were not all verified ACTIVE.",
            partial=True,
        )

    if args.execute_submit or args.execute_wait:
        result.update(
            {
                "success": False,
                "outcome_status": "partially_succeeded",
                "outcome_known": True,
                "planning_only": False,
                "error_code": "ECS_RESOURCE_VERIFICATION_REQUIRED",
                "error_message": (
                    "Submit or async job completion is not the final ECS resource outcome; ACTIVE verification is still required."
                ),
            }
        )
    return result


def parse_args() -> argparse.Namespace:
    """Parse end-to-end ECS change flow arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-input-file", required=True)
    parser.add_argument("--security-group-evidence-file", required=True)
    parser.add_argument("--operation", default="CreateServers")
    parser.add_argument("--region", required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--profile")
    parser.add_argument("--state-file")
    parser.add_argument("--ledger-file")
    parser.add_argument("--workflow-id")
    parser.add_argument("--step-id")
    parser.add_argument("--resource-role", required=True)
    parser.add_argument("--depends-on", action="append", default=[])
    parser.add_argument("--execute-dryrun", action="store_true")
    parser.add_argument("--execute-submit", action="store_true")
    parser.add_argument("--execute-wait", action="store_true")
    parser.add_argument("--execute-verify", action="store_true")
    parser.add_argument("--confirm-submit", action="store_true")
    parser.add_argument("--submit-token")
    parser.add_argument("--managed-workflow", action="store_true")
    parser.add_argument("--allow-placeholders", action="store_true")
    parser.add_argument("--max-count", type=int, default=10)
    parser.add_argument("--allow-large-count", action="store_true")
    parser.add_argument("--allow-public-web", action="store_true")
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--command-timeout", type=int, default=120)
    parser.add_argument("--max-command-failures", type=int, default=3)
    parser.add_argument("--journal")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if args.max_count < 1 or args.max_count > 100:
        parser.error("--max-count must be between 1 and 100")
    if args.interval <= 0 or args.timeout <= 0 or args.command_timeout <= 0:
        parser.error("polling intervals and timeouts must be greater than 0")
    if args.max_command_failures < 1:
        parser.error("--max-command-failures must be at least 1")
    if not args.managed_workflow:
        missing = [
            flag
            for flag, value in (
                ("--state-file", args.state_file),
                ("--ledger-file", args.ledger_file),
                ("--workflow-id", args.workflow_id),
                ("--step-id", args.step_id),
            )
            if not value
        ]
        if missing:
            parser.error(f"legacy workflow mode requires {', '.join(missing)}")
    return args


def main() -> int:
    """Run the ECS change flow and emit the structured outcome."""
    args = parse_args()
    result = build_flow(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result.get("outcome_status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
