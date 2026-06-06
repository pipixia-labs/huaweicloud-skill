#!/usr/bin/env python3
"""Build P1 governance closure plans for Huawei Cloud services."""

from __future__ import annotations

import argparse
from types import SimpleNamespace
from typing import Any

import hcloud_billing_readonly
import hcloud_catalog
import hcloud_common
import hcloud_curated_promotion_audit


P1_SERVICES = ("TMS", "CTS", "CBR", "RMS_CONFIG", "BILLING_BSS", "WAF", "DLI", "CODEARTSREPO")
SERVICE_ALIASES = {
    "RMS": "RMS_CONFIG",
    "CONFIG": "RMS_CONFIG",
    "RMS_CONFIG": "RMS_CONFIG",
    "RMS/CONFIG": "RMS_CONFIG",
    "BILLING": "BILLING_BSS",
    "COST": "BILLING_BSS",
    "BSS": "BILLING_BSS",
    "BILLING_BSS": "BILLING_BSS",
    "BILLING/COST/BSS": "BILLING_BSS",
    "CODEARTS_REPO": "CODEARTSREPO",
    "CODEARTSREPO": "CODEARTSREPO",
}

SERVICE_GROUPS = {
    "TMS": ["TMS"],
    "CTS": ["CTS"],
    "CBR": ["CBR"],
    "RMS_CONFIG": ["RMS", "Config"],
    "BILLING_BSS": ["BSS"],
    "WAF": ["WAF"],
    "DLI": ["DLI"],
    "CODEARTSREPO": ["CodeArtsRepo"],
}

