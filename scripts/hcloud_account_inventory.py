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
import hcloud_meta_lookup
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
_USE_ARGS_PROJECT_ID = object()


def selected_targets(services: list[str]) -> list[dict[str, str]]:
    """Return inventory targets filtered by service names when provided."""
    if not services:
        return [dict(target) for target in INVENTORY_TARGETS]
    requested = {service.upper() for service in services}
    return [dict(target) for target in INVENTORY_TARGETS if target["service"] in requested]


def inventory_scope_type(service: str) -> str:
    """Return whether one registered inventory service is regional or global."""
    registry = hcloud_resource_discovery.load_registry()
    service_entry = registry.get("services", {}).get(service.upper(), {})
    return "regional" if service_entry.get("default_region_required", True) else "global"


def describe_inventory_scope(targets: list[dict[str, str]]) -> dict[str, Any]:
    """Describe the exact registered service and operation scope of an inventory."""
    selected_services = sorted({target["service"] for target in targets})
    return {
        "scope_kind": "registered_core_services",
        "complete_claim_scope": "selected_services_and_regions",
        "selected_service_count": len(selected_services),
        "selected_services": selected_services,
        "selected_operation_count": len(targets),
        "selected_operations": [
            {
                "service": target["service"],
                "operation": target["operation"],
                "scope_type": inventory_scope_type(target["service"]),
            }
            for target in targets
        ],
    }


def load_service_region_support(
    service: str,
    *,
    meta_repo: Path | None = None,
) -> dict[str, Any]:
    """Return region support declared by the local KooCLI endpoint metadata.

    Missing or unreadable metadata is reported as unknown so callers continue
    with the query instead of guessing that a service is unavailable.
    """
    repository = meta_repo or Path.home() / ".hcloud" / "metaRepo"
    try:
        template_dir = hcloud_meta_lookup.collect_template_dirs(repository).get(hcloud_meta_lookup.normalize_token(service))
        endpoint_data = hcloud_meta_lookup.load_endpoints(template_dir, None)
    except (OSError, TypeError, ValueError):
        endpoint_data = None

    groups = endpoint_data.get("groups") if isinstance(endpoint_data, dict) else None
    supported_regions = sorted(
        {str(group.get("region")).strip() for group in groups or [] if isinstance(group, dict) and str(group.get("region") or "").strip()}
    )
    if not supported_regions:
        return {
            "service": service.upper(),
            "known": False,
            "source": "hcloud_endpoint_metadata",
            "reason": "endpoint_metadata_unavailable",
            "supported_regions": [],
        }
    return {
        "service": service.upper(),
        "known": True,
        "source": "hcloud_endpoint_metadata",
        "metadata_language": endpoint_data.get("metadata_language"),
        "metadata_update_time": endpoint_data.get("update_time"),
        "supported_regions": supported_regions,
    }


def discovery_args(
    args: argparse.Namespace,
    service: str,
    operation: str,
    region: str | None,
    project_id: str | None,
) -> SimpleNamespace:
    """Return hcloud_resource_discovery arguments for one inventory target."""
    return SimpleNamespace(
        service=service,
        operation=operation,
        region=region,
        project_id=project_id,
        profile=args.profile,
        limit=args.limit,
        catalog_max_operations=1,
        execute=False,
        timeout=args.timeout,
    )


def iam_discovery_args(args: argparse.Namespace, operation: str) -> SimpleNamespace:
    """Return generic discovery arguments for one global IAM context query."""
    return SimpleNamespace(
        service="IAM",
        operation=operation,
        region=None,
        project_id=None,
        profile=args.profile,
        limit=None,
        catalog_max_operations=1,
        execute=False,
        timeout=args.timeout,
    )


def execute_iam_discovery_operation(args: argparse.Namespace, operation: str) -> dict[str, Any]:
    """Execute one metadata-backed IAM discovery operation through safe_exec."""
    plan = hcloud_resource_discovery.build_plan(iam_discovery_args(args, operation))
    if plan.get("success"):
        plan = hcloud_resource_discovery.execute_plan(plan, args.timeout)
    return plan


