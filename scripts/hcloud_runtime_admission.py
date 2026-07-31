#!/usr/bin/env python3
"""Expose the code-enforced runtime freeze for unbridged cloud side effects."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT_DIR / "references" / "unified-runtime-execution-policy.json"


class RuntimeAdmissionError(ValueError):
    """Raised when the local runtime-admission policy is unavailable or malformed."""


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    """Load the local runtime freeze policy without contacting external systems."""
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeAdmissionError(f"Cannot read runtime admission policy: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeAdmissionError(f"Invalid runtime admission policy: {path}: {exc}") from exc
    if not isinstance(policy, dict) or policy.get("mode") != "hard_freeze_unbridged_mutations":
        raise RuntimeAdmissionError("Runtime admission policy has an unsupported mode.")
    if not isinstance(policy.get("path_groups"), dict):
        raise RuntimeAdmissionError("Runtime admission policy requires path_groups.")
    return policy


def block_result(
    path_group_id: str,
    requested_action: str,
    *,
    reason: str,
    next_action: str,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one uniform plan-only rejection for an unbridged side effect.

    The result is designed for callers to return before creating a subprocess or
    HTTP request.  It is not an authorization object and does not expose a
    compatibility escape hatch.
    """
    policy = policy or load_policy()
    group_policy = policy["path_groups"].get(path_group_id)
    if not isinstance(group_policy, dict):
        raise RuntimeAdmissionError(f"Runtime admission policy has no path group: {path_group_id}")
    return {
        "success": False,
        "planning_only": True,
        "error_type": "UNIFIED_RUNTIME_PLAN_ONLY",
        "error": "Runtime execution is disabled until this path has a Skill-controlled entry.",
        "reason": reason,
        "requested_action": requested_action,
        "next_action": next_action,
        "execution_authority": {
            "mode": "plan_only",
            "submission_authority": "not_implemented",
            "policy_id": policy.get("id"),
            "policy_version": policy.get("version"),
            "path_group_id": path_group_id,
            "path_policy": copy.deepcopy(group_policy),
        },
    }