SERVICE_TASKS: dict[str, dict[str, Any]] = {
    "TMS": {
        "task": "tag-coverage-and-cost-allocation-governance",
        "tenant_goals": ["上好云", "管好云"],
        "summary": "Plan tag taxonomy, tag coverage, owner/cost-center evidence, and tag-fix review without writing tags.",
        "required_inputs": ["required_tag_keys", "resource_types", "owner_taxonomy"],
        "review_checks": [
            "Confirm the mandatory tag taxonomy such as owner, env, cost-center, app, and expiry.",
            "Map supported resource types before checking tag coverage.",
            "Use target-scoped resource tag readback before proposing tag fixes.",
            "Record tag gaps as review candidates rather than immediate tag mutations.",
        ],
        "reporting_outputs": [
            "Tag key/value taxonomy summary.",
            "Resource tag coverage gaps by service/resource type.",
            "Batch tag remediation plan requiring owner approval.",
        ],
    },
    "CTS": {
        "task": "audit-tracker-and-trace-readiness",
        "tenant_goals": ["管好云"],
        "summary": "Plan audit tracker, trace query, notification, OBS delivery, and sensitive trace handling checks.",
        "required_inputs": ["trace_type", "time_range", "region", "audit_scope"],
        "review_checks": [
            "Confirm tracker status, tracker type, OBS delivery bucket, and encryption posture.",
            "Use bounded trace time ranges and trace types.",
            "Treat operator, source IP, resource ID, and request metadata as sensitive output.",
            "Do not treat empty traces as proof until tracker, region, time range, and trace type are verified.",
        ],
        "reporting_outputs": [
            "Tracker readiness summary.",
            "Bounded trace evidence summary.",
            "Audit gap review items for tracker, notification, and OBS delivery.",
        ],
    },
    "CBR": {
        "task": "backup-posture-and-recovery-governance",
        "tenant_goals": ["用好云", "管好云"],
        "summary": "Plan backup vault, policy, backup checkpoint, and protectable-resource evidence before resilience conclusions.",
        "required_inputs": ["resource_scope", "recovery_objective", "vault_or_policy_id"],
        "review_checks": [
            "Inventory vaults, policies, backup records, and protectable resources.",
            "Check whether critical resources are protected by an active policy.",
            "Separate backup existence from restore readiness.",
            "Keep policy changes, protection changes, and deletes hard-gated.",
        ],
        "reporting_outputs": [
            "Protected/unprotected resource summary.",
            "Backup freshness and policy gap list.",
            "Recovery-readiness review plan.",
        ],
    },
    "RMS_CONFIG": {
        "task": "resource-inventory-and-compliance-governance",
        "tenant_goals": ["管好云"],
        "summary": "Plan resource inventory, policy state, conformance-pack, and aggregator evidence across RMS/Config.",
        "required_inputs": ["domain_id", "provider", "resource_type", "compliance_scope"],
        "review_checks": [
            "Confirm domain/account scope before account-wide inventory or compliance checks.",
            "Collect provider/resource inventory and policy-state evidence separately.",
            "State freshness and scope limits for compliance data.",
            "Keep policy assignment, aggregator, remediation, and conformance-pack mutations hard-gated.",
        ],
        "reporting_outputs": [
            "Resource inventory coverage summary.",
            "Compliance gap summary by policy/provider/resource type.",
            "Aggregator and organization-scope readiness gaps.",
        ],
    },
    "BILLING_BSS": {
        "task": "billing-cost-evidence-planning",
        "tenant_goals": ["管好云"],
        "summary": "Plan official Billing/Cost/BSS request specs and data-sensitivity boundaries without signing or sending requests.",
        "required_inputs": ["bill_cycle", "begin_time", "end_time", "enterprise_project_id"],
        "review_checks": [
            "Confirm account, enterprise project, time range, and permission scope before live billing access.",
            "Use official Billing/Cost APIs or API Explorer; do not infer spend from resource inventory.",
            "Keep raw records narrow because billing data contains account, resource, and spend-sensitive fields.",
            "Record freshness limits before using data for optimization decisions.",
        ],
        "reporting_outputs": [
            "Monthly summary or cost-analysis request spec.",
            "Resource fee/detail request spec.",
            "Cost data freshness and permission boundary summary.",
        ],
    },
    "WAF": {
        "task": "waf-policy-posture-governance",
        "tenant_goals": ["管好云"],
        "summary": "Plan WAF instance, host, certificate, and policy-rule readback before any web security policy change.",
        "required_inputs": ["domain", "policy_id", "enterprise_project_id"],
        "review_checks": [
            "Inventory WAF instances, protected hosts, certificates, and policy rules.",
            "Separate security visibility from policy enforcement changes.",
            "Keep host binding, certificate replacement, rule changes, and bypass controls hard-gated.",
            "Use event/rule evidence before claiming protection posture.",
        ],
        "reporting_outputs": [
            "Protected host and policy posture summary.",
            "Certificate and rule readback gaps.",
            "Policy change review plan.",
        ],
    },
    "DLI": {
        "task": "analytics-sql-governance-readiness",
        "tenant_goals": ["用好云", "管好云"],
        "summary": "Plan DLI auth, catalog, database, queue, and SQL check evidence for analytics readiness.",
        "required_inputs": ["queue_name", "database_name", "sql_check_scope"],
        "review_checks": [
            "Check auth info, catalogs, databases, and elastic resource pools before SQL workload claims.",
            "Use SQL check/read-only metadata before recommending job execution.",
            "Keep queue, permission, and workload changes planner-only until curated flow exists.",
            "Avoid exposing broad table metadata unless scope is approved.",
        ],
        "reporting_outputs": [
            "Catalog/database/queue readiness summary.",
            "Permission and SQL-check gaps.",
            "Analytics workload readiness review plan.",
        ],
    },
    "CODEARTSREPO": {
        "task": "repository-devops-governance-readiness",
        "tenant_goals": ["管好云"],
        "summary": "Plan repository, branch, merge-request, member, and deploy-key evidence for DevOps governance.",
        "required_inputs": ["project_id", "repository_id", "branch"],
        "review_checks": [
            "Inventory repositories, groups, branches, and merge-request scope before DevOps conclusions.",
            "Treat repository metadata, branch names, and merge requests as potentially sensitive.",
            "Keep repository, branch, member, webhook, and deploy-key mutations planner-only until curated flow exists.",
            "Use target-scoped repository readback before recommending automation changes.",
        ],
        "reporting_outputs": [
            "Repository and branch governance summary.",
            "MR/member/deploy-key evidence gaps.",
            "DevOps hygiene review plan.",
        ],
    },
}


def canonical_service(value: str) -> str:
    """Return a canonical P1 governance service key."""
    token = value.upper().replace("-", "_").replace(" ", "")
    return SERVICE_ALIASES.get(token, token)


def parse_params(values: list[str]) -> dict[str, str]:
    """Parse repeated key=value parameters."""
    params: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Expected --param KEY=VALUE, got {item!r}.")
        key, value = item.split("=", 1)
        if not key:
            raise ValueError(f"Expected non-empty key in --param {item!r}.")
        params[key] = value
    return params


