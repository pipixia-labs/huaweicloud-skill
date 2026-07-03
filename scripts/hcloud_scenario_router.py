#!/usr/bin/env python3
"""Route natural-language Huawei Cloud goals to local hcloud-first guidance."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import hcloud_common


ROUTER_PATH = hcloud_common.REFERENCES_DIR / "scenario-router.json"
SERVICE_ALIAS_PATH = hcloud_common.REFERENCES_DIR / "service-aliases.json"

TERRAFORM_ROUTE = {
    "context_inspect": "scripts/hcloud_terraform_context_inspect.py",
    "router": "scripts/hcloud_terraform_router.py",
    "workflow": "references/terraform-workflow.md",
    "asset_index": "references/terraform/README.md",
    "boundary": "Use only when the user explicitly wants IaC, repeatable infrastructure, import, drift review, or long-term management.",
}
P0_CLOSURE_SERVICES = {"VPC", "EIP", "EVS", "ELB", "RDS", "OBS", "DNS", "SCM", "CDN", "CES", "LTS"}
P0_ACCEPTANCE_FOLLOWUPS = [
    {
        "step": "closure_plan",
        "tool": "scripts/hcloud_closure_plan.py",
        "purpose": "Build the selected lifecycle/governance/scenario closure plan; use --tier lifecycle for P0.",
    },
    {
        "step": "acceptance_closure",
        "tool": "scripts/hcloud_acceptance_closure.py",
        "purpose": "Use plan/run/evaluate subcommands to collect and judge acceptance evidence.",
    },
]


def normalize_token(value: str) -> str:
    """Return a lowercase alphanumeric/CJK-friendly token."""
    return re.sub(r"[\s_\-./:]+", "", value.lower())


def load_router(path: Path = ROUTER_PATH) -> dict[str, Any]:
    """Load scenario router JSON."""
    if not path.exists():
        return {"schema_version": 1, "scenarios": []}
    return hcloud_common.load_json(path)


def load_service_aliases(path: Path = SERVICE_ALIAS_PATH) -> dict[str, str]:
    """Load Chinese-English service aliases for query expansion."""
    if not path.exists():
        return {}
    data = hcloud_common.load_json(path)
    aliases = data.get("aliases", {})
    if not isinstance(aliases, dict):
        return {}
    return {str(alias): str(service).upper() for alias, service in aliases.items()}


def recommended_followups(scenario: dict[str, Any]) -> list[dict[str, str]]:
    """Return standard local follow-up steps for a matched scenario."""
    if bool(scenario.get("skip_standard_followups", False)):
        return []
    services = {str(service).upper() for service in scenario.get("services", [])}
    if services & P0_CLOSURE_SERVICES:
        return [dict(item) for item in P0_ACCEPTANCE_FOLLOWUPS]
    return []


def score_scenario(
    scenario: dict[str, Any],
    query: str,
    category: str | None = None,
    service: str | None = None,
    service_aliases: dict[str, str] | None = None,
) -> tuple[int, list[str]]:
    """Return match score and reasons for one scenario."""
    query_token = normalize_token(query)
    query_lower = query.lower()
    scenario_services = {str(item).upper() for item in scenario.get("services", [])}
    score = 0
    reasons: list[str] = []

    if category and normalize_token(str(scenario.get("category") or "")) == normalize_token(category):
        score += 6
        reasons.append("category match +6")

    if service:
        service_token = normalize_token(service)
        services = [normalize_token(str(item)) for item in scenario.get("services", [])]
        if service_token in services:
            score += 8
            reasons.append("service match +8")

    for alias, mapped_service in (service_aliases or {}).items():
        alias_text = str(alias)
        if mapped_service not in scenario_services:
            continue
        if alias_text.lower() in query_lower or normalize_token(alias_text) in query_token:
            score += 8
            reasons.append(f"alias:{alias_text}->{mapped_service} +8")

    name = str(scenario.get("name") or "")
    if normalize_token(name) and normalize_token(name) in query_token:
        score += 10
        reasons.append("name match +10")

    for trigger in scenario.get("triggers", []):
        trigger_text = str(trigger)
        if trigger_text.lower() in query_lower or normalize_token(trigger_text) in query_token:
            score += 8
            reasons.append(f"trigger:{trigger_text} +8")

    description = str(scenario.get("description") or "")
    for word in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", query):
        if len(word) < 2:
            continue
        if word.lower() in description.lower():
            score += 2
            reasons.append(f"description:{word} +2")

    return score, reasons


def route(query: str, category: str | None = None, service: str | None = None, limit: int = 5, router_path: Path = ROUTER_PATH) -> dict[str, Any]:
    """Route a user goal to local scenario entries."""
    router = load_router(router_path)
    service_aliases = load_service_aliases()
    matches = []
    for scenario in router.get("scenarios", []):
        if not isinstance(scenario, dict):
            continue
        score, reasons = score_scenario(
            scenario,
            query,
            category=category,
            service=service,
            service_aliases=service_aliases,
        )
        if score <= 0:
            continue
        matches.append(
            {
                "id": scenario.get("id"),
                "name": scenario.get("name"),
                "category": scenario.get("category"),
                "score": score,
                "reasons": reasons[:8],
                "services": scenario.get("services", []),
                "primary_playbooks": scenario.get("primary_playbooks", []),
                "guides": scenario.get("guides", []),
                "planners": scenario.get("planners", []),
                "recommended_followups": recommended_followups(scenario),
                "sdk_supplements": scenario.get("sdk_supplements", []),
                "terraform_candidate": scenario.get("terraform_candidate", False),
                "terraform_route": TERRAFORM_ROUTE if scenario.get("terraform_candidate", False) else None,
            }
        )
    matches.sort(key=lambda item: (-int(item["score"]), str(item["id"])))
    return {
        "success": bool(matches),
        "query": query,
        "category": category,
        "service": service,
        "match_count": len(matches),
        "matches": matches[:limit],
        "routing_boundary": "Routes to local hcloud-first playbooks/planners; does not install or execute external skills.",
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Natural-language cloud goal.")
    parser.add_argument("--category", help="Optional scenario category filter hint.")
    parser.add_argument("--service", help="Optional service hint such as ECS or VPC.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum matches to return.")
    parser.add_argument("--router", type=Path, default=ROUTER_PATH, help="Path to scenario-router.json.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be greater than 0.")
    return args


def main() -> int:
    """Route a scenario query."""
    args = parse_args()
    result = route(args.query, category=args.category, service=args.service, limit=args.limit, router_path=args.router)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
