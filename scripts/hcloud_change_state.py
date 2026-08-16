#!/usr/bin/env python3
"""Persist generic Huawei Cloud change receipts and safe resume decisions."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import hcloud_common

SCHEMA_VERSION = 1
RESUMABLE_STATUSES = {
    "submitted",
    "submit_unknown",
    "verification_failed",
    "verified",
}
MAX_IDENTIFIER_VALUES = 256


def utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp for lifecycle records."""
    return datetime.now(UTC).isoformat()


def request_fingerprint(value: Any) -> str:
    """Return a full stable digest for one exact cloud change request."""
    serialized = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _is_identifier_key(key: str) -> bool:
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", key.strip())
    normalized = normalized.replace("-", "_").lower()
    return normalized == "id" or normalized.endswith("_id") or normalized.endswith("_ids")


def _scalar_identifier_values(value: Any) -> list[str]:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, list):
        values: list[str] = []
        for child in value:
            if isinstance(child, (str, int)) and not isinstance(child, bool):
                text = str(child).strip()
                if text and text not in values:
                    values.append(text)
        return values
    return []


def extract_identifiers(value: Any) -> dict[str, list[str]]:
    """Extract bounded identifier receipts from common Huawei API responses.

    Keys are retained as dotted JSON paths so service-specific verification can
    distinguish shapes such as ``instance.id`` and ``publicip.id``. Only scalar
    ``id``, ``*_id``, and ``*_ids`` fields are retained; response bodies and
    unrelated values are deliberately not persisted.
    """
    identifiers: dict[str, list[str]] = {}
    value_count = 0

    def visit(current: Any, path: tuple[str, ...]) -> None:
        nonlocal value_count
        if value_count >= MAX_IDENTIFIER_VALUES:
            return
        if isinstance(current, dict):
            for raw_key, child in current.items():
                key = str(raw_key)
                child_path = (*path, key)
                if _is_identifier_key(key):
                    values = _scalar_identifier_values(child)
                    if values:
                        remaining = MAX_IDENTIFIER_VALUES - value_count
                        selected = values[:remaining]
                        identifiers[".".join(child_path)] = selected
                        value_count += len(selected)
                visit(child, child_path)
        elif isinstance(current, list):
            for child in current:
                visit(child, path)

    visit(value, ())
    return identifiers


def _empty_state(workflow_id: str) -> dict[str, Any]:
    now = utc_timestamp()
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "created_at": now,
        "updated_at": now,
        "steps": {},
    }


def load_state(path: Path, *, workflow_id: str) -> dict[str, Any]:
    """Load lifecycle state or initialize an empty state document."""
    if not path.exists():
        return _empty_state(workflow_id)
    state = hcloud_common.load_json(path)
    if not isinstance(state, dict):
        raise ValueError("Change state must be a JSON object.")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported change state schema_version: {state.get('schema_version')!r}.")
    if state.get("workflow_id") != workflow_id:
        raise ValueError("Change state belongs to a different workflow_id; use a separate state file.")
    if not isinstance(state.get("steps"), dict):
        raise ValueError("Change state steps must be a JSON object.")
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    """Atomically save lifecycle state without exposing partial JSON files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_timestamp()
    payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare_step(
    path: Path,
    *,
    workflow_id: str,
    step_id: str,
    fingerprint: str,
    request_summary: dict[str, Any],
) -> dict[str, Any]:
    """Create or inspect a step and return the only safe next submit action."""
    state = load_state(path, workflow_id=workflow_id)
    steps = state["steps"]
    step = steps.get(step_id)
    if step is None:
        secrets = hcloud_common.collect_json_secrets(request_summary)
        step = {
            "step_id": step_id,
            "fingerprint": fingerprint,
            "status": "planned",
            "request": hcloud_common.redact_json(request_summary, secrets),
            "submit_attempts": 0,
            "created_at": utc_timestamp(),
            "updated_at": utc_timestamp(),
        }
        steps[step_id] = step
        save_state(path, state)
        return {
            "resume_action": "execute_submit",
            "can_submit": True,
            "step": step,
        }

    if step.get("fingerprint") != fingerprint:
        return {
            "resume_action": "fingerprint_mismatch",
            "can_submit": False,
            "step": step,
        }

    status = str(step.get("status") or "planned")
    if status == "verified":
        resume_action = "reuse_verified"
        can_submit = False
    elif status in RESUMABLE_STATUSES:
        resume_action = "verify_existing"
        can_submit = False
    elif status == "submit_failed":
        resume_action = "retry_submit"
        can_submit = True
    else:
        resume_action = "execute_submit"
        can_submit = True
    return {
        "resume_action": resume_action,
        "can_submit": can_submit,
        "step": step,
    }


def _matching_step(
    path: Path,
    *,
    workflow_id: str,
    step_id: str,
    fingerprint: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = load_state(path, workflow_id=workflow_id)
    step = state["steps"].get(step_id)
    if not isinstance(step, dict):
        raise ValueError(f"Unknown change step_id: {step_id}")
    if step.get("fingerprint") != fingerprint:
        raise ValueError("Change step fingerprint no longer matches the planned request.")
    return state, step


def record_submit(
    path: Path,
    *,
    workflow_id: str,
    step_id: str,
    fingerprint: str,
    success: bool,
    identifiers: dict[str, list[str]] | None = None,
    verification_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record whether submit was accepted and the identifiers needed to resume."""
    state, step = _matching_step(
        path,
        workflow_id=workflow_id,
        step_id=step_id,
        fingerprint=fingerprint,
    )
    step["submit_attempts"] = int(step.get("submit_attempts") or 0) + 1
    step["submit"] = {"success": bool(success), "recorded_at": utc_timestamp()}
    # A failed local command result does not prove the cloud rejected the
    # request. Preserve ambiguity and require readback before another submit.
    step["status"] = "submitted" if success else "submit_unknown"
    if identifiers:
        step["identifiers"] = identifiers
    if verification_params:
        step["verification_params"] = verification_params
    step["updated_at"] = utc_timestamp()
    save_state(path, state)
    return step


def record_verification(
    path: Path,
    *,
    workflow_id: str,
    step_id: str,
    fingerprint: str,
    success: bool,
) -> dict[str, Any]:
    """Record the latest business verification outcome for a submitted step."""
    state, step = _matching_step(
        path,
        workflow_id=workflow_id,
        step_id=step_id,
        fingerprint=fingerprint,
    )
    step["verification"] = {
        "success": bool(success),
        "recorded_at": utc_timestamp(),
    }
    step["status"] = "verified" if success else "verification_failed"
    step["updated_at"] = utc_timestamp()
    save_state(path, state)
    return step
