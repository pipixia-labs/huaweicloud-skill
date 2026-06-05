#!/usr/bin/env python3
"""Shared helpers for Huawei Cloud CLI skill scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REFERENCES_DIR = ROOT / "references"
REGISTRY_PATH = REFERENCES_DIR / "service-registry.json"

SECRET_HINTS = (
    "access-key",
    "accesskey",
    "secret-key",
    "secretaccesskey",
    "security-token",
    "securitytoken",
    "x-auth-token",
    "auth-token",
    "token",
    "credential",
    "credentials",
    "password",
    "passwd",
    "adminpass",
    "private-key",
    "private_key",
    "privatekey",
    "user-data",
    "user_data",
    "userdata",
)
OBSUTIL_SECRET_ARG_NAMES = {"-i", "-k", "-t", "-token"}


def load_json(path: Path) -> Any:
    """Return parsed JSON content from a UTF-8 file."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Return the curated service registry."""
    return load_json(path)


def emit_json(value: Any, pretty: bool = False) -> None:
    """Print a JSON value using the repository's standard formatting."""
    if pretty:
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(value, ensure_ascii=False))


def collect_known_secrets(config_path: Path | None = None) -> set[str]:
    """Collect locally known hcloud secrets so they can be redacted from output."""
    target = config_path or (Path.home() / ".hcloud" / "config.json")
    if not target.exists():
        return set()

    try:
        config = load_json(target)
    except (OSError, json.JSONDecodeError):
        return set()

    secrets: set[str] = set()
    for profile in config.get("profiles", []):
        for key in ("accessKeyId", "secretAccessKey", "securityToken"):
            value = profile.get(key)
            if value:
                secrets.add(str(value))
    return secrets


def looks_like_secret_arg(arg: str) -> bool:
    """Return True when an argument or JSON key suggests sensitive data."""
    lowered = arg.lower()
    if lowered.split("=", 1)[0] in OBSUTIL_SECRET_ARG_NAMES:
        return True
    return any(hint in lowered for hint in SECRET_HINTS)


def collect_inline_secrets(args: list[str]) -> set[str]:
    """Collect secret values passed directly via CLI argument tokens."""
    secrets: set[str] = set()
    for index, arg in enumerate(args):
        if "=" in arg and looks_like_secret_arg(arg.split("=", 1)[0]):
            secrets.add(arg.split("=", 1)[1])
            continue
        if looks_like_secret_arg(arg) and index + 1 < len(args):
            next_arg = args[index + 1]
            if next_arg and not next_arg.startswith("-"):
                secrets.add(next_arg)
    return secrets


def collect_json_secrets(value: Any) -> set[str]:
    """Collect sensitive scalar values from a JSON-like object."""
    secrets: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if looks_like_secret_arg(str(key)):
                if isinstance(child, str) and child:
                    secrets.add(child)
                elif isinstance(child, (int, float, bool)):
                    secrets.add(str(child))
                continue
            secrets.update(collect_json_secrets(child))
    elif isinstance(value, list):
        for child in value:
            secrets.update(collect_json_secrets(child))
    return secrets


def coerce_output_text(value: str | bytes | None) -> str:
    """Normalize subprocess output to text for redaction and reporting."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def redact_text(text: str | bytes | None, secrets: set[str]) -> str:
    """Replace exact secret values with a redaction marker."""
    redacted = coerce_output_text(text)
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        redacted = redacted.replace(secret, "***")
    return redacted


def redact_command(command: list[str], secrets: set[str]) -> list[str]:
    """Return a command list with sensitive argument values redacted."""
    redacted: list[str] = []
    redact_next = False
    for item in command:
        if redact_next:
            redacted.append(item if item.startswith("-") else "***")
            redact_next = False
            continue
        if "=" in item and looks_like_secret_arg(item.split("=", 1)[0]):
            key = item.split("=", 1)[0]
            redacted.append(f"{key}=***")
        elif looks_like_secret_arg(item):
            redacted.append(item)
            redact_next = True
        else:
            redacted.append(redact_text(item, secrets))
    return redacted


def redact_json(value: Any, secrets: set[str], key: str | None = None) -> Any:
    """Recursively redact sensitive values in parsed JSON-like data."""
    if key is not None and looks_like_secret_arg(key):
        return "***"
    if isinstance(value, dict):
        return {item_key: redact_json(child, secrets, str(item_key)) for item_key, child in value.items()}
    if isinstance(value, list):
        return [redact_json(child, secrets) for child in value]
    if isinstance(value, str):
        return redact_text(value, secrets)
    return value
