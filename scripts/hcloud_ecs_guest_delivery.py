#!/usr/bin/env python3
"""Deliver a local directory to an ECS guest and verify its HTTP user path."""

from __future__ import annotations

import argparse
import hashlib
import re
import shlex
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

import hcloud_acceptance_probe_run
import hcloud_change_state
import hcloud_common

MAX_SOURCE_FILES = 10_000
MAX_SOURCE_BYTES = 512 * 1024 * 1024
USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.:[\]-]{1,253}$")
PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:-]{0,127}$")
SERVICE_RE = re.compile(r"^[A-Za-z0-9@_.-]{1,128}$")


def source_manifest(source_dir: Path) -> dict[str, Any]:
    """Return a bounded digest of regular, symlink-free delivery inputs."""
    root = source_dir.resolve(strict=True)
    if not root.is_dir() or source_dir.is_symlink():
        raise ValueError("source_dir must be a real directory, not a symlink")
    digest = hashlib.sha256()
    file_count = 0
    byte_count = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("source_dir must not contain symlinks")
        if not path.is_file():
            continue
        file_count += 1
        byte_count += path.stat().st_size
        if file_count > MAX_SOURCE_FILES or byte_count > MAX_SOURCE_BYTES:
            raise ValueError("source_dir exceeds the bounded delivery limit")
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    if file_count == 0:
        raise ValueError("source_dir does not contain any regular files")
    return {
        "schema_version": 1,
        "file_count": file_count,
        "byte_count": byte_count,
        "sha256": digest.hexdigest(),
    }


def _validated_destination(value: str) -> str:
    destination = PurePosixPath(str(value or ""))
    if not destination.is_absolute() or ".." in destination.parts:
        raise ValueError("destination_dir must be an absolute normalized POSIX path")
    normalized = destination.as_posix()
    if normalized in {"/", "/root", "/home", "/etc", "/usr", "/var"}:
        raise ValueError("destination_dir is too broad for artifact delivery")
    if any(character in normalized for character in ("\x00", "\n", "\r")):
        raise ValueError("destination_dir contains invalid characters")
    return normalized


def _auth_prefix(args: argparse.Namespace) -> list[str]:
    if args.password_file:
        password_file = Path(args.password_file).resolve(strict=True)
        if not password_file.is_file():
            raise ValueError("password_file must be a regular file")
        if password_file.stat().st_mode & 0o077:
            raise ValueError("password_file permissions must not allow group or other access")
        return ["sshpass", "-f", str(password_file)]
    return []


def _ssh_argv(args: argparse.Namespace, remote_script: str) -> list[str]:
    options = [
        "ssh",
        "-p",
        str(args.port),
        "-o",
        f"ConnectTimeout={args.connect_timeout}",
        "-o",
        f"StrictHostKeyChecking={args.host_key_policy}",
        "-o",
        f"UserKnownHostsFile={Path(args.known_hosts_file).resolve()}",
        "-o",
        "BatchMode=no" if args.password_file else "BatchMode=yes",
    ]
    if args.identity_file:
        options.extend(("-i", str(Path(args.identity_file).resolve(strict=True))))
    options.extend((f"{args.user}@{args.host}", "sh", "-lc", shlex.quote(remote_script)))
    return [*_auth_prefix(args), *options]


def _rsync_argv(args: argparse.Namespace, destination: str) -> list[str]:
    ssh_parts = [
        "ssh",
        "-p",
        str(args.port),
        "-o",
        f"ConnectTimeout={args.connect_timeout}",
        "-o",
        f"StrictHostKeyChecking={args.host_key_policy}",
        "-o",
        f"UserKnownHostsFile={Path(args.known_hosts_file).resolve()}",
    ]
    if args.identity_file:
        ssh_parts.extend(("-i", str(Path(args.identity_file).resolve(strict=True))))
    source = f"{Path(args.source_dir).resolve(strict=True).as_posix()}/"
    target = f"{args.user}@{args.host}:{destination.rstrip('/')}/"
    return [
        *_auth_prefix(args),
        "rsync",
        "-a",
        "--checksum",
        "--itemize-changes",
        "-e",
        shlex.join(ssh_parts),
        source,
        target,
    ]


