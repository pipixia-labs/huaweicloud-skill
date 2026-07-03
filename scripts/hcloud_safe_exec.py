#!/usr/bin/env python3
"""Execute hcloud commands with structured JSON output and basic secret redaction."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from hcloud_common import (
    collect_inline_secrets,
    collect_json_secrets,
    collect_known_secrets,
    coerce_output_text,
    emit_json,
    load_json,
    looks_like_secret_arg,
    redact_command,
    redact_json,
    redact_text,
)

ERROR_TYPES = ("USE_ERROR", "NETWORK_ERROR", "CLI_ERROR", "OPENAPI_ERROR", "APIE_ERROR")
CLOUD_ERROR_CODE_KEYS = ("error_code", "errorCode", "code", "errCode")
CLOUD_ERROR_MESSAGE_KEYS = ("error_msg", "errorMsg", "message", "msg", "error_description", "reason")

COMMON_ERROR_CATEGORIES = (
    (
        "credential",
        (
            r"\binvalidaccesskeyid\b",
            r"\bsignaturedoesnotmatch\b",
            r"\binvalidcredential\b",
            r"\binvalidtoken\b",
            r"\bauthentication\b",
            r"\baccess key\b",
            r"\bak/sk\b",
            r"\bsignature\b",
        ),
        "Check AK/SK/security token, active profile, and whether the credentials belong to the target Huawei Cloud account or site.",
    ),
    (
        "permission",
        (
            r"\baccessdenied\b",
            r"\bforbidden\b",
            r"\bunauthorized\b",
            r"\bnot authorized\b",
            r"\bpermission\b",
            r"\biam\b",
        ),
        "Check IAM permissions, agency policy, project scope, and whether the service is enabled for this account.",
    ),
    (
        "quota",
        (
            r"\bquota\b",
            r"\binsufficient\b",
            r"\blimit exceeded\b",
            r"\btoo many\b",
        ),
        "Check service quota, resource limits, and current usage before retrying or requesting quota increase.",
    ),
    (
        "region_or_endpoint",
        (
            r"\bunsupported region\b",
            r"\binvalid region\b",
            r"\bregion\b",
            r"\bendpoint\b",
        ),
        "Check --cli-region, endpoint availability, and whether this service accepts the requested CLI region.",
    ),
    (
        "project",
        (
            r"\bproject[_ -]?id\b",
            r"\bproject\b",
        ),
        "Check project_id, region-project mapping, and whether the active profile has access to the target project.",
    ),
    (
        "parameter",
        (
            r"\binvalidparameter\b",
            r"\bmissingparameter\b",
            r"\brequired parameter\b",
            r"\bparameter\b",
            r"\bbad request\b",
            r"\binvalid request\b",
            r"\bunknown flag\b",
            r"\bunknown command\b",
        ),
        "Check operation help, required parameters, JSON body shape, and CLI argument names.",
    ),
    (
        "not_found",
        (
            r"\bnotfound\b",
            r"\bnot found\b",
            r"\bnosuch\b",
            r"\bdoes not exist\b",
        ),
        "Check resource ID/name, region, project, and whether the resource has already been deleted.",
    ),
    (
        "network",
        (
            r"\btimeout\b",
            r"\bconnection refused\b",
            r"\bno such host\b",
            r"\bi/o timeout\b",
            r"\btls handshake\b",
        ),
        "Check connectivity, proxy/DNS settings, and KooCLI timeout/retry configuration.",
    ),
)

ERROR_TYPE_CATEGORY = {
    "USE_ERROR": "parameter",
    "NETWORK_ERROR": "network",
    "CLI_ERROR": "cli_runtime",
    "OPENAPI_ERROR": "cloud_api",
    "APIE_ERROR": "metadata",
    "TIMEOUT": "network",
}
REFERENCES_DIR = Path(__file__).resolve().parents[1] / "references"
IAM_ACTIONS_PATH = REFERENCES_DIR / "iam-actions-catalog.json"


def normalize_bool_text(value: Any) -> Any:
    """Normalize KooCLI config booleans stored as strings."""
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return value


def collect_json_input_secrets(args: argparse.Namespace) -> set[str]:
    """Collect secrets embedded in JSON input text or files when parseable."""
    secrets: set[str] = set()
    try:
        if args.json_input_file:
            secrets.update(collect_json_secrets(load_json(Path(args.json_input_file))))
        if args.json_input_text:
            secrets.update(collect_json_secrets(json.loads(args.json_input_text)))
    except (OSError, json.JSONDecodeError):
        return secrets
    return secrets


def classify_error(stdout: str, stderr: str) -> str | None:
    """Extract the first known KooCLI error type from output."""
    combined = f"{stdout}\n{stderr}"
    for error_type in ERROR_TYPES:
        if f"[{error_type}]" in combined:
            return error_type
    return None


def advice_for_error(error_type: str | None) -> str | None:
    """Return a short next-step hint for a known error type."""
    if error_type == "USE_ERROR":
        return "Re-check the active profile, region, service, operation, and parameter names."
    if error_type == "NETWORK_ERROR":
        return "Check connectivity and consider increasing cli-connect-timeout, cli-read-timeout, and cli-retry-count."
    if error_type == "CLI_ERROR":
        return "KooCLI failed while processing the command. Check local KooCLI logs under ~/.hcloud/logs/ and verify the installed hcloud version."
    if error_type == "OPENAPI_ERROR":
        return "The cloud API rejected the request. Re-check the actual business parameters and service-side constraints."
    if error_type == "APIE_ERROR":
        return "Live metadata lookup failed. Fall back to local meta cache or curated references before guessing parameters."
    return None


def iter_dicts(value: Any) -> list[dict[str, Any]]:
    """Return all dictionaries found inside a JSON-like value."""
    if isinstance(value, dict):
        nested = [value]
        for child in value.values():
            nested.extend(iter_dicts(child))
        return nested
    if isinstance(value, list):
        nested = []
        for child in value:
            nested.extend(iter_dicts(child))
        return nested
    return []


def first_string_field(mapping: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty string value for any known key."""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return None


