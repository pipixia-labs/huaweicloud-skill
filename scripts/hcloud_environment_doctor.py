#!/usr/bin/env python3
"""Check local Huawei Cloud tool readiness without installing or calling cloud APIs."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import hcloud_common
import hcloud_context_inspect
import hcloud_terraform_context_inspect


MIN_PYTHON = (3, 10)
NEED_CHOICES = ("hcloud", "live", "sdk", "terraform", "obsutil", "maas")
HCLOUD_INSTALL_COMMANDS = [
    "curl -sSL https://cn-north-4-hdn-koocli.obs.cn-north-4.myhuaweicloud.com/cli/latest/hcloud_install.sh -o ./hcloud_install.sh",
    "bash ./hcloud_install.sh -y",
    "hcloud version",
]
HCLOUD_CONFIG_COMMANDS = [
    "hcloud configure init --cli-profile <profile-name>",
    "hcloud configure list",
]
SDK_INSTALL_COMMANDS = [
    "python3 -m pip install huaweicloudsdkcore huaweicloudsdkecs huaweicloudsdkvpc",
]
TERRAFORM_CHECK_COMMANDS = [
    "terraform version",
    "python3 scripts/hcloud_terraform_context_inspect.py --pretty",
]
OBSUTIL_CHECK_COMMANDS = [
    "obsutil version",
]


def run_command(command: list[str], timeout: int = 15) -> dict[str, Any]:
    """Run a local command for version checks only."""
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


def check_item(
    name: str,
    status: str,
    *,
    required: bool,
    summary: str,
    details: dict[str, Any] | None = None,
    next_actions: list[str] | None = None,
    install_commands: list[str] | None = None,
) -> dict[str, Any]:
    """Build one normalized environment check result."""
    return {
        "name": name,
        "status": status,
        "required": required,
        "summary": summary,
        "details": details or {},
        "next_actions": next_actions or [],
        "install_commands": install_commands or [],
    }


def inspect_python() -> dict[str, Any]:
    """Inspect Python runtime compatibility for local helper scripts."""
    version = sys.version_info[:3]
    ok = version >= MIN_PYTHON
    return check_item(
        "python",
        "ok" if ok else "blocker",
        required=True,
        summary=f"Python {version[0]}.{version[1]}.{version[2]}",
        details={
            "version": list(version),
            "minimum": list(MIN_PYTHON),
            "executable": sys.executable,
            "platform": platform.platform(),
        },
        next_actions=[] if ok else ["Install Python 3.10+ and rerun this doctor."],
    )


def inspect_hcloud() -> dict[str, Any]:
    """Inspect KooCLI and hcloud config without making cloud API calls."""
    summary = hcloud_context_inspect.build_summary(include_meta_files=False)
    hcloud = summary.get("hcloud", {})
    config = summary.get("config", {})
    found = bool(hcloud.get("found"))
    current_profile = config.get("current_profile") if isinstance(config, dict) else None
    profile_auth_ready = bool(
        isinstance(current_profile, dict)
        and (
            current_profile.get("has_access_key")
            or current_profile.get("mode") in {"ecsAgency", "SSO", "AssumeRole"}
        )
    )
    status = "ok" if found else "blocker"
    next_actions = []
    install_commands = []
    if not found:
        next_actions.append("Install Huawei Cloud KooCLI before live hcloud discovery or changes.")
        install_commands = HCLOUD_INSTALL_COMMANDS
    if found and not profile_auth_ready:
        next_actions.append("Configure or choose an hcloud profile before live cloud calls.")
    meta_repo = summary.get("meta_repo", {})
    return check_item(
        "hcloud",
        status,
        required=True,
        summary="KooCLI is available." if found else "KooCLI hcloud binary is missing.",
        details={
            "hcloud": hcloud,
            "config_exists": config.get("exists") if isinstance(config, dict) else False,
            "current_profile_name": config.get("current_profile_name") if isinstance(config, dict) else None,
            "profile_auth_ready": profile_auth_ready,
            "meta_repo": {
                "exists": meta_repo.get("exists") if isinstance(meta_repo, dict) else False,
                "services_file_exists": meta_repo.get("services_file_exists") if isinstance(meta_repo, dict) else False,
                "cached_service_count": meta_repo.get("cached_service_count") if isinstance(meta_repo, dict) else 0,
                "services_update_time": meta_repo.get("services_update_time") if isinstance(meta_repo, dict) else None,
                "template_service_count": len(meta_repo.get("template_services", [])) if isinstance(meta_repo, dict) else 0,
                "template_file_count": meta_repo.get("template_file_count") if isinstance(meta_repo, dict) else 0,
            },
        },
        next_actions=next_actions,
        install_commands=install_commands,
    )


def env_presence(keys: list[str]) -> dict[str, dict[str, bool]]:
    """Return redacted presence information for environment variables."""
    return {key: {"set": bool(os.environ.get(key)), "empty": os.environ.get(key) == ""} for key in keys}


def inspect_auth(needs: set[str]) -> dict[str, Any]:
    """Inspect cloud credential hints without exposing values."""
    keys = [
        "HW_ACCESS_KEY",
        "HW_SECRET_KEY",
        "HW_REGION_NAME",
        "HW_SECURITY_TOKEN",
        "OS_ACCESS_KEY",
        "OS_SECRET_KEY",
        "OS_REGION_NAME",
        "HUAWEICLOUD_ACCESS_KEY",
        "HUAWEICLOUD_SECRET_KEY",
        "HUAWEICLOUD_REGION",
        "HUAWEI_ACCESS_KEY",
        "HUAWEI_SECRET_KEY",
        "HUAWEI_PROJECT_ID",
        "HUAWEI_REGION",
        "HUAWEI_DOMAIN_ID",
        "MAAS_API_KEY",
        "MODELARTS_MAAS_API_KEY",
    ]
    env = env_presence(keys)
    hw_complete = env["HW_ACCESS_KEY"]["set"] and env["HW_SECRET_KEY"]["set"] and env["HW_REGION_NAME"]["set"]
    os_complete = env["OS_ACCESS_KEY"]["set"] and env["OS_SECRET_KEY"]["set"] and env["OS_REGION_NAME"]["set"]
    huaweicloud_complete = (
        env["HUAWEICLOUD_ACCESS_KEY"]["set"]
        and env["HUAWEICLOUD_SECRET_KEY"]["set"]
        and env["HUAWEICLOUD_REGION"]["set"]
    )
    huawei_complete = (
        env["HUAWEI_ACCESS_KEY"]["set"]
        and env["HUAWEI_SECRET_KEY"]["set"]
        and env["HUAWEI_REGION"]["set"]
    )
    cloud_ready = hw_complete or os_complete or huaweicloud_complete or huawei_complete
    live_required = "live" in needs
    status = "ok" if cloud_ready else ("blocker" if live_required else "warning")
    return check_item(
        "cloud_credentials",
        status,
        required=live_required,
        summary="Cloud credential environment looks complete." if cloud_ready else "No complete cloud credential environment was found.",
        details={
            "environment": env,
            "auth_modes": {
                "hw_env_complete": hw_complete,
                "os_env_complete": os_complete,
                "huaweicloud_env_complete": huaweicloud_complete,
                "huawei_env_complete": huawei_complete,
                "maas_api_key_set": env["MAAS_API_KEY"]["set"] or env["MODELARTS_MAAS_API_KEY"]["set"],
            },
        },
        next_actions=[] if cloud_ready else [
            "Use an existing hcloud profile, or set HW_ACCESS_KEY/HW_SECRET_KEY/HW_REGION_NAME for one-off commands.",
            "Existing HUAWEI_ACCESS_KEY/HUAWEI_SECRET_KEY/HUAWEI_REGION variables can be mapped to HW_* for Terraform subprocesses.",
            "Never paste AK/SK into chat or logs; configure them locally through hcloud or environment variables.",
        ],
        install_commands=HCLOUD_CONFIG_COMMANDS if not cloud_ready else [],
    )


def inspect_sdk(needs: set[str]) -> dict[str, Any]:
    """Inspect optional Huawei Cloud Python SDK availability."""
    sdk_runtime = hcloud_context_inspect.inspect_sdk_runtime(hcloud_context_inspect.hcloud_sdk_catalog.DEFAULT_SDK_ROOT)
    installed_count = int(sdk_runtime.get("installed_package_count") or 0)
    required = "sdk" in needs
    status = "ok" if installed_count else ("blocker" if required else "skipped")
    return check_item(
        "huaweicloud_python_sdk",
        status,
        required=required,
        summary="Huawei Cloud Python SDK packages are installed." if installed_count else "SDK is optional and not installed.",
        details=sdk_runtime,
        next_actions=[] if installed_count else ["Install only the service SDK packages needed by a selected SDK supplement."],
        install_commands=[] if installed_count else SDK_INSTALL_COMMANDS,
    )


def inspect_terraform(needs: set[str], workdir: Path) -> dict[str, Any]:
    """Inspect optional Terraform readiness through the existing Terraform inspector."""
    context = hcloud_terraform_context_inspect.build_context(SimpleNamespace(workdir=workdir))
    found = bool(context.get("terraform", {}).get("found"))
    required = "terraform" in needs
    status = "ok" if found else ("blocker" if required else "skipped")
    return check_item(
        "terraform",
        status,
        required=required,
        summary="Terraform CLI is available." if found else "Terraform is optional and not installed.",
        details={
            "terraform": context.get("terraform", {}),
            "readiness": context.get("readiness", {}),
            "terraform_cli_config": context.get("terraform_cli_config", {}),
            "provider_cache": context.get("provider_cache", {}),
            "forbidden_artifacts": context.get("forbidden_artifacts", []),
        },
        next_actions=[] if found else ["Install Terraform only when the task explicitly needs IaC, import, drift, or long-term management."],
        install_commands=[] if found else TERRAFORM_CHECK_COMMANDS,
    )


def obsutil_config_status(config_path: Path) -> dict[str, Any]:
    """Inspect obsutil config presence without printing credential values."""
    result = {
        "path": str(config_path),
        "exists": config_path.exists(),
        "has_ak": False,
        "has_sk": False,
        "has_security_token": False,
        "read_error": None,
    }
    if not config_path.exists():
        return result
    try:
        lines = config_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        result["read_error"] = str(exc)
        return result
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().lower()
        has_value = bool(value.strip())
        if key in {"ak", "accesskey", "access_key"}:
            result["has_ak"] = result["has_ak"] or has_value
        elif key in {"sk", "secretkey", "secret_key"}:
            result["has_sk"] = result["has_sk"] or has_value
        elif key in {"securitytoken", "security_token", "token"}:
            result["has_security_token"] = result["has_security_token"] or has_value
    return result


def inspect_obsutil(needs: set[str]) -> dict[str, Any]:
    """Inspect optional obsutil readiness."""
    path = shutil.which("obsutil")
    version = run_command([path, "version"], timeout=15) if path else {"found": False}
    config = obsutil_config_status(Path.home() / ".obsutilconfig")
    found = bool(path)
    required = "obsutil" in needs
    status = "ok" if found else ("blocker" if required else "skipped")
    return check_item(
        "obsutil",
        status,
        required=required,
        summary="obsutil is available." if found else "obsutil is optional and not installed.",
        details={"path": path, "version_command": version, "config": config},
        next_actions=[] if found else ["Install obsutil only for OBS bucket/object/static-website workflows that need obsutil."],
        install_commands=[] if found else OBSUTIL_CHECK_COMMANDS,
    )


def inspect_maas(needs: set[str]) -> dict[str, Any]:
    """Inspect optional MaaS API key presence."""
    required = "maas" in needs
    env = env_presence(["MAAS_API_KEY", "MODELARTS_MAAS_API_KEY"])
    has_key = env["MAAS_API_KEY"]["set"] or env["MODELARTS_MAAS_API_KEY"]["set"]
    status = "ok" if has_key else ("blocker" if required else "skipped")
    return check_item(
        "modelarts_maas",
        status,
        required=required,
        summary="A MaaS API key environment variable is set." if has_key else "MaaS API calls are optional and no MaaS API key is set.",
        details={"environment": env},
        next_actions=[] if has_key else ["Set MAAS_API_KEY or MODELARTS_MAAS_API_KEY only when calling Huawei Cloud MaaS APIs."],
    )


def inspect_proxy() -> dict[str, Any]:
    """Inspect proxy environment presence."""
    env = env_presence(["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"])
    any_proxy = any(item["set"] for item in env.values())
    return check_item(
        "proxy",
        "ok" if any_proxy else "skipped",
        required=False,
        summary="Proxy variables are set." if any_proxy else "No proxy variables set; this is fine for direct networks.",
        details={"environment": env},
    )


def summarize(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a compact status summary."""
    counts = {"ok": 0, "warning": 0, "blocker": 0, "skipped": 0}
    for item in checks:
        counts[str(item.get("status"))] = counts.get(str(item.get("status")), 0) + 1
    return {
        **counts,
        "ready": counts.get("blocker", 0) == 0,
        "required_blockers": [
            item["name"] for item in checks if item.get("required") and item.get("status") == "blocker"
        ],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    """Build the check-only environment doctor report."""
    needs = {str(item).lower() for item in getattr(args, "need", [])}
    workdir = Path(getattr(args, "workdir", hcloud_common.ROOT)).resolve()
    checks = [
        inspect_python(),
        inspect_hcloud(),
        inspect_auth(needs),
        inspect_sdk(needs),
        inspect_terraform(needs, workdir),
        inspect_obsutil(needs),
        inspect_maas(needs),
        inspect_proxy(),
    ]
    return {
        "success": True,
        "mode": "check_only",
        "no_changes_made": True,
        "needs": sorted(needs),
        "workdir": str(workdir),
        "summary": summarize(checks),
        "checks": checks,
        "source_references": [
            "reference-projects/huaweicloud-skills-by-huawei/skills/devtools/cli/huawei-cloud-cli-guidance",
            "reference-projects/huaweicloud-skills-by-huawei/skills/devtools/terraform/huawei-cloud-terraform-installer",
            "reference-projects/huaweicloud-skills-by-huawei/skills/storage/obs/huawei-cloud-obs-website-host",
        ],
        "execution_boundary": "This doctor does not install packages, modify credentials, write config, run terraform init/plan/apply, or call Huawei Cloud APIs.",
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--need",
        action="append",
        choices=NEED_CHOICES,
        default=[],
        help="Mark a capability as required for this task. Can be repeated.",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=hcloud_common.ROOT,
        help="Workspace directory to inspect for Terraform runtime artifacts.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    """Run the environment doctor."""
    args = parse_args()
    result = build_report(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