def _root_command(command: str) -> str:
    return (
        'if [ "$(id -u)" -eq 0 ]; then '
        f"{command}; "
        "elif command -v sudo >/dev/null 2>&1; then "
        f"sudo -n {command}; "
        "else echo 'root privileges unavailable' >&2; exit 77; fi"
    )


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """Build secret-free, idempotent guest delivery phase commands."""
    if not USER_RE.fullmatch(str(args.user or "")):
        raise ValueError("user is invalid")
    if not HOST_RE.fullmatch(str(args.host or "")):
        raise ValueError("host is invalid")
    if bool(args.identity_file) == bool(args.password_file):
        raise ValueError("provide exactly one identity_file or password_file")
    if not 1 <= int(args.port) <= 65535:
        raise ValueError("port is invalid")
    destination = _validated_destination(args.destination_dir)
    packages = list(dict.fromkeys(args.package))
    if any(not PACKAGE_RE.fullmatch(value) for value in packages):
        raise ValueError("package contains an invalid name")
    if args.service_name and not SERVICE_RE.fullmatch(args.service_name):
        raise ValueError("service_name is invalid")
    manifest = source_manifest(Path(args.source_dir))
    known_hosts = Path(args.known_hosts_file).resolve()
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    known_hosts.touch(mode=0o600, exist_ok=True)

    preflight = "set -eu; id; command -v sh; command -v mkdir"
    prepare_commands = [_root_command(f'install -d -o {shlex.quote(args.user)} -g "$(id -gn)" {shlex.quote(destination)}')]
    if packages:
        package_args = " ".join(shlex.quote(value) for value in packages)
        prepare_commands.append(
            "if command -v apt-get >/dev/null 2>&1; then "
            + _root_command("apt-get update")
            + "; "
            + _root_command(f"apt-get install -y --no-install-recommends {package_args}")
            + "; elif command -v dnf >/dev/null 2>&1; then "
            + _root_command(f"dnf install -y {package_args}")
            + "; elif command -v yum >/dev/null 2>&1; then "
            + _root_command(f"yum install -y {package_args}")
            + "; else echo 'supported package manager unavailable' >&2; exit 78; fi"
        )
    prepare = "set -eu; " + "; ".join(prepare_commands)
    service_script = "set -eu; true"
    if args.service_name:
        service_script = "set -eu; " + _root_command(f"systemctl enable --now {shlex.quote(args.service_name)}")
    phases = [
        {"id": "preflight", "command": _ssh_argv(args, preflight)},
        {"id": "prepare_guest", "command": _ssh_argv(args, prepare)},
        {"id": "sync_artifact", "command": _rsync_argv(args, destination)},
        {"id": "converge_service", "command": _ssh_argv(args, service_script)},
    ]
    token_payload = {
        "host": args.host,
        "user": args.user,
        "port": args.port,
        "destination_dir": destination,
        "source_manifest": manifest,
        "packages": packages,
        "service_name": args.service_name,
        "health_url": args.health_url,
        "phases": phases,
    }
    return {
        "success": True,
        "planning_only": True,
        "source_manifest": manifest,
        "destination_dir": destination,
        "phases": phases,
        "delivery_token": hcloud_common.stable_plan_token(token_payload),
        "request_fingerprint": hcloud_change_state.request_fingerprint(token_payload),
    }


def execute_process(command: list[str], timeout: int) -> dict[str, Any]:
    """Execute one delivery phase and return bounded process evidence."""
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "success": completed.returncode == 0,
        "return_code": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def _prepare_state(args: argparse.Namespace, plan: dict[str, Any]) -> dict[str, Any] | None:
    state_values = (args.state_file, args.workflow_id, args.step_id)
    if not any(state_values):
        return None
    if not all(state_values):
        raise ValueError("state_file, workflow_id, and step_id must be provided together")
    return hcloud_change_state.prepare_step(
        Path(args.state_file),
        workflow_id=args.workflow_id,
        step_id=args.step_id,
        fingerprint=plan["request_fingerprint"],
        request_summary={
            "target": f"{args.user}@{args.host}:{args.port}",
            "destination_dir": plan["destination_dir"],
            "source_manifest": plan["source_manifest"],
            "service_name": args.service_name,
            "health_url": args.health_url,
        },
    )