def billing_args(operation: str, params: dict[str, str]) -> SimpleNamespace:
    """Return arguments for the Billing/Cost request-spec planner."""
    return SimpleNamespace(
        operation=operation,
        endpoint_base=params.get("endpoint_base", hcloud_billing_readonly.DEFAULT_ENDPOINT_BASE),
        language=params.get("language", "zh_CN"),
        bill_cycle=params.get("bill_cycle"),
        begin_time=params.get("begin_time"),
        end_time=params.get("end_time"),
        time_measure_id=int(params.get("time_measure_id", "1")),
        group_by=params.get("group_by", "CLOUD_SERVICE_TYPE").split(","),
        filter=[],
        cost_type=params.get("cost_type", "ORIGINAL_COST"),
        amount_type=params.get("amount_type", "PAYMENT_AMOUNT"),
        service_type_code=params.get("service_type_code"),
        resource_type=params.get("resource_type"),
        region_code=params.get("region_code"),
        resource_id=params.get("resource_id"),
        enterprise_project_id=params.get("enterprise_project_id"),
        charge_mode=params.get("charge_mode"),
        bill_type=int(params["bill_type"]) if params.get("bill_type") else None,
        method=params.get("method"),
        sub_customer_id=params.get("sub_customer_id"),
        include_zero_record=params.get("include_zero_record"),
        statistic_type=int(params["statistic_type"]) if params.get("statistic_type") else None,
        offset=int(params.get("offset", "0")),
        limit=int(params.get("limit", "10")),
        query=[],
        body_json_file=None,
        body_json_text=None,
    )


def build_billing_specs(params: dict[str, str]) -> list[dict[str, Any]]:
    """Return planner-only Billing/Cost request specs for governance review."""
    specs = []
    for operation in ("monthly-sum", "cost-data", "resource-records"):
        spec = hcloud_billing_readonly.build_request_spec(billing_args(operation, params))
        specs.append(
            {
                "operation": operation,
                "success": bool(spec.get("success")),
                "title": spec.get("title"),
                "request_spec": spec.get("request_spec"),
                "validation": spec.get("validation"),
                "official_docs": spec.get("official_docs"),
            }
        )
    return specs


def load_profiles() -> dict[str, Any]:
    """Load service curation profiles."""
    return hcloud_curated_promotion_audit.load_curation_profiles()


def profile_for(profiles: dict[str, Any], service_name: str) -> dict[str, Any] | None:
    """Return a curation profile for a service."""
    return hcloud_curated_promotion_audit.profile_for_service(profiles, service_name)


def audit_map(services: list[str], min_live_ops: int) -> dict[str, dict[str, Any]]:
    """Return promotion audit entries keyed by normalized service name."""
    if not services:
        return {}
    result = hcloud_curated_promotion_audit.audit(services=services, min_live_ops=min_live_ops)
    return {
        hcloud_catalog.normalize_token(str(item.get("service"))): item
        for item in result.get("candidates", [])
        if isinstance(item, dict)
    }


def profile_summaries(service_key: str, profiles: dict[str, Any]) -> list[dict[str, Any]]:
    """Return compact profile summaries for the underlying services."""
    summaries = []
    for service_name in SERVICE_GROUPS[service_key]:
        profile = profile_for(profiles, service_name)
        summary = hcloud_curated_promotion_audit.profile_summary(profile)
        summaries.append(
            {
                "service": service_name,
                "profile": summary,
                "profile_present": bool(summary),
            }
        )
    return summaries