def _first_successful_payload(plan: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first successful parsed payload from a discovery plan."""
    for item in plan.get("results", []):
        result = item.get("result", {})
        parsed_json = result.get("parsed_json") if isinstance(result, dict) else None
        if result.get("success") and isinstance(parsed_json, dict):
            return parsed_json
    return None


def _discovery_check(operation: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Return bounded evidence for one IAM discovery query."""
    payload = _first_successful_payload(plan)
    return {
        "service": "IAM",
        "operation": operation,
        "success": bool(plan.get("success") and payload is not None),
        "error": None if payload is not None else str(plan.get("error") or "IAM discovery returned no usable JSON payload."),
    }


def discover_region_context(args: argparse.Namespace) -> dict[str, Any]:
    """Discover Huawei Cloud regions and accessible region projects via IAM."""
    region_operation = "KeystoneListRegions"
    project_operation = "KeystoneListAuthProjects"
    region_plan = execute_iam_discovery_operation(args, region_operation)
    project_plan = execute_iam_discovery_operation(args, project_operation)
    checks = [
        _discovery_check(region_operation, region_plan),
        _discovery_check(project_operation, project_plan),
    ]
    region_payload = _first_successful_payload(region_plan)
    project_payload = _first_successful_payload(project_plan)
    if region_payload is None or project_payload is None:
        return {
            "success": False,
            "source": "iam_regions_and_auth_projects",
            "checks": checks,
            "error": "IAM region/project discovery did not return both required payloads.",
        }

    regions = [item for item in region_payload.get("regions", []) if isinstance(item, dict) and str(item.get("id") or "").strip()]
    projects_by_region: dict[str, dict[str, Any]] = {}
    region_ids = {str(region["id"]) for region in regions}
    for project in project_payload.get("projects", []):
        if not isinstance(project, dict):
            continue
        region_id = str(project.get("name") or "").strip()
        project_id = str(project.get("id") or "").strip()
        if (
            not region_id
            or region_id not in region_ids
            or not project_id
            or project.get("enabled") is False
            or project.get("is_domain") is True
        ):
            continue
        current = projects_by_region.get(region_id)
        is_system_project = project.get("parent_id") == project.get("domain_id")
        current_is_system = bool(current and current.get("parent_id") == current.get("domain_id"))
        if current is None or (is_system_project and not current_is_system):
            projects_by_region[region_id] = project

    region_scopes = []
    skipped_regions = []
    for region in regions:
        region_id = str(region["id"])
        locales = region.get("locales") if isinstance(region.get("locales"), dict) else {}
        region_name = str(locales.get("zh-cn") or locales.get("en-us") or region_id)
        region_type = str(region.get("type") or "unknown")
        project = projects_by_region.get(region_id)
        if project is None:
            skipped_regions.append(
                {
                    "region": region_id,
                    "region_type": region_type,
                    "region_name": region_name,
                    "reason": "no_accessible_project",
                }
            )
            continue
        region_scopes.append(
            {
                "region": region_id,
                "project_id": str(project["id"]),
                "region_type": region_type,
                "region_name": region_name,
            }
        )

    return {
        "success": True,
        "source": "iam_regions_and_auth_projects",
        "catalog_region_count": len(regions),
        "accessible_project_count": len(region_scopes),
        "region_scopes": region_scopes,
        "skipped_regions": skipped_regions,
        "checks": checks,
    }


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


def scope_for(
    args: argparse.Namespace,
    region: str | None,
    project_id: str | None,
) -> dict[str, str | None]:
    """Return the read-only inventory scope for one check."""
    return {
        "region": region,
        "project_id": project_id,
        "profile": args.profile,
        "enterprise_project_id": getattr(args, "enterprise_project_id", None),
    }


def operation_supports_enterprise_project(service: str, operation: str) -> bool:
    """Return whether the local operation metadata supports enterprise_project_id."""
    names = {name.lower().replace("-", "_") for name in hcloud_resource_discovery.operation_param_names(service, operation)}
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
    project_id_override: str | None | object = _USE_ARGS_PROJECT_ID,
) -> dict[str, Any]:
    """Build or execute one read-only inventory check for one region scope."""
    service = target["service"]
    project_id = args.project_id if project_id_override is _USE_ARGS_PROJECT_ID else project_id_override
    if service == "OBS":
        plan = hcloud_obs_readonly.build_plan(obs_args(args))
    else:
        plan = hcloud_resource_discovery.build_plan(
            discovery_args(
                args,
                service,
                target["operation"],
                region,
                project_id,
            )
        )
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
            "status": "not_applicable_to_obs_adapter" if getattr(args, "enterprise_project_id", None) else "not_requested",
        }
    return {
        **target,
        "scope_type": inventory_scope_type(service),
        "scope": scope_for(args, region, project_id),
        "enterprise_project_scope": enterprise_project_scope,
        "success": bool(plan.get("success")),
        "plan": plan,
    }


def _compact_text(value: Any, *, limit: int = 1000) -> str | None:
    """Return one bounded single-line diagnostic string."""
    if value in (None, ""):
        return None
    compact = " ".join(str(value).split())
    return compact[:limit] or None


