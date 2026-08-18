#!/usr/bin/env python3
"""Render and validate portable cross-Agent huaweicloud-skill evaluations."""

from __future__ import annotations

import argparse
import copy
from collections import defaultdict
from pathlib import Path
from typing import Any

import hcloud_common

PACK_PATH = hcloud_common.ROOT / "references" / "cross-agent-evaluation-cases.json"


def load_pack(path: Path = PACK_PATH) -> dict[str, Any]:
    """Load and minimally validate the cross-Agent evaluation case pack."""

    payload = hcloud_common.load_json(path)
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported cross-Agent evaluation schema version.")
    if not isinstance(payload.get("cases"), list):
        raise ValueError("Cross-Agent evaluation pack must contain a cases list.")
    return payload


def find_case(case_id: str, *, pack: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return one evaluation case or raise a clear error."""

    payload = pack if pack is not None else load_pack()
    for item in payload.get("cases", []):
        if isinstance(item, dict) and item.get("id") == case_id:
            return copy.deepcopy(item)
    raise ValueError(f"Unknown evaluation case: {case_id}")


def build_result_template(
    case_id: str,
    *,
    run_id: str,
    pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an Agent-neutral observation template for one run."""

    case = find_case(case_id, pack=pack)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "case_id": case_id,
        "skill_revision": None,
        "agent": None,
        "agent_version": None,
        "model": None,
        "model_version": None,
        "tool_permissions": None,
        "workspace_topology": None,
        "real_cloud_mutation": "none"
        if case["cloud_mutation"] == "none"
        else "explicit_opt_in_not_yet_confirmed",
        "elapsed_seconds": None,
        "tool_call_count": None,
        "token_usage": None,
        "adoption_state": None,
        "checks": [
            {
                "id": check["id"],
                "category": check["category"],
                "required": bool(check.get("required")),
                "status": None,
                "evidence": None,
                "note": None,
            }
            for check in case.get("checks", [])
        ],
        "hard_failures": [],
        "artifacts": {
            "final_response": None,
            "tool_trace": None,
            "task_memory": None,
        },
        "reviewer_note": None,
    }


def _score_checks(checks: list[dict[str, Any]], hard_failures: list[Any]) -> dict[str, Any]:
    """Return raw check counts and a non-compensating result."""

    counts = {status: 0 for status in ("pass", "fail", "not_observable")}
    for item in checks:
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    total = len(checks)
    if hard_failures or counts["fail"]:
        result = "fail"
    elif counts["not_observable"] or counts["pass"] != total:
        result = "not_observable"
    else:
        result = "pass"
    return {
        "passed": counts["pass"],
        "failed": counts["fail"],
        "not_observable": counts["not_observable"],
        "total": total,
        "hard_failure_count": len(hard_failures),
        "result": result,
    }