def promotion_entries(service_key: str, audits: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return promotion audit snippets for the underlying services."""
    entries = []
    for service_name in SERVICE_GROUPS[service_key]:
        entry = audits.get(hcloud_catalog.normalize_token(service_name))
        if not entry:
            continue
        entries.append(
            {
                "service": entry.get("service"),
                "status": entry.get("status"),
                "eligible": entry.get("eligible"),
                "missing": entry.get("missing", []),
                "next_steps": entry.get("next_steps", []),
                "value": entry.get("value", {}),
                "live_read_smoked_operations": entry.get("live_read_smoked_operations", []),
                "readiness_discovery_candidates": entry.get("readiness_discovery_candidates", []),
                "resource_query_candidates": entry.get("resource_query_candidates", []),
            }
        )
    return entries


def profile_operations(profile_entries: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    """Return profile operations for each underlying service."""
    result = []
    for entry in profile_entries:
        profile = entry.get("profile") or {}
        operations = profile.get(field, []) if isinstance(profile, dict) else []
        result.append({"service": entry["service"], "operations": operations})
    return result


def build_service_plan(
    service_key: str,
    params: dict[str, str],
    profiles: dict[str, Any],
    audits: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build one P1 governance closure service plan."""
    task = SERVICE_TASKS[service_key]
    profile_entries = profile_summaries(service_key, profiles)
    promotion = promotion_entries(service_key, audits)
    billing_specs = build_billing_specs(params) if service_key == "BILLING_BSS" else []
    risk_profiles = [
        {
            "service": entry["service"],
            "risk_profile": (entry.get("profile") or {}).get("risk_profile", {}),
        }
        for entry in profile_entries
    ]
    return {
        "service_key": service_key,
        "services": SERVICE_GROUPS[service_key],
        "task": task["task"],
        "tenant_goals": task["tenant_goals"],
        "summary": task["summary"],
        "planning_only": True,
        "execution_supported": False,
        "stages": [
            {
                "id": "governance_scope",
                "description": "Confirm tenant goal, scope, account/region/domain boundary, and required inputs.",
                "required_inputs": task["required_inputs"],
                "provided_params": {key: value for key, value in params.items() if key in task["required_inputs"]},
            },
            {
                "id": "read_only_evidence",
                "description": "Collect or plan read-only discovery and target-scoped evidence before any conclusion.",
                "readiness_operations": profile_operations(profile_entries, "readiness_operations"),
                "resource_query_operations": profile_operations(profile_entries, "resource_query_operations"),
                "billing_request_specs": billing_specs,
            },
            {
                "id": "risk_and_privacy_gate",
                "description": "Keep governance/security/cost data narrow and keep mutations behind hard gates.",
                "risk_profiles": risk_profiles,
                "mutation_boundary": "planner_only_no_submit",
                "sensitive_data_notes": [
                    "Governance data can expose owners, resource IDs, policies, audit traces, repository metadata, or spend.",
                    "Summaries should prefer counts, gaps, and scoped evidence over broad raw dumps.",
                ],
            },
            {
                "id": "review_plan",
                "description": "Convert evidence into reviewable governance gaps rather than immediate mutations.",
                "checks": task["review_checks"],
                "reporting_outputs": task["reporting_outputs"],
            },
            {
                "id": "promotion_readiness",
                "description": "Show what is still needed before curated promotion or guarded write support.",
                "promotion_audit": promotion,
                "profiles": profile_entries,
            },
        ],
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """Build a planner-only P1 governance closure plan."""
    params = parse_params(args.param)
    selected = [canonical_service(service) for service in (args.service or P1_SERVICES)]
    unsupported = [service for service in selected if service not in SERVICE_TASKS]
    if unsupported:
        return {
            "success": False,
            "mode": "plan",
            "planning_only": True,
            "error": "Unsupported P1 governance service.",
            "unsupported_services": unsupported,
            "supported_services": list(P1_SERVICES),
        }

    selected = list(dict.fromkeys(selected))
    underlying_services = [
        service
        for service_key in selected
        for service in SERVICE_GROUPS[service_key]
        if service.upper() != "BSS"
    ]
    profiles = load_profiles()
    audits = audit_map(underlying_services, args.min_live_ops)
    service_plans = [build_service_plan(service_key, params, profiles, audits) for service_key in selected]
    return {
        "success": True,
        "mode": "plan",
        "planning_only": True,
        "scope": "P1 governance closure for tag, audit, backup, compliance, cost, security, analytics, and DevOps readiness.",
        "region": args.region,
        "project_id": args.project_id,
        "profile": args.profile,
        "selected_services": selected,
        "service_count": len(service_plans),
        "services": service_plans,
        "global_boundaries": [
            "P1 governance closure is read-only/planner-only by default.",
            "No tag, tracker, backup, policy, billing, WAF, DLI, or repository mutation is generated by this planner.",
            "Curated promotion requires live read-smoke evidence, target-scoped queries, playbooks, risk profiles, and tests.",
        ],
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", action="append", help="P1 governance service. Defaults to all P1 services.")
    parser.add_argument("--param", action="append", default=[], help="Task parameter as KEY=VALUE. Can be repeated.")
    parser.add_argument("--region", help="Explicit cli-region for generated review context.")
    parser.add_argument("--project-id", help="Optional project_id for generated review context.")
    parser.add_argument("--profile", help="Optional cli-profile for generated review context.")
    parser.add_argument("--min-live-ops", type=int, default=2, help="Minimum live-read-smoked ops used in promotion audit.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    if args.min_live_ops < 1:
        parser.error("--min-live-ops must be greater than 0.")
    return args


def main() -> int:
    """Build the P1 governance closure plan."""
    args = parse_args()
    try:
        result = build_plan(args)
    except ValueError as exc:
        result = {"success": False, "mode": "plan", "planning_only": True, "error": str(exc)}
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
