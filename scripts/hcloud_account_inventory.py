#!/usr/bin/env python3
"""Build or run a read-only account inventory plan across core services."""

from __future__ import annotations

import argparse
from collections import Counter
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


def discovery_args(args: argparse.Namespace, service: str, operation: str) -> SimpleNamespace:
    """Return hcloud_resource_discovery arguments for one inventory target."""
    return SimpleNamespace(
        service=service,
        operation=operation,
        region=args.region,
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


def build_target_plan(args: argparse.Namespace, target: dict[str, str]) -> dict[str, Any]:
    """Build or execute one read-only inventory check."""
    service = target["service"]
    if service == "OBS":
        plan = hcloud_obs_readonly.build_plan(obs_args(args))
    else:
        plan = hcloud_resource_discovery.build_plan(discovery_args(args, service, target["operation"]))
        if plan.get("success") and args.execute:
            plan = hcloud_resource_discovery.execute_plan(plan, args.timeout)
    return {
        **target,
        "success": bool(plan.get("success")),
        "plan": plan,
    }


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a compact inventory summary without embedding raw cloud results."""
    category_counts = Counter(check["category"] for check in checks)
    service_counts = Counter(check["service"] for check in checks)
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
        "categories": dict(sorted(category_counts.items())),
        "services": dict(sorted(service_counts.items())),
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

    checks = [build_target_plan(args, target) for target in targets]
    summary = summarize_checks(checks)
    success = summary["failed_check_count"] == 0 if args.strict else bool(checks)
    return {
        "success": success,
        "mode": "execute" if args.execute else "plan",
        "planning_only": not args.execute,
        "region": args.region,
        "project_id": args.project_id,
        "profile": args.profile,
        "limit": args.limit,
        "summary": summary,
        "checks": checks,
        "next_steps": [
            "Run with --execute only for approved read-only inventory collection.",
            "Save executed JSON output and pass it to hcloud_idle_audit.py for idle-candidate analysis.",
            "Do not delete, release, or downsize resources from inventory data alone; confirm owner, tags, recent metrics, backups, and retention first.",
        ],
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", action="append", default=[], help="Limit inventory to a service. Can be repeated.")
    parser.add_argument("--region", help="Explicit cli-region for generated commands.")
    parser.add_argument("--project-id", help="Optional project_id for generated commands.")
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
