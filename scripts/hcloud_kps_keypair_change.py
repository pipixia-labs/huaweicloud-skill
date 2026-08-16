#!/usr/bin/env python3
"""Import or delete one Huawei Cloud SSH key pair with exact read-back."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import os
import re
from pathlib import Path
from typing import Any

import hcloud_common

KEYPAIR_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,255}$")
PUBLIC_KEY_TYPES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)
NOT_FOUND_MARKERS = (
    "not found",
    "not exist",
    "does not exist",
    "cannot find",
    "不存在",
    "未找到",
)


def execute_command(command: list[str], timeout: int) -> dict[str, Any]:
    """Run one bundled safe-exec command and return its structured result."""

    return hcloud_common.run_json_command(command, timeout)


def _safe_exec_command(
    *,
    operation: str,
    region: str,
    project_id: str | None,
    arguments: list[str],
    timeout: int,
) -> list[str]:
    """Build a bounded KPS command through the shared safe executor."""

    command = [
        *hcloud_common.safe_exec_command_prefix(),
        "--service=KPS",
        f"--operation={operation}",
        f"--arg=--cli-region={region}",
        f"--timeout={timeout}",
        "--expect-json",
        "--output-mode=full",
        "--max-parsed-json-chars=1048576",
    ]
    if project_id:
        command.append(f"--arg=--project_id={project_id}")
    command.extend(f"--arg={argument}" for argument in arguments)
    return command


def _workspace_file(value: str) -> Path:
    """Resolve a relative input file inside the platform-projected workspace."""

    workspace = Path(
        os.getenv("CLOUD_CLAW_ACTION_WORKSPACE_PATH")
        or os.getenv("CLOUD_CLAW_WORKSPACE")
        or Path.cwd()
    ).resolve(strict=True)
    candidate = (workspace / value).resolve(strict=True)
    if workspace not in candidate.parents or not candidate.is_file():
        raise ValueError("public key file must be a regular workspace file")
    return candidate


def _load_public_key(value: str) -> tuple[str, dict[str, str]]:
    """Load and validate one OpenSSH public key without retaining its comment."""

    path = _workspace_file(value)
    if path.stat().st_size > 16 * 1024:
        raise ValueError("public key file is too large")
    tokens = path.read_text(encoding="utf-8").strip().split()
    if len(tokens) < 2 or not tokens[0].startswith(PUBLIC_KEY_TYPES):
        raise ValueError("public key file is not a supported OpenSSH public key")
    try:
        key_blob = base64.b64decode(tokens[1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("public key payload is not valid base64") from exc
    if not key_blob:
        raise ValueError("public key payload is empty")
    normalized = f"{tokens[0]} {tokens[1]}"
    md5_value = hashlib.md5(key_blob, usedforsecurity=False).hexdigest()
    sha256_value = base64.b64encode(hashlib.sha256(key_blob).digest()).decode("ascii")
    return normalized, {
        "md5": ":".join(md5_value[index : index + 2] for index in range(0, 32, 2)),
        "sha256": f"SHA256:{sha256_value.rstrip('=')}",
    }


def _iter_mappings(value: Any):
    """Yield every mapping in a JSON-like response."""

    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_mappings(child)


def _keypair_detail(value: Any, keypair_name: str) -> dict[str, str] | None:
    """Extract normalized non-secret key-pair evidence for an exact name."""

    for mapping in _iter_mappings(value):
        name = str(mapping.get("name") or mapping.get("keypair_name") or "").strip()
        if name != keypair_name:
            continue
        detail = {"name": name}
        for source, target in (
            ("fingerprint", "fingerprint"),
            ("public_key", "public_key"),
        ):
            candidate = mapping.get(source)
            if isinstance(candidate, str) and candidate.strip():
                detail[target] = candidate.strip()
        return detail
    return None


def _is_not_found(result: dict[str, Any]) -> bool:
    """Return whether a failed exact-key query proves the key pair is absent."""

    error_details = result.get("error_details")
    values = [result.get("stdout"), result.get("stderr")]
    if isinstance(error_details, dict):
        values.extend(
            [
                error_details.get("cloud_error_code"),
                error_details.get("cloud_error_message"),
            ]
        )
    text = " ".join(str(value or "") for value in values).lower()
    return any(marker in text for marker in NOT_FOUND_MARKERS)


def query_keypair(args: argparse.Namespace) -> dict[str, Any]:
    """Return exact KPS presence and detail evidence for one key-pair name."""

    result = execute_command(
        _safe_exec_command(
            operation="ListKeypairDetail",
            region=args.region,
            project_id=args.project_id,
            arguments=[f"--keypair_name={args.keypair_name}"],
            timeout=args.timeout,
        ),
        args.timeout + 10,
    )
    if result.get("success"):
        detail = _keypair_detail(result.get("parsed_json"), args.keypair_name)
        if detail:
            return {"success": True, "exists": True, "detail": detail}
        return {
            "success": False,
            "error_code": "KEYPAIR_DETAIL_INVALID",
            "error_message": "KPS detail response did not identify the requested key pair",
        }
    if _is_not_found(result):
        return {"success": True, "exists": False, "detail": None}
    return {
        "success": False,
        "error_code": "KEYPAIR_QUERY_FAILED",
        "error_message": "KPS key-pair read-back failed",
        "diagnostic": _command_diagnostic(result),
    }


def _command_diagnostic(result: dict[str, Any]) -> dict[str, Any]:
    """Return bounded, non-secret failure evidence from safe-exec."""

    error_details = result.get("error_details")
    return {
        "error_type": result.get("error_type"),
        "error_code": result.get("error_code"),
        "request_dispatched": result.get("request_dispatched"),
        "cloud_error_code": (
            error_details.get("cloud_error_code")
            if isinstance(error_details, dict)
            else None
        ),
        "cloud_error_message": (
            error_details.get("cloud_error_message")
            if isinstance(error_details, dict)
            else None
        ),
    }


def _public_key_matches(
    detail: dict[str, str],
    public_key: str,
    fingerprints: dict[str, str],
) -> bool:
    """Compare cloud read-back with the local public key using available evidence."""

    remote_key = detail.get("public_key", "").strip().split()
    if len(remote_key) >= 2:
        return f"{remote_key[0]} {remote_key[1]}" == public_key
    fingerprint = detail.get("fingerprint", "").strip().lower()
    return bool(
        fingerprint
        and fingerprint
        in {
            fingerprints["md5"].lower(),
            fingerprints["sha256"].lower(),
        }
    )


def _outcome(
    status: str,
    *,
    operation: str,
    keypair_name: str,
    changed: bool,
    detail: dict[str, str] | None = None,
    error_code: str = "",
    error_message: str = "",
    diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable json_outcome_v1 payload returned to the platform."""

    resource = {"type": "kps_keypair", "name": keypair_name}
    if detail and detail.get("fingerprint"):
        resource["fingerprint"] = detail["fingerprint"]
    result: dict[str, Any] = {
        "success": status == "succeeded",
        "outcome_status": status,
        "operation": operation,
        "changed": changed,
        "resource": resource,
        "verification": {
            "operation": "ListKeypairDetail",
            "verified": status == "succeeded",
        },
    }
    if error_code:
        result["error_code"] = error_code
    if error_message:
        result["error_message"] = error_message
    if diagnostic:
        result["diagnostic"] = diagnostic
    return result


