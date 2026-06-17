#!/usr/bin/env python3
"""Audit closure maturity tiers across huaweicloud-skill planners."""

from __future__ import annotations

import argparse
from typing import Any

import hcloud_common
import hcloud_governance_closure_plan
import hcloud_lifecycle_closure_plan
import hcloud_p2_scenario_closure_plan


ECS_SAMPLE_ASSETS = [
    "scripts/hcloud_context_inspect.py",
    "scripts/hcloud_resource_discovery.py",
    "scripts/hcloud_ecs_create_plan.py",
    "scripts/hcloud_change_plan.py",
    "scripts/hcloud_ecs_wait_job.py",
    "scripts/hcloud_ecs_verify_active.py",
    "references/playbooks/ecs-create-readiness.md",
    "references/playbooks/ecs-ssh-access-readiness.md",
]
METADATA_EVIDENCE_GAP_EXAMPLES = [
    "HSS",
    "SecMaster",
    "CFW",
    "DBSS",
    "KMS",
    "GaussDB",
    "GaussDBforNoSQL",
    "GaussDBforopenGauss",
    "DDS",
    "DDM",
    "DWS",
]


def tier(
    tier_id: str,
    status: str,
    execution_boundary: str,
    services: list[str],
    implemented_assets: list[str],
    closure_outputs: list[str],
    remaining_gaps: list[str],
) -> dict[str, Any]:
    """Build one maturity tier entry."""
    return {
        "id": tier_id,
        "status": status,
        "execution_boundary": execution_boundary,
        "service_or_group_count": len(services),
        "services_or_groups": services,
        "implemented_assets": implemented_assets,
        "closure_outputs": closure_outputs,
        "remaining_gaps": remaining_gaps,
    }


def build_audit() -> dict[str, Any]:
    """Return a planner-only audit of current closure maturity."""
    p0_services = list(hcloud_lifecycle_closure_plan.CLOSURE_SERVICES)
    p1_services = list(hcloud_governance_closure_plan.P1_SERVICES)
    p2_groups = list(hcloud_p2_scenario_closure_plan.GROUP_SERVICES)
    tiers = [
        tier(
            "ecs_end_to_end_sample",
            "sample_reference",
            "guarded_plan_dryrun_submit_with_job_and_resource_readiness_guidance",
            ["ECS"],
            ECS_SAMPLE_ASSETS,
            [
                "dependency discovery",
                "create JSON validation",
                "security gate",
                "dry-run/submit plan",
                "ShowJob polling",
                "ACTIVE verification",
                "SSH/application readiness guidance",
            ],
            [
                "Not every ECS API is automated.",
                "Application readiness still needs task-specific protocol or host-level evidence.",
            ],
        ),
        tier(
            "p0_task_level_planner",
            "implemented_task_level_planner",
            "planner_only_no_live_probe",
            p0_services,
            [
                "scripts/hcloud_lifecycle_closure_plan.py",
                "scripts/hcloud_service_change_plan.py",
                "scripts/hcloud_service_readiness.py",
                "scripts/hcloud_resource_verify.py",
                "scripts/hcloud_obs_readonly.py",
                "scripts/hcloud_lts_readonly.py",
            ],
            [
                "six-stage closure plan",
                "service-specific risk gates",
                "readiness plan",
                "acceptance_evidence_plan",
                "governance/audit follow-up",
            ],
            [
                "Live protocol probes are planned, not executed by the lifecycle planner.",
                "Guest OS checks for EVS and application probes still require task-specific execution.",
                "Some write paths still require dedicated guarded flows before submit.",
            ],
        ),
        tier(
            "p1_governance_planner_only",
            "implemented_governance_planner",
            "planner_only_or_request_spec_only",
            p1_services,
            [
                "scripts/hcloud_governance_closure_plan.py",
                "scripts/hcloud_billing_readonly.py",
                "scripts/hcloud_curated_promotion_audit.py",
            ],
            [
                "inventory/candidate framing",
                "read-only evidence command plans",
                "Billing/BSS request specs without credentials or HTTP",
                "review plan",
                "curated promotion gaps",
            ],
            [
                "Governance mutations remain intentionally disabled.",
                "Billing live queries need a reviewed signed-request or SDK path before execution.",
            ],
        ),
        tier(
            "p2_scenario_planner_only",
            "implemented_scenario_planner",
            "planner_only_no_submit",
            p2_groups,
            [
                "scripts/hcloud_p2_scenario_closure_plan.py",
                "references/playbooks/cce-cluster-readiness.md",
                "references/playbooks/nat-gateway-readiness.md",
                "references/playbooks/dcs-readiness.md",
                "references/playbooks/rfs-stack-readiness.md",
                "references/playbooks/ucs-fleet-readiness.md",
            ],
            [
                "scenario scope",
                "read-only evidence command plan",
                "target-scoped parameter gaps",
                "risk boundary",
                "next closure steps",
            ],
            [
                "P2 groups are not ECS-level end-to-end flows.",
                "Cluster, NAT, cache, stack, fleet, security, key, IAM, and database mutations need dedicated guarded flows.",
            ],
        ),
        tier(
            "metadata_backed_evidence_gap",
            "evidence_gap_until_promoted",
            "discovery_readonly_or_planner_only",
            METADATA_EVIDENCE_GAP_EXAMPLES,
            [
                "references/hcloud-service-catalog.index.json",
                "references/hcloud-service-catalog/",
                "scripts/hcloud_catalog_readonly_smoke.py",
                "scripts/hcloud_curated_promotion_audit.py",
            ],
            [
                "service/operation discovery",
                "explicit-parameter read-only query planning",
                "planner-only mutation classification",
                "promotion gap reporting",
            ],
            [
                "Needs live read-smoke evidence before curated promotion.",
                "Needs playbook, risk profile, target-scoped verifier, and tests before higher maturity claims.",
            ],
        ),
    ]
    return {
        "success": True,
        "mode": "audit",
        "planning_only": True,
        "all_services_ecs_level": False,
        "summary": {
            "tier_count": len(tiers),
            "p0_service_count": len(p0_services),
            "p1_service_count": len(p1_services),
            "p2_group_count": len(p2_groups),
            "metadata_gap_example_count": len(METADATA_EVIDENCE_GAP_EXAMPLES),
            "highest_maturity": "ecs_end_to_end_sample",
            "current_focus": "Strengthen P0 acceptance evidence and keep P1/P2 boundaries explicit.",
        },
        "tiers": tiers,
        "audit_boundary": "This audit reports local planner maturity only; it does not execute hcloud, SDK, or Terraform.",
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    """Build and print the closure maturity audit."""
    args = parse_args()
    result = build_audit()
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