def _failed_check_summary(check: dict[str, Any]) -> dict[str, Any]:
    """Return structured, bounded failure context for one inventory check."""
    plan = check.get("plan", {})
    failed_result = None
    for item in plan.get("results", []):
        result = item.get("result", {}) if isinstance(item, dict) else {}
        if isinstance(result, dict) and not result.get("success"):
            failed_result = result
            break
    failed_result = failed_result or {}
    details = failed_result.get("error_details", {})
    if not isinstance(details, dict):
        details = {}
    parsed_json = failed_result.get("parsed_json")
    if not isinstance(parsed_json, dict):
        parsed_json = {}
    return {
        "service": check["service"],
        "operation": check["operation"],
        "region": (check.get("scope") or {}).get("region"),
        "category": details.get("category") or "unknown",
        "error_code": details.get("cloud_error_code") or details.get("error_type") or failed_result.get("error_type"),
        "message": _compact_text(
            details.get("cloud_error_message")
            or parsed_json.get("error_msg")
            or failed_result.get("error")
            or failed_result.get("stdout")
            or failed_result.get("stderr")
            or plan.get("error")
        ),
    }


def summarize_checks(
    checks: list[dict[str, Any]],
    skipped_checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a compact inventory summary without embedding raw cloud results."""
    skipped_checks = skipped_checks or []
    category_counts = Counter(check["category"] for check in checks)
    service_counts = Counter(check["service"] for check in checks)
    region_counts = Counter((check.get("scope") or {}).get("region") or "default" for check in checks)
    eps_counts = Counter((check.get("scope") or {}).get("enterprise_project_id") or "all_or_unknown" for check in checks)
    command_count = 0
    failed_checks = []
    succeeded_check_count = 0
    for check in checks:
        plan = check.get("plan", {})
        if "command" in plan:
            command_count += 1
        command_count += len(plan.get("commands", []))
        if not check.get("success"):
            failed_checks.append(_failed_check_summary(check))
        else:
            succeeded_check_count += 1
    failed_check_count = len(failed_checks)
    skipped_check_count = len(skipped_checks)
    completeness_affecting_skipped_check_count = sum(1 for check in skipped_checks if check.get("affects_completeness", True))
    non_applicable_skipped_check_count = skipped_check_count - completeness_affecting_skipped_check_count
    return {
        "check_count": len(checks),
        "attempted_check_count": len(checks),
        "succeeded_check_count": succeeded_check_count,
        "command_count": command_count,
        "service_count": len(service_counts),
        "region_count": len(region_counts),
        "categories": dict(sorted(category_counts.items())),
        "services": dict(sorted(service_counts.items())),
        "regions": dict(sorted(region_counts.items())),
        "enterprise_projects": dict(sorted(eps_counts.items())),
        "failed_check_count": failed_check_count,
        "failed_checks": failed_checks,
        "skipped_check_count": skipped_check_count,
        "completeness_affecting_skipped_check_count": completeness_affecting_skipped_check_count,
        "non_applicable_skipped_check_count": non_applicable_skipped_check_count,
        "skipped_checks": skipped_checks,
        "complete": bool(checks or skipped_checks) and failed_check_count == 0 and completeness_affecting_skipped_check_count == 0,
    }


def inventory_outcome_status(
    *,
    check_count: int,
    failed_check_count: int,
    skipped_check_count: int = 0,
    non_applicable_skipped_check_count: int = 0,
) -> str:
    """Return the declared aggregate outcome for an inventory result."""
    if check_count < 1:
        return "succeeded" if non_applicable_skipped_check_count > 0 and skipped_check_count == 0 else "failed"
    if failed_check_count >= check_count:
        return "failed"
    if failed_check_count or skipped_check_count:
        return "partially_succeeded"
    return "succeeded"


def _skipped_checks_for_regions(
    skipped_regions: list[dict[str, Any]],
    regional_targets: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Expand inaccessible regions into explicit, non-attempted coverage gaps."""
    return [
        {
            "service": target["service"],
            "operation": target["operation"],
            "region": region["region"],
            "reason": region["reason"],
            "status": "skipped",
            "affects_completeness": True,
            "evidence_source": "iam_regions_and_auth_projects",
        }
        for region in skipped_regions
        for target in regional_targets
    ]


def _unsupported_region_skip(
    target: dict[str, str],
    region: str | None,
    support: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a non-applicable skip when endpoint metadata excludes a region."""
    if region is None or not support.get("known"):
        return None
    if region in support.get("supported_regions", []):
        return None
    return {
        "service": target["service"],
        "operation": target["operation"],
        "region": region,
        "reason": "service_region_not_supported",
        "status": "skipped",
        "affects_completeness": False,
        "evidence_source": support["source"],
        "metadata_update_time": support.get("metadata_update_time"),
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """Build or run a read-only account inventory plan."""
    targets = selected_targets(args.service)
    if not targets:
        result = {
            "success": False,
            "mode": "execute" if args.execute else "plan",
            "error": "No inventory targets match the requested service filters.",
            "available_services": sorted({target["service"] for target in INVENTORY_TARGETS}),
        }
        result["outcome_status" if args.execute else "planning_status"] = "failed"
        return result

    requested_regions = normalized_regions(args)
    inventory_scope = describe_inventory_scope(targets)
    explicit_regions = [region for region in requested_regions if region is not None]
    regional_targets = [target for target in targets if inventory_scope_type(target["service"]) == "regional"]
    global_targets = [target for target in targets if inventory_scope_type(target["service"]) == "global"]
    region_support = {
        service: load_service_region_support(service) for service in sorted({target["service"] for target in regional_targets})
    }
    region_discovery = None
    skipped_checks: list[dict[str, Any]] = []

    if explicit_regions:
        region_source = "explicit"
        region_scopes = [{"region": region, "project_id": args.project_id} for region in explicit_regions]
    elif args.execute and regional_targets:
        region_discovery = discover_region_context(args)
        if not region_discovery.get("success"):
            return {
                "success": False,
                "mode": "execute",
                "planning_only": False,
                "region": None,
                "regions": [],
                "region_source": "iam_regions_and_auth_projects",
                "region_discovery": region_discovery,
                "inventory_scope": inventory_scope,
                "service_region_support": region_support,
                "summary": {
                    "check_count": 0,
                    "attempted_check_count": 0,
                    "succeeded_check_count": 0,
                    "failed_check_count": 0,
                    "failed_checks": [],
                    "skipped_check_count": 0,
                    "completeness_affecting_skipped_check_count": 0,
                    "non_applicable_skipped_check_count": 0,
                    "skipped_checks": [],
                    "complete": False,
                },
                "checks": [],
                "outcome_status": "failed",
                "error": region_discovery.get("error") or "IAM region/project discovery failed.",
            }
        region_source = str(region_discovery["source"])
        region_scopes = list(region_discovery.get("region_scopes", []))
        skipped_checks = _skipped_checks_for_regions(
            list(region_discovery.get("skipped_regions", [])),
            regional_targets,
        )
    else:
        region_source = "profile_default"
        region_scopes = [{"region": None, "project_id": args.project_id}]

    checks = []
    for scope in region_scopes:
        region = str(scope["region"]) if scope.get("region") is not None else None
        for target in regional_targets:
            unsupported_skip = _unsupported_region_skip(
                target,
                region,
                region_support[target["service"]],
            )
            if unsupported_skip is not None:
                skipped_checks.append(unsupported_skip)
                continue
            checks.append(
                build_target_plan_for_region(
                    args,
                    target,
                    region,
                    scope.get("project_id"),
                )
            )
    checks.extend(
        build_target_plan_for_region(
            args,
            target,
            None,
            None,
        )
        for target in global_targets
    )
    summary = summarize_checks(checks, skipped_checks)
    outcome_status = inventory_outcome_status(
        check_count=summary["check_count"],
        failed_check_count=summary["failed_check_count"],
        skipped_check_count=summary["completeness_affecting_skipped_check_count"],
        non_applicable_skipped_check_count=summary["non_applicable_skipped_check_count"],
    )
    has_covered_scope = bool(checks or summary["non_applicable_skipped_check_count"])
    success = outcome_status == "succeeded" if args.strict else has_covered_scope
    result = {
        "success": success,
        "mode": "execute" if args.execute else "plan",
        "planning_only": not args.execute,
        "region": region_scopes[0].get("region") if len(region_scopes) == 1 else None,
        "regions": [scope.get("region") for scope in region_scopes],
        "region_source": region_source,
        "project_id": args.project_id,
        "profile": args.profile,
        "enterprise_project_id": getattr(args, "enterprise_project_id", None),
        "limit": args.limit,
        "inventory_scope": inventory_scope,
        "service_region_support": region_support,
        "summary": summary,
        "skipped_checks": skipped_checks,
        "checks": checks,
        "next_steps": [
            "Run with --execute only for approved read-only inventory collection.",
            "Save executed JSON output and pass it to hcloud_idle_audit.py for idle-candidate analysis.",
            "For multi-region reviews, keep partial failures visible and rerun only the failed region/service checks after fixing permissions or service enablement.",
            "Do not delete, release, or downsize resources from inventory data alone; confirm owner, tags, recent metrics, backups, and retention first.",
        ],
    }
    if region_discovery is not None:
        result["region_discovery"] = region_discovery
    result["outcome_status" if args.execute else "planning_status"] = outcome_status
    return result


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
