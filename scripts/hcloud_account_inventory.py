#!/usr/bin/env python3
"""Build or run a read-only account inventory plan across core services."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import hcloud_common
import hcloud_obs_readonly
import hcloud_resource_discovery


INVENTORY_TARGETS = (
    {
        "service": "ECS",
        "operation": "ListCloudServers",
        "category": "compute",
        "purpose": "Inventory ECS instances and status distribution.",
    },
    {
        "service": "VPC",
        "operation": "ListVpcs",
        "category": "network",
        "purpose": "Inventory VPC boundaries.",
    },
    {
        "service": "VPC",
        "operation": "ListSubnets",
        "category": "network",
        "purpose": "Inventory subnet and CIDR layout.",
    },
    {
        "service": "VPC",
        "operation": "ListSecurityGroups",
        "category": "security",
        "purpose": "Inventory security group surfaces before changes.",
    },
    {
        "service": "EIP",
        "operation": "ListPublicips",
        "category": "network",
        "purpose": "Inventory public IPs, bindings, and idle EIP candidates.",
    },
    {
        "service": "ELB",
        "operation": "ListLoadbalancers",
        "category": "traffic",
        "purpose": "Inventory load balancers and operating status.",
    },
    {
        "service": "EVS",
        "operation": "ListVolumes",
        "category": "storage",
        "purpose": "Inventory disks and unattached EVS candidates.",
    },
    {
        "service": "NAT",
        "operation": "ListNatGateways",
        "category": "network",
        "purpose": "Inventory NAT gateways before rule-level checks.",
    },
    {
        "service": "RDS",
        "operation": "ListInstances",
        "category": "database",
        "purpose": "Inventory database instances and lifecycle status.",
    },
    {
        "service": "CCE",
        "operation": "ListClusters",
        "category": "container",
        "purpose": "Inventory Kubernetes clusters.",
    },
    {
        "service": "CDN",
        "operation": "ListDomains",
        "category": "edge",
        "purpose": "Inventory CDN domains and online status.",
    },
    {
        "service": "DNS",
        "operation": "ListPublicZones",
        "category": "network",
        "purpose": "Inventory public DNS zones.",
    },
    {
        "service": "SCM",
        "operation": "ListCertificates",
        "category": "security",
        "purpose": "Inventory SSL certificates and expiration status.",
    },
    {
        "service": "OBS",
        "operation": "ListBuckets",
        "category": "storage",
        "purpose": "Inventory OBS buckets through the obsutil adapter.",
    },
)


def selected_targets(services: list[str]) -> list[dict[str, str]]:
    """Return inventory targets filtered by service names when provided."""
    if not services:
        return [dict(target) for target in INVENTORY_TARGETS]
    requested = {service.upper() for service in services}
    return [dict(target) for target in INVENTORY_TARGETS if target["service"] in requested]


def discovery_args(args: argparse.Namespace, service: str, operation: str, region: str | None) -> SimpleNamespace:
    """Return hcloud_resource_discovery arguments for one inventory target."""
    return SimpleNamespace(
        service=service,
        operation=operation,
        region=region,
        project_id=args.project_id,
        profile=args.profile,
        limit=args.limit,
        catalog_max_operations=1,
        execute=False,
        timeout=args.timeout,
    )


def obs_args(args: argparse.Namespace) -> SimpleNamespace:
    """Return hcloud_obs_readonly arguments for the inventory OBS target."""
    return SimpleNamespace(
        operation="ListBuckets",
        bucket=None,
        endpoint=args.obs_endpoint,
        config=args.obs_config,
        payer=args.obs_payer,
        limit=args.limit,
        arg=[],
        execute=args.execute,
        timeout=args.timeout,
    )


def read_region_file(path: str | None) -> list[str]:
    """Return region names from a newline-delimited or JSON list file."""
    if not path:
        return []
    raw_text = Path(path).expanduser().read_text(encoding="utf-8")
    stripped = raw_text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        data = json.loads(stripped)
        return [str(item).strip() for item in data if str(item).strip()]
    return [line.strip() for line in raw_text.splitlines() if line.strip() and not line.strip().startswith("#")]


def normalized_regions(args: argparse.Namespace) -> list[str | None]:
    """Return requested regions while preserving a single default scope when none are provided."""
    raw_regions = getattr(args, "region", None)
    regions: list[str] = []
    if isinstance(raw_regions, str):
        regions.extend([raw_regions])
    elif isinstance(raw_regions, list):
        regions.extend(str(region).strip() for region in raw_regions if str(region).strip())
    regions.extend(read_region_file(getattr(args, "region_file", None)))

    deduped: list[str] = []
    seen: set[str] = set()
    for region in regions:
        if region in seen:
            continue
        deduped.append(region)
        seen.add(region)
    return deduped or [None]


def scope_for(args: argparse.Namespace, region: str | None) -> dict[str, str | None]:
    """Return the read-only inventory scope for one check."""
    return {
        "region": region,
        "project_id": args.project_id,
        "profile": args.profile,
        "enterprise_project_id": getattr(args, "enterprise_project_id", None),
    }


def operation_supports_enterprise_project(service: str, operation: str) -> bool:
    """Return whether the local operation metadata supports enterprise_project_id."""
    names = {
        name.lower().replace("-", "_")
        for name in hcloud_resource_discovery.operation_param_names(service, operation)
    }
    return "enterprise_project_id" in names or "enterpriseprojectid" in names


def apply_enterprise_project_scope(
    plan: dict[str, Any],
    service: str,
    operation: str,
    enterprise_project_id: str | None,
) -> dict[str, Any]:
    """Append enterprise_project_id to supported command plans and report handling."""
    if not enterprise_project_id:
        return {"requested": False, "status": "not_requested"}

    supported = operation_supports_enterprise_project(service, operation)
    handling = {
        "requested": True,
        "enterprise_project_id": enterprise_project_id,
        "status": "passed_to_command" if supported else "not_supported_by_operation",
    }
    if not supported:
        return handling

    arg = f"--arg=--enterprise_project_id={enterprise_project_id}"
    for command_item in plan.get("commands", []):
        command = command_item.get("command")
        if isinstance(command, list) and arg not in command:
            command.append(arg)
    command = plan.get("command")
    if isinstance(command, list) and arg not in command:
        command.append(arg)
    return handling


def build_target_plan(args: argparse.Namespace, target: dict[str, str]) -> dict[str, Any]:
    """Build or execute one read-only inventory check."""
    return build_target_plan_for_region(args, target, normalized_regions(args)[0])


def build_target_plan_for_region(
    args: argparse.Namespace,
    target: dict[str, str],
    region: str | None,
) -> dict[str, Any]:
    """Build or execute one read-only inventory check for one region scope."""
    service = target["service"]
    if service == "OBS":
        plan = hcloud_obs_readonly.build_plan(obs_args(args))
    else:
        plan = hcloud_resource_discovery.build_plan(discovery_args(args, service, target["operation"], region))
        enterprise_project_scope = apply_enterprise_project_scope(
            plan,
            service,
            target["operation"],
            getattr(args, "enterprise_project_id", None),
        )
        if plan.get("success") and args.execute:
            plan = hcloud_resource_discovery.execute_plan(plan, args.timeout)
    if service == "OBS":
        enterprise_project_scope = {
            "requested": bool(getattr(args, "enterprise_project_id", None)),
            "enterprise_project_id": getattr(args, "enterprise_project_id", None),
            "status": "not_applicable_to_obs_adapter"
            if getattr(args, "enterprise_project_id", None)
            else "not_requested",
        }
    return {
        **target,
        "scope": scope_for(args, region),
        "enterprise_project_scope": enterprise_project_scope,
        "success": bool(plan.get("success")),
        "plan": plan,
    }


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a compact inventory summary without embedding raw cloud results."""
    category_counts = Counter(check["category"] for check in checks)
    service_counts = Counter(check["service"] for check in checks)
    region_counts = Counter((check.get("scope") or {}).get("region") or "default" for check in checks)
    eps_counts = Counter(
        (check.get("scope") or {}).get("enterprise_project_id") or "all_or_unknown"
        for check in checks
    )
    command_count = 0
    failed_checks = []
    for check in checks:
        plan = check.get("plan", {})
        if "command" in plan:
            command_count += 1
        command_count += len(plan.get("commands", []))
        if not check.get("success"):
            failed_checks.append({"service": check["service"], "operation": check["operation"]})
    return {
        "check_count": len(checks),
        "command_count": command_count,
        "service_count": len(service_counts),
        "region_count": len(region_counts),
        "categories": dict(sorted(category_counts.items())),
        "services": dict(sorted(service_counts.items())),
        "regions": dict(sorted(region_counts.items())),
        "enterprise_projects": dict(sorted(eps_counts.items())),
        "failed_check_count": len(failed_checks),
        "failed_checks": failed_checks,
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """Build or run a read-only account inventory plan."""
    targets = selected_targets(args.service)
    if not targets:
        return {
            "success": False,
            "mode": "execute" if args.execute else "plan",
            "error": "No inventory targets match the requested service filters.",
            "available_services": sorted({target["service"] for target in INVENTORY_TARGETS}),
        }

    regions = normalized_regions(args)
    checks = [
        build_target_plan_for_region(args, target, region)
        for region in regions
        for target in targets
    ]
    summary = summarize_checks(checks)
    success = summary["failed_check_count"] == 0 if args.strict else bool(checks)
    return {
        "success": success,
        "mode": "execute" if args.execute else "plan",
        "planning_only": not args.execute,
        "region": regions[0] if len(regions) == 1 else None,
        "regions": regions,
        "project_id": args.project_id,
        "profile": args.profile,
        "enterprise_project_id": getattr(args, "enterprise_project_id", None),
        "limit": args.limit,
        "summary": summary,
        "checks": checks,
        "next_steps": [
            "Run with --execute only for approved read-only inventory collection.",
            "Save executed JSON output and pass it to hcloud_idle_audit.py for idle-candidate analysis.",
            "For multi-region reviews, keep partial failures visible and rerun only the failed region/service checks after fixing permissions or service enablement.",
            "Do not delete, release, or downsize resources from inventory data alone; confirm owner, tags, recent metrics, backups, and retention first.",
        ],
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", action="append", default=[], help="Limit inventory to a service. Can be repeated.")
    parser.add_argument("--region", action="append", default=[], help="Explicit cli-region for generated commands. Can be repeated.")
    parser.add_argument("--region-file", help="Optional newline-delimited or JSON-list file of regions.")
    parser.add_argument("--project-id", help="Optional project_id for generated commands.")
    parser.add_argument("--enterprise-project-id", help="Optional enterprise_project_id scope for operations that support it.")
    parser.add_argument("--profile", help="Optional cli-profile for generated commands.")
    parser.add_argument("--limit", type=int, default=50, help="Optional limit for list operations that support it.")
    parser.add_argument("--obs-endpoint", help="Optional OBS endpoint passed to the obsutil adapter.")
    parser.add_argument("--obs-config", help="Optional obsutil config path.")
    parser.add_argument("--obs-payer", help="Optional OBS request payer.")
    parser.add_argument("--execute", action="store_true", help="Execute approved read-only inventory commands.")
    parser.add_argument("--strict", action="store_true", help="Return failure when any inventory check fails.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per executed command.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be greater than 0.")
    if args.timeout < 1:
        parser.error("--timeout must be greater than 0.")
    return args


def main() -> int:
    """Build or run the read-only account inventory plan."""
    args = parse_args()
    result = build_plan(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
