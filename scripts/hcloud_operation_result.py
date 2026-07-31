#!/usr/bin/env python3
"""Normalize a redacted local operation result into the portable result envelope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import hcloud_unified_contracts
import hcloud_unified_policy


RESULT_STAGES = {"discover", "plan", "dry_run", "submit", "verify"}


def source_error_fields(source_result: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Extract already-redacted error signals from common script result shapes."""
    details = source_result.get("error_details")
    if not isinstance(details, dict):
        details = {}
    cloud_error = source_result.get("cloud_error")
    if not isinstance(cloud_error, dict):
        cloud_error = {}
    error_type = source_result.get("error_type") or details.get("error_type")
    error_code = (
        source_result.get("cloud_error_code")
        or details.get("cloud_error_code")
        or cloud_error.get("code")
    )
    error_message = (
        source_result.get("cloud_error_message")
        or details.get("cloud_error_message")
        or cloud_error.get("message")
        or source_result.get("error")
    )
    return (
        str(error_type) if error_type else None,
        str(error_code) if error_code else None,
        str(error_message) if error_message else None,
    )


def source_success(source_result: dict[str, Any]) -> bool | None:
    """Resolve an explicit success signal without guessing from a process exit code."""
    value = source_result.get("success")
    return value if isinstance(value, bool) else None


def build_operation_result(source_result: dict[str, Any], stage: str) -> dict[str, Any]:
    """Build a portable, secret-safe result summary without replaying an operation.

    The source input is expected to have already applied its own redaction policy.
    This adapter preserves only result classification metadata and never copies raw
    stdout, stderr, command arguments, request bodies, or response payloads.
    """
    if stage not in RESULT_STAGES:
        raise ValueError(f"Unsupported result stage: {stage}")
    secret_paths = hcloud_unified_contracts.secret_field_paths(source_result)
    if secret_paths:
        raise ValueError("Source result contains secret-bearing fields: " + ", ".join(secret_paths))

    success = source_success(source_result)
    error_type, cloud_error_code, cloud_error_message = source_error_fields(source_result)
    source_name = str(source_result.get("source") or "local_adapter")
    evidence = [
        {
            "kind": "source_result",
            "source": source_name,
            "success": success,
            "error_type": error_type,
            "cloud_error_code": cloud_error_code,
        }
    ]
    if success is True and not error_type and not cloud_error_code and not cloud_error_message:
        return {
            "schema_version": "operation-result/v1",
            "stage": stage,
            "outcome": "succeeded",
            "facts": [{"kind": "source_success", "value": True}],
            "evidence": evidence,
            "risks": [],
            "gaps": [],
            "next_actions": [{"action": "continue_lifecycle", "stage": stage}],
            "user_summary": f"已归一化 {stage} 阶段的成功结果；仍需按 Action Plan 完成后续验证。",
        }

    error_decision = hcloud_unified_policy.classify_operation_error(
        error_type=error_type,
        cloud_error_code=cloud_error_code,
        cloud_error_message=cloud_error_message,
        stage=stage,
    )
    outcome = "failed" if success is False or error_type or cloud_error_code or cloud_error_message else "unknown"
    return {
        "schema_version": "operation-result/v1",
        "stage": stage,
        "outcome": outcome,
        "facts": [{"kind": "source_success", "value": success}],
        "evidence": evidence,
        "risks": [
            {
                "kind": "operation_error",
                "category": error_decision["category"],
                "automatic_retry_allowed": error_decision["automatic_retry_allowed"],
            }
        ],
        "gaps": ([{"kind": "error_context", "status": "requires_review"}] if outcome == "unknown" else []),
        "next_actions": [
            {
                "action": "follow_error_policy",
                "retry": error_decision["retry"],
                "instruction": error_decision["next_action"],
            }
        ],
        "error_policy": error_decision,
        "user_summary": f"{stage} 阶段未被视为成功；请先按 {error_decision['category']} 处置并保留脱敏证据，禁止自动重试。",
    }


def load_source_result(path: Path) -> dict[str, Any]:
    """Load a JSON object produced by a local script without invoking that script."""
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read source result: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid source result JSON: {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("Source result must be a JSON object.")
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the local result-normalization command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Redacted local script result JSON.")
    parser.add_argument("--stage", required=True, choices=sorted(RESULT_STAGES))
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Normalize one local result and print it without any cloud call or retry."""
    args = parse_args(argv)
    try:
        result = build_operation_result(load_source_result(args.input), args.stage)
        validation = hcloud_unified_contracts.validate_contract("operation-result", result)
        if not validation["success"]:
            raise ValueError("Normalized result violates contract: " + "; ".join(validation["errors"]))
    except ValueError as exc:
        result = {"success": False, "error": str(exc), "execution_boundary": "No source operation was replayed."}
        exit_code = 2
    else:
        result = {
            "success": True,
            "operation_result": result,
            "execution_boundary": "Local normalization only; no cloud request or retry was sent.",
        }
        exit_code = 0
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