def build_flow(args: argparse.Namespace) -> dict[str, Any]:
    """Plan or execute guest delivery and verify its declared HTTP path."""
    try:
        plan = build_plan(args)
        prepared = _prepare_state(args, plan)
    except (OSError, TypeError, ValueError) as exc:
        return {
            "success": False,
            "outcome_status": "failed",
            "error_code": "GUEST_DELIVERY_PLAN_INVALID",
            "error_message": str(exc),
        }
    result: dict[str, Any] = {
        "success": True,
        "outcome_status": "succeeded",
        "result_contract": "json_outcome_v1",
        "planning_only": True,
        "plan": plan,
        "delivery_guard": {
            "delivery_token": plan["delivery_token"],
            "delivery_token_required": True,
            "delivery_token_provided": bool(args.delivery_token),
            "confirm_delivery": bool(args.confirm_delivery),
        },
    }
    if prepared:
        result["resume_action"] = prepared["resume_action"]
        result["lifecycle_status"] = prepared["step"].get("status")
        if prepared["resume_action"] == "fingerprint_mismatch":
            result.update(
                {
                    "success": False,
                    "outcome_status": "failed",
                    "error_code": "GUEST_DELIVERY_FINGERPRINT_MISMATCH",
                }
            )
            return result
    if not args.execute:
        return result
    if not args.confirm_delivery or args.delivery_token != plan["delivery_token"]:
        result.update(
            {
                "success": False,
                "outcome_status": "failed",
                "error_code": "GUEST_DELIVERY_CONFIRMATION_INVALID",
                "error_message": "Delivery requires explicit confirmation for this exact plan.",
            }
        )
        return result

    can_submit = prepared is None or prepared["can_submit"]
    if can_submit:
        result["planning_only"] = False
        phase_results = []
        for phase in plan["phases"]:
            phase_result = execute_process(phase["command"], args.command_timeout)
            phase_results.append({"id": phase["id"], **phase_result})
            if not phase_result.get("success"):
                break
        result["delivery"] = {
            "success": len(phase_results) == len(plan["phases"]) and all(item["success"] for item in phase_results),
            "phases": phase_results,
        }
        if prepared:
            step = hcloud_change_state.record_submit(
                Path(args.state_file),
                workflow_id=args.workflow_id,
                step_id=args.step_id,
                fingerprint=plan["request_fingerprint"],
                success=bool(result["delivery"]["success"]),
            )
            result["lifecycle_status"] = step["status"]
        if not result["delivery"]["success"]:
            result.update(
                {
                    "success": False,
                    "outcome_status": "partially_succeeded",
                    "error_code": "GUEST_DELIVERY_OUTCOME_REQUIRES_READBACK",
                }
            )
            return result
    else:
        result["planning_only"] = False
        result["resume"] = {
            "delivery_was_not_repeated": True,
            "resume_action": prepared["resume_action"],
            "prior_status": prepared["step"].get("status"),
        }

    if not args.health_url:
        result.update(
            {
                "success": False,
                "outcome_status": "partially_succeeded",
                "error_code": "GUEST_ACCEPTANCE_REQUIRED",
                "error_message": "Artifact delivery is not complete until a user-path probe passes.",
            }
        )
        return result
    acceptance = hcloud_acceptance_probe_run.http_probe(
        args.health_url,
        method="GET",
        timeout=args.connect_timeout,
        allow_private_targets=args.allow_private_target,
    )
    result["acceptance"] = acceptance
    verified = acceptance.get("status") == "passed"
    if prepared:
        step = hcloud_change_state.record_verification(
            Path(args.state_file),
            workflow_id=args.workflow_id,
            step_id=args.step_id,
            fingerprint=plan["request_fingerprint"],
            success=verified,
        )
        result["lifecycle_status"] = step["status"]
    result["success"] = verified
    result["outcome_status"] = "succeeded" if verified else "partially_succeeded"
    if not verified:
        result["error_code"] = "GUEST_ACCEPTANCE_FAILED"
    return result


def parse_args() -> argparse.Namespace:
    """Parse guest delivery and acceptance arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--destination-dir", required=True)
    parser.add_argument("--identity-file")
    parser.add_argument("--password-file")
    parser.add_argument("--known-hosts-file", required=True)
    parser.add_argument(
        "--host-key-policy",
        choices=("yes", "accept-new"),
        default="accept-new",
    )
    parser.add_argument("--package", action="append", default=[])
    parser.add_argument("--service-name")
    parser.add_argument("--health-url")
    parser.add_argument("--allow-private-target", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-delivery", action="store_true")
    parser.add_argument("--delivery-token")
    parser.add_argument("--state-file")
    parser.add_argument("--workflow-id")
    parser.add_argument("--step-id")
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--command-timeout", type=int, default=300)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if args.connect_timeout < 1 or args.command_timeout < 1:
        parser.error("timeouts must be greater than 0")
    state_values = (args.state_file, args.workflow_id, args.step_id)
    if any(state_values) and not all(state_values):
        parser.error("state_file, workflow_id, and step_id must be provided together")
    return args


def main() -> int:
    """Run guest delivery and emit its structured acceptance outcome."""
    args = parse_args()
    result = build_flow(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result.get("outcome_status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