def import_keypair(args: argparse.Namespace) -> dict[str, Any]:
    """Idempotently import a workspace public key and verify exact identity."""

    public_key, fingerprints = _load_public_key(args.public_key_file)
    before = query_keypair(args)
    if not before.get("success"):
        return _outcome(
            "failed",
            operation="import",
            keypair_name=args.keypair_name,
            changed=False,
            error_code=str(before.get("error_code") or "KEYPAIR_QUERY_FAILED"),
            error_message=str(before.get("error_message") or "KPS query failed"),
            diagnostic=before.get("diagnostic"),
        )
    if before.get("exists"):
        detail = before["detail"]
        if _public_key_matches(detail, public_key, fingerprints):
            return _outcome(
                "succeeded",
                operation="import",
                keypair_name=args.keypair_name,
                changed=False,
                detail=detail,
            )
        return _outcome(
            "failed",
            operation="import",
            keypair_name=args.keypair_name,
            changed=False,
            detail=detail,
            error_code="KEYPAIR_NAME_CONFLICT",
            error_message="the key-pair name already exists with different key material",
        )

    submit = execute_command(
        _safe_exec_command(
            operation="CreateKeypair",
            region=args.region,
            project_id=args.project_id,
            arguments=[
                f"--keypair.name={args.keypair_name}",
                f"--keypair.public_key={public_key}",
                "--keypair.type=ssh",
            ],
            timeout=args.timeout,
        ),
        args.timeout + 10,
    )
    after = query_keypair(args)
    if after.get("success") and after.get("exists"):
        detail = after["detail"]
        if _public_key_matches(detail, public_key, fingerprints):
            return _outcome(
                "succeeded",
                operation="import",
                keypair_name=args.keypair_name,
                changed=True,
                detail=detail,
            )
        return _outcome(
            "partially_succeeded",
            operation="import",
            keypair_name=args.keypair_name,
            changed=True,
            detail=detail,
            error_code="KEYPAIR_VERIFICATION_CONFLICT",
            error_message="a key pair exists after submit but its key material differs",
        )
    if submit.get("success"):
        return _outcome(
            "partially_succeeded",
            operation="import",
            keypair_name=args.keypair_name,
            changed=True,
            error_code="KEYPAIR_VERIFICATION_FAILED",
            error_message="key-pair import completed but exact read-back did not converge",
            diagnostic=after.get("diagnostic"),
        )
    uncertain = submit.get("request_dispatched") is not False
    return _outcome(
        "partially_succeeded" if uncertain else "failed",
        operation="import",
        keypair_name=args.keypair_name,
        changed=uncertain,
        error_code="KEYPAIR_IMPORT_OUTCOME_UNKNOWN" if uncertain else "KEYPAIR_IMPORT_FAILED",
        error_message="key-pair import did not produce verified cloud state",
        diagnostic=_command_diagnostic(submit),
    )


