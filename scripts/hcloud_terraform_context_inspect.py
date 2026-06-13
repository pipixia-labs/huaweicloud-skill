#!/usr/bin/env python3
"""Inspect local Terraform readiness for Huawei Cloud IaC workflows."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import hcloud_common
import hcloud_terraform_catalog


TERRAFORM_ENV_KEYS = (
    "HW_ACCESS_KEY",
    "HW_SECRET_KEY",
    "HW_REGION_NAME",
    "HW_PROJECT_ID",
    "HW_PROJECT_NAME",
    "HW_DOMAIN_NAME",
    "HW_SECURITY_TOKEN",
    "HUAWEICLOUD_ACCESS_KEY",
    "HUAWEICLOUD_SECRET_KEY",
    "HUAWEICLOUD_REGION",
    "HUAWEICLOUD_PROJECT_ID",
    "HUAWEICLOUD_SECURITY_TOKEN",
    "TF_PLUGIN_CACHE_DIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
)


def env_status() -> dict[str, dict[str, Any]]:
    """Return redacted environment variable status for Terraform-related keys."""
    result = {}
    for key in TERRAFORM_ENV_KEYS:
        value = os.environ.get(key)
        result[key] = {
            "set": value is not None and value != "",
            "empty": value == "",
        }
    return result


def run_command(command: list[str], timeout: int = 15) -> dict[str, Any]:
    """Run a local command and return structured output."""
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except FileNotFoundError:
        return {"found": False, "return_code": None, "stdout": "", "stderr": "command not found"}
    except subprocess.TimeoutExpired:
        return {"found": True, "return_code": None, "stdout": "", "stderr": "timeout"}
    return {
        "found": True,
        "return_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def inspect_terraform() -> dict[str, Any]:
    """Inspect Terraform CLI availability."""
    path = shutil.which("terraform")
    result: dict[str, Any] = {"found": bool(path), "path": path}
    if not path:
        return result
    version = run_command([path, "version"], timeout=15)
    result["version_command"] = version
    version_match = re.search(r"Terraform v([0-9][^\s]+)", version.get("stdout", ""))
    result["version"] = version_match.group(1) if version_match else None
    return result


def inspect_hcloud() -> dict[str, Any]:
    """Inspect hcloud availability for discovery and post-apply verification."""
    path = shutil.which("hcloud")
    result: dict[str, Any] = {"found": bool(path), "path": path}
    if not path:
        return result
    result["version_command"] = run_command([path, "version"], timeout=15)
    return result


def forbidden_artifacts(workdir: Path) -> list[str]:
    """Return Terraform runtime artifacts that should not be committed."""
    if not workdir.exists():
        return []
    patterns = [
        "**/.terraform",
        "**/terraform.tfstate",
        "**/terraform.tfstate.*",
        "**/*.tfvars",
        "**/crash.log",
    ]
    findings: list[str] = []
    for pattern in patterns:
        for path in workdir.glob(pattern):
            if path.name.endswith(".tfvars.example"):
                continue
            findings.append(str(path))
    return sorted(dict.fromkeys(findings))


def provider_cache_hints(workdir: Path) -> dict[str, Any]:
    """Inspect local Terraform provider cache hints."""
    lock_files = sorted(path for path in workdir.rglob(".terraform.lock.hcl")) if workdir.exists() else []
    terraform_dirs = sorted(path for path in workdir.rglob(".terraform") if path.is_dir()) if workdir.exists() else []
    plugin_cache = os.environ.get("TF_PLUGIN_CACHE_DIR")
    return {
        "lock_file_count": len(lock_files),
        "lock_files_sample": [str(path) for path in lock_files[:10]],
        "local_terraform_dir_count": len(terraform_dirs),
        "plugin_cache_dir": plugin_cache,
        "plugin_cache_dir_exists": bool(plugin_cache and Path(plugin_cache).exists()),
    }


def readiness(terraform: dict[str, Any], env: dict[str, dict[str, Any]], forbidden: list[str]) -> dict[str, Any]:
    """Return readiness flags and blockers."""
    has_terraform = bool(terraform.get("found"))
    has_hw_auth = env["HW_ACCESS_KEY"]["set"] and env["HW_SECRET_KEY"]["set"] and env["HW_REGION_NAME"]["set"]
    has_huaweicloud_auth = env["HUAWEICLOUD_ACCESS_KEY"]["set"] and env["HUAWEICLOUD_SECRET_KEY"]["set"] and env["HUAWEICLOUD_REGION"]["set"]
    has_auth = has_hw_auth or has_huaweicloud_auth
    blockers = []
    warnings = []
    if not has_terraform:
        blockers.append("terraform_cli_missing")
    if forbidden:
        warnings.append("terraform_runtime_artifacts_present")
    if not has_hw_auth and has_huaweicloud_auth:
        warnings.append("huaweicloud_env_set_but_hw_env_unset")
    if not has_auth:
        warnings.append("terraform_cloud_credentials_unset")
    return {
        "can_generate": True,
        "can_fmt": has_terraform,
        "can_validate": has_terraform,
        "can_plan": has_terraform and has_auth,
        "can_apply": has_terraform and has_auth,
        "blockers": blockers,
        "warnings": warnings,
        "auth": {
            "hw_env_complete": has_hw_auth,
            "huaweicloud_env_complete": has_huaweicloud_auth,
            "cloud_credentials_complete": has_auth,
        },
        "execution_boundary": "plan/apply require credentials and explicit user confirmation; hcloud remains post-apply verification path",
    }


def build_context(args: argparse.Namespace) -> dict[str, Any]:
    """Build the Terraform context readiness report."""
    workdir = args.workdir.resolve()
    terraform = inspect_terraform()
    env = env_status()
    forbidden = forbidden_artifacts(workdir)
    return {
        "success": True,
        "workdir": str(workdir),
        "terraform": terraform,
        "hcloud": inspect_hcloud(),
        "environment": env,
        "provider_cache": provider_cache_hints(workdir),
        "asset_catalog": {
            "example_catalog": str(hcloud_terraform_catalog.EXAMPLE_CATALOG_PATH),
            "reference_catalog": str(hcloud_terraform_catalog.REFERENCE_CATALOG_PATH),
            "example_catalog_exists": hcloud_terraform_catalog.EXAMPLE_CATALOG_PATH.exists(),
            "reference_catalog_exists": hcloud_terraform_catalog.REFERENCE_CATALOG_PATH.exists(),
        },
        "forbidden_artifacts": forbidden,
        "readiness": readiness(terraform, env, forbidden),
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=hcloud_common.ROOT, help="Directory to inspect for Terraform assets and artifacts.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    """Inspect Terraform readiness."""
    args = parse_args()
    result = build_context(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