def extract_cloud_error(parsed_json: Any, stdout: str, stderr: str) -> dict[str, str | None]:
    """Extract cloud error code and message from parsed JSON or text output."""
    for mapping in iter_dicts(parsed_json):
        has_error_key = any(key in mapping for key in ("error", "error_code", "errorCode", "errCode", "error_msg", "errorMsg"))
        if isinstance(mapping.get("error"), dict):
            nested = mapping["error"]
            code = first_string_field(nested, CLOUD_ERROR_CODE_KEYS)
            message = first_string_field(nested, CLOUD_ERROR_MESSAGE_KEYS)
            if code or message:
                return {"code": code, "message": message, "source": "parsed_json"}
        if not has_error_key:
            continue
        code = first_string_field(mapping, CLOUD_ERROR_CODE_KEYS)
        message = first_string_field(mapping, CLOUD_ERROR_MESSAGE_KEYS)
        if code or message:
            return {"code": code, "message": message, "source": "parsed_json"}

    combined = f"{stdout}\n{stderr}"
    bracket_match = re.search(
        r"error code\s+\[(?P<code>[^\]]+)\].*?error message\s+\[(?P<message>[^\]]+)\]",
        combined,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if bracket_match:
        return {
            "code": bracket_match.group("code").strip(),
            "message": bracket_match.group("message").strip(),
            "source": "text",
        }

    code_match = re.search(
        r'"(?:error_code|errorCode|errCode)"\s*:\s*"(?P<code>[^"]+)"',
        combined,
        flags=re.IGNORECASE,
    )
    message_match = re.search(
        r'"(?:error_msg|errorMsg|message|msg)"\s*:\s*"(?P<message>[^"\n]+)"',
        combined,
        flags=re.IGNORECASE,
    )
    if code_match or message_match:
        return {
            "code": code_match.group("code").strip() if code_match else None,
            "message": message_match.group("message").strip() if message_match else None,
            "source": "text",
        }
    return {"code": None, "message": None, "source": None}


def load_iam_actions_catalog(path: Path = IAM_ACTIONS_PATH) -> dict[str, Any]:
    """Return the local IAM action hint catalog when available."""
    try:
        value = load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def iam_action_hint(
    service: str | None,
    operation: str | None,
    *,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return best-effort IAM action hints for a service operation."""
    if not service:
        return None
    catalog = catalog if catalog is not None else load_iam_actions_catalog()
    services = catalog.get("services") if isinstance(catalog.get("services"), dict) else {}
    service_key = str(service).upper()
    service_entry = services.get(service_key)
    if not isinstance(service_entry, dict):
        return None

    operation_key = str(operation or "").strip()
    operations = service_entry.get("operations") if isinstance(service_entry.get("operations"), dict) else {}
    operation_entry = operations.get(operation_key)
    match = "operation"
    if not isinstance(operation_entry, dict):
        operation_entry = None
        match = "service_default"

    actions = []
    risk = None
    notes = None
    if operation_entry:
        actions = [str(item) for item in operation_entry.get("required_actions", []) if str(item).strip()]
        risk = operation_entry.get("risk")
        notes = operation_entry.get("notes")

    if not actions:
        actions_key = "default_change_actions" if risk in {"change", "destructive"} else "default_readonly_actions"
        actions = [str(item) for item in service_entry.get(actions_key, []) if str(item).strip()]

    if not actions:
        return None

    return {
        "source": "references/iam-actions-catalog.json",
        "service": service_key,
        "operation": operation_key or None,
        "match": match,
        "risk": risk or "unknown",
        "permission_scope": service_entry.get("permission_scope") or "unknown",
        "required_actions": actions,
        "notes": notes,
        "verify_exact_policy": True,
        "next_steps": [
            "Check allow and explicit-deny policies for the required action hints.",
            "Check region/project or enterprise-project scope, agency trust, service enablement, and organization-level SCP/custom deny rules.",
        ],
    }


def classify_common_error(
    error_type: str | None,
    stdout: str,
    stderr: str,
    parsed_json: Any,
    service: str | None = None,
    operation: str | None = None,
) -> dict[str, Any] | None:
    """Return a structured diagnosis for common hcloud configuration and API failures."""
    if not error_type and not stdout and not stderr and parsed_json is None:
        return None

    cloud_error = extract_cloud_error(parsed_json, stdout, stderr)
    combined = "\n".join(
        item
        for item in (
            error_type or "",
            cloud_error.get("code") or "",
            cloud_error.get("message") or "",
            stdout,
            stderr,
        )
        if item
    )

    signals: list[str] = []
    category = ERROR_TYPE_CATEGORY.get(error_type or "", "unknown")
    advice = advice_for_error(error_type)
    for candidate, patterns, candidate_advice in COMMON_ERROR_CATEGORIES:
        matched_patterns = [pattern for pattern in patterns if re.search(pattern, combined, flags=re.IGNORECASE)]
        if matched_patterns:
            category = candidate
            advice = candidate_advice
            signals.extend(matched_patterns[:3])
            break

    if error_type == "APIE_ERROR" and category == "metadata":
        advice = advice or "Live metadata lookup failed. Use local metadata cache, curated references, or official docs."
    if category == "unknown" and not cloud_error.get("code") and not cloud_error.get("message"):
        return None

    details = {
        "category": category,
        "error_type": error_type,
        "cloud_error_code": cloud_error.get("code"),
        "cloud_error_message": cloud_error.get("message"),
        "source": cloud_error.get("source") or ("error_type" if error_type else "text"),
        "signals": signals,
        "advice": advice,
    }
    if category == "permission":
        permission_hint = iam_action_hint(service, operation)
        if permission_hint:
            details["permission_hint"] = permission_hint
    return details


def trim_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Trim text to a maximum length and report whether truncation happened."""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def maybe_parse_json(stdout: str | bytes | None) -> tuple[Any | None, str | None]:
    """Try to parse stdout as JSON."""
    stdout = coerce_output_text(stdout)
    stripped = stdout.strip()
    if not stripped:
        return None, None
    try:
        return json.loads(stripped), None
    except json.JSONDecodeError as exc:
        decoder = json.JSONDecoder()
        for marker in ("{", "["):
            marker_index = stripped.find(marker)
            if marker_index >= 0:
                candidate = stripped[marker_index:]
                try:
                    parsed, _ = decoder.raw_decode(candidate)
                    return parsed, None
                except json.JSONDecodeError:
                    continue
        return None, str(exc)


def build_command(args: argparse.Namespace, temp_json_file: Path | None) -> list[str]:
    """Build the final hcloud subprocess command."""
    binary = shutil.which("hcloud")
    if not binary:
        raise FileNotFoundError("hcloud binary not found in PATH.")

    if args.command_part:
        command = [binary] + args.command_part
    else:
        command = [binary, args.service, args.operation]

    command.extend(args.arg)

    if args.json_input_file:
        command.append(f"--cli-jsonInput={args.json_input_file}")
    if temp_json_file is not None:
        command.append(f"--cli-jsonInput={temp_json_file}")

    return command


def ensure_json_input_args(args: argparse.Namespace) -> None:
    """Validate JSON input arguments."""
    if args.json_input_file and args.json_input_text:
        raise ValueError("Use either --json-input-file or --json-input-text, not both.")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", help="Huawei Cloud service name, for example ECS.")
    parser.add_argument("--operation", help="Huawei Cloud operation name, for example ListFlavors.")
    parser.add_argument(
        "--command-part",
        action="append",
        default=[],
        help="Generic hcloud command parts, for example --command-part=configure --command-part=show.",
    )
    parser.add_argument(
        "--arg",
        action="append",
        default=[],
        help="A raw hcloud argument token. Use the = form, for example --arg=--cli-region=cn-north-4.",
    )
    parser.add_argument("--json-input-file", help="Existing JSON file path to pass via --cli-jsonInput.")
    parser.add_argument("--json-input-text", help="Inline JSON text to write to a temporary file for --cli-jsonInput.")
    parser.add_argument("--cwd", help="Working directory for the hcloud subprocess.")
    parser.add_argument("--timeout", type=int, default=120, help="Subprocess timeout in seconds.")
    parser.add_argument("--max-output-chars", type=int, default=20000, help="Maximum number of chars kept for stdout and stderr.")
    parser.add_argument("--expect-json", action="store_true", help="Attempt to parse stdout as JSON.")
    parser.add_argument("--result-file", help="Optional path to save the full structured result JSON.")
    parser.add_argument("--parsed-json-file", help="Optional path to save only parsed_json when available.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON result.")
    args = parser.parse_args()

    if not args.command_part and not (args.service and args.operation):
        parser.error("Provide either --command-part ... or both --service and --operation.")
    if args.command_part and (args.service or args.operation):
        parser.error("Do not mix --command-part with --service/--operation.")

    return args


def main() -> int:
    """Run hcloud and print a structured execution result."""
    args = parse_args()
    ensure_json_input_args(args)

    temp_json_file: Path | None = None
    if args.json_input_text:
        temp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        temp.write(args.json_input_text)
        temp.flush()
        temp.close()
        temp_json_file = Path(temp.name)

    known_secrets = collect_known_secrets()
    known_secrets.update(collect_inline_secrets(args.arg + args.command_part))
    known_secrets.update(collect_json_input_secrets(args))

    started_at = time.time()
    try:
        command = build_command(args, temp_json_file)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=args.cwd,
            timeout=args.timeout,
            check=False,
        )
        duration_seconds = round(time.time() - started_at, 3)
        raw_stdout = completed.stdout
        raw_stderr = completed.stderr
        parsed_json = None
        parsed_json_error = None
        if args.expect_json:
            parsed_json, parsed_json_error = maybe_parse_json(raw_stdout)
            if parsed_json is not None:
                known_secrets.update(collect_json_secrets(parsed_json))

        redacted_stdout = redact_text(raw_stdout, known_secrets)
        redacted_stderr = redact_text(raw_stderr, known_secrets)
        stdout_trimmed, stdout_truncated = trim_text(redacted_stdout, args.max_output_chars)
        stderr_trimmed, stderr_truncated = trim_text(redacted_stderr, args.max_output_chars)
        error_type = classify_error(raw_stdout, raw_stderr)
        redacted_parsed_json = redact_json(parsed_json, known_secrets) if parsed_json is not None else None
        cloud_error = extract_cloud_error(redacted_parsed_json, redacted_stdout, redacted_stderr)
        has_cloud_error = bool(cloud_error.get("code") or cloud_error.get("message"))
        logical_success = completed.returncode == 0 and error_type is None and not has_cloud_error

        error_details = None
        if not logical_success:
            error_details = classify_common_error(
                error_type,
                redacted_stdout,
                redacted_stderr,
                redacted_parsed_json,
                args.service,
                args.operation,
            )

        result = {
            "success": logical_success,
            "return_code": completed.returncode,
            "duration_seconds": duration_seconds,
            "service": args.service,
            "operation": args.operation,
            "command": redact_command(command, known_secrets),
            "stdout": stdout_trimmed,
            "stderr": stderr_trimmed,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "error_type": error_type,
            "error_details": error_details,
            "advice": (error_details or {}).get("advice") or advice_for_error(error_type),
            "parsed_json": redacted_parsed_json,
            "parsed_json_error": parsed_json_error,
            "config_context": {
                "cwd": args.cwd,
                "timeout": args.timeout,
                "expect_json": args.expect_json,
                "used_temp_json_input": bool(temp_json_file),
            },
        }
    except FileNotFoundError as exc:
        result = {
            "success": False,
            "return_code": None,
            "duration_seconds": round(time.time() - started_at, 3),
            "service": args.service,
            "operation": args.operation,
            "command": [],
            "stdout": "",
            "stderr": str(exc),
            "stdout_truncated": False,
            "stderr_truncated": False,
            "error_type": None,
            "error_details": {
                "category": "local_environment",
                "error_type": None,
                "cloud_error_code": None,
                "cloud_error_message": str(exc),
                "source": "exception",
                "signals": ["hcloud binary not found"],
                "advice": "Install KooCLI or make sure `hcloud` is available in PATH.",
            },
            "advice": "Install KooCLI or make sure `hcloud` is available in PATH.",
            "parsed_json": None,
            "parsed_json_error": None,
            "config_context": {
                "cwd": args.cwd,
                "timeout": args.timeout,
                "expect_json": args.expect_json,
                "used_temp_json_input": bool(temp_json_file),
            },
        }
    except subprocess.TimeoutExpired as exc:
        stdout_text = coerce_output_text(exc.stdout)
        stderr_text = coerce_output_text(exc.stderr)
        result = {
            "success": False,
            "return_code": None,
            "duration_seconds": round(time.time() - started_at, 3),
            "service": args.service,
            "operation": args.operation,
            "command": redact_command(exc.cmd if isinstance(exc.cmd, list) else [], known_secrets),
            "stdout": redact_text(stdout_text, known_secrets),
            "stderr": redact_text(stderr_text, known_secrets),
            "stdout_truncated": False,
            "stderr_truncated": False,
            "error_type": "TIMEOUT",
            "error_details": {
                "category": "network",
                "error_type": "TIMEOUT",
                "cloud_error_code": None,
                "cloud_error_message": "The command timed out.",
                "source": "exception",
                "signals": ["timeout"],
                "advice": "The command timed out. Consider increasing --timeout or KooCLI timeout arguments.",
            },
            "advice": "The command timed out. Consider increasing --timeout or KooCLI timeout arguments.",
            "parsed_json": None,
            "parsed_json_error": None,
            "config_context": {
                "cwd": args.cwd,
                "timeout": args.timeout,
                "expect_json": args.expect_json,
                "used_temp_json_input": bool(temp_json_file),
            },
        }
    finally:
        if temp_json_file and temp_json_file.exists():
            temp_json_file.unlink()

    if args.result_file:
        result_path = Path(args.result_file)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.parsed_json_file and result.get("parsed_json") is not None:
        parsed_path = Path(args.parsed_json_file)
        parsed_path.parent.mkdir(parents=True, exist_ok=True)
        parsed_path.write_text(
            json.dumps(result["parsed_json"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    emit_json(result, pretty=args.pretty)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