def delete_keypair(args: argparse.Namespace) -> dict[str, Any]:
    """Idempotently delete one exact key-pair name and verify absence."""

    before = query_keypair(args)
    if not before.get("success"):
        return _outcome(
            "failed",
            operation="delete",
            keypair_name=args.keypair_name,
            changed=False,
            error_code=str(before.get("error_code") or "KEYPAIR_QUERY_FAILED"),
            error_message=str(before.get("error_message") or "KPS query failed"),
            diagnostic=before.get("diagnostic"),
        )
    if not before.get("exists"):
        return _outcome(
            "succeeded",
            operation="delete",
            keypair_name=args.keypair_name,
            changed=False,
        )

    submit = execute_command(
        _safe_exec_command(
            operation="DeleteKeypair",
            region=args.region,
            project_id=args.project_id,
            arguments=[f"--keypair_name={args.keypair_name}"],
            timeout=args.timeout,
        ),
        args.timeout + 10,
    )
    after = query_keypair(args)
    if after.get("success") and not after.get("exists"):
        return _outcome(
            "succeeded",
            operation="delete",
            keypair_name=args.keypair_name,
            changed=True,
        )
    uncertain = submit.get("success") or submit.get("request_dispatched") is not False
    return _outcome(
        "partially_succeeded" if uncertain else "failed",
        operation="delete",
        keypair_name=args.keypair_name,
        changed=uncertain,
        detail=after.get("detail") if after.get("exists") else None,
        error_code="KEYPAIR_DELETE_NOT_VERIFIED" if uncertain else "KEYPAIR_DELETE_FAILED",
        error_message="key-pair deletion did not produce verified absence",
        diagnostic=(after.get("diagnostic") or _command_diagnostic(submit)),
    )


def parse_args() -> argparse.Namespace:
    """Parse the small business-facing key-pair capability interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=("import", "delete"), required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--keypair-name", required=True)
    parser.add_argument("--public-key-file")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-change", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if not KEYPAIR_NAME_RE.fullmatch(args.keypair_name):
        parser.error("--keypair-name contains unsupported characters")
    if args.timeout < 1 or args.timeout > 600:
        parser.error("--timeout must be between 1 and 600")
    if args.operation == "import" and not args.public_key_file:
        parser.error("--public-key-file is required for import")
    if args.operation == "delete" and args.public_key_file:
        parser.error("--public-key-file is only valid for import")
    return args


def main() -> int:
    """Execute the confirmed key-pair change and emit json_outcome_v1."""

    args = parse_args()
    if not args.execute or not args.confirm_change:
        result = _outcome(
            "failed",
            operation=args.operation,
            keypair_name=args.keypair_name,
            changed=False,
            error_code="KEYPAIR_CHANGE_CONFIRMATION_REQUIRED",
            error_message="both --execute and --confirm-change are required",
        )
    else:
        try:
            result = import_keypair(args) if args.operation == "import" else delete_keypair(args)
        except (OSError, UnicodeError, ValueError) as exc:
            result = _outcome(
                "failed",
                operation=args.operation,
                keypair_name=args.keypair_name,
                changed=False,
                error_code="KEYPAIR_CHANGE_INPUT_INVALID",
                error_message=str(exc),
            )
    hcloud_common.emit_json(result, args.pretty)
    return 0 if result["outcome_status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