def validate_result(
    result: dict[str, Any],
    *,
    pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one human-observed run and return explicit score evidence."""

    payload = pack if pack is not None else load_pack()
    issues: list[str] = []
    case_id = str(result.get("case_id") or "")
    try:
        case = find_case(case_id, pack=payload)
    except ValueError as exc:
        return {"valid": False, "issues": [str(exc)], "score": None}
    for field in ("run_id", "agent", "model"):
        if not result.get(field):
            issues.append(f"Missing required run field: {field}")
    expected_checks = {item["id"] for item in case.get("checks", [])}
    checks = result.get("checks")
    if not isinstance(checks, list):
        issues.append("checks must be a list")
        checks = []
    observed_checks = {str(item.get("id")) for item in checks if isinstance(item, dict)}
    if observed_checks != expected_checks:
        issues.append("checks must contain every case check exactly once")
    allowed_statuses = set(payload.get("check_statuses", []))
    for item in checks:
        if not isinstance(item, dict):
            issues.append("every check must be an object")
            continue
        if item.get("status") not in allowed_statuses:
            issues.append(f"Invalid check status for {item.get('id')}")
        if item.get("status") in allowed_statuses and not item.get("evidence"):
            issues.append(f"Missing evidence for check {item.get('id')}")
    hard_failures = result.get("hard_failures")
    if not isinstance(hard_failures, list):
        issues.append("hard_failures must be a list")
        hard_failures = []
    allowed_hard_failures = set(payload.get("hard_failure_categories", []))
    for item in hard_failures:
        if not isinstance(item, dict) or item.get("category") not in allowed_hard_failures:
            issues.append("hard failure has an invalid category")
        elif not item.get("evidence"):
            issues.append("hard failure evidence is required")
    return {
        "valid": not issues,
        "issues": issues,
        "score": _score_checks(checks, hard_failures) if not issues else None,
    }


def aggregate_results(
    results: list[dict[str, Any]],
    *,
    pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate valid observations by Agent, model, and case with raw counts."""

    payload = pack if pack is not None else load_pack()
    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "run_count": 0,
            "passed_runs": 0,
            "failed_runs": 0,
            "not_observable_runs": 0,
            "hard_failure_count": 0,
            "check_passed": 0,
            "check_failed": 0,
            "check_not_observable": 0,
            "check_total": 0,
        }
    )
    invalid: list[dict[str, Any]] = []
    result_counter = {
        "pass": "passed_runs",
        "fail": "failed_runs",
        "not_observable": "not_observable_runs",
    }
    for result in results:
        validation = validate_result(result, pack=payload)
        if not validation["valid"]:
            invalid.append(
                {"run_id": result.get("run_id"), "issues": validation["issues"]}
            )
            continue
        key = (str(result["agent"]), str(result["model"]), str(result["case_id"]))
        group = groups[key]
        score = validation["score"]
        group["run_count"] += 1
        group[result_counter[score["result"]]] += 1
        group["hard_failure_count"] += score["hard_failure_count"]
        group["check_passed"] += score["passed"]
        group["check_failed"] += score["failed"]
        group["check_not_observable"] += score["not_observable"]
        group["check_total"] += score["total"]
    rendered_groups = []
    for (agent, model, case_id), values in sorted(groups.items()):
        rendered_groups.append(
            {"agent": agent, "model": model, "case_id": case_id, **values}
        )
    return {
        "success": not invalid,
        "run_count": len(results),
        "valid_run_count": len(results) - len(invalid),
        "invalid_runs": invalid,
        "groups": rendered_groups,
    }


def parse_args() -> argparse.Namespace:
    """Parse local cross-Agent evaluation arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-path", type=Path, default=PACK_PATH)
    parser.add_argument("--pretty", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List available evaluation cases.")
    render = subparsers.add_parser("render", help="Render one exact test prompt and checks.")
    render.add_argument("--case", required=True)
    template = subparsers.add_parser("template", help="Create one result template.")
    template.add_argument("--case", required=True)
    template.add_argument("--run-id", required=True)
    validate = subparsers.add_parser("validate", help="Validate one completed result JSON.")
    validate.add_argument("--input", type=Path, required=True)
    aggregate = subparsers.add_parser("aggregate", help="Aggregate a JSON list of results.")
    aggregate.add_argument("--input", type=Path, required=True)
    return parser.parse_args()


def build_cli_result(args: argparse.Namespace) -> dict[str, Any]:
    """Build one CLI response without executing an Agent or cloud request."""

    pack = load_pack(args.pack_path)
    if args.command == "list":
        return {
            "success": True,
            "mode": "list",
            "cases": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "cloud_mutation": item["cloud_mutation"],
                    "recommended_timeout_minutes": item["recommended_timeout_minutes"],
                }
                for item in pack["cases"]
            ],
        }
    if args.command == "render":
        return {"success": True, "mode": "render", "case": find_case(args.case, pack=pack)}
    if args.command == "template":
        return {
            "success": True,
            "mode": "template",
            "result": build_result_template(args.case, run_id=args.run_id, pack=pack),
        }
    input_payload = hcloud_common.load_json(args.input)
    if args.command == "validate":
        validation = validate_result(input_payload, pack=pack)
        return {"success": validation["valid"], "mode": "validate", **validation}
    if not isinstance(input_payload, list):
        raise ValueError("Aggregate input must be a JSON list of result objects.")
    return {"mode": "aggregate", **aggregate_results(input_payload, pack=pack)}


def main() -> int:
    """Print local evaluation metadata or validation results."""

    args = parse_args()
    try:
        result = build_cli_result(args)
    except (OSError, ValueError) as exc:
        result = {"success": False, "mode": "error", "error": str(exc)}
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
