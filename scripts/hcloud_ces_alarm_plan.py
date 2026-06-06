#!/usr/bin/env python3
"""Build a planner-only CES alarm readiness and rule plan."""

from __future__ import annotations

import argparse
from types import SimpleNamespace
from typing import Any

import hcloud_common
import hcloud_resource_discovery


def discovery_args(args: argparse.Namespace, operation: str) -> SimpleNamespace:
    """Return read-only CES discovery arguments."""
    return SimpleNamespace(
        service="CES",
        operation=operation,
        region=args.region,
        project_id=args.project_id,
        profile=args.profile,
        limit=args.limit,
        catalog_max_operations=1,
        execute=args.execute,
        timeout=args.timeout,
    )


def build_readonly_plan(args: argparse.Namespace, operation: str) -> dict[str, Any]:
    """Build or execute a read-only CES discovery plan."""
    plan = hcloud_resource_discovery.build_plan(discovery_args(args, operation))
    if plan.get("success") and args.execute:
        plan = hcloud_resource_discovery.execute_plan(plan, args.timeout)
    return plan


def alarm_rule_spec(args: argparse.Namespace) -> dict[str, Any]:
    """Return a non-executable CES alarm rule draft."""
    return {
        "alarm_name": args.alarm_name,
        "namespace": args.namespace,
        "metric_name": args.metric_name,
        "dimensions": args.dimension,
        "comparison_operator": args.comparison_operator,
        "threshold": args.threshold,
        "period": args.period,
        "evaluation_periods": args.evaluation_periods,
        "statistic": args.statistic,
        "notification_enabled": args.notification_enabled,
        "planner_only": True,
        "submit_command": None,
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """Build a CES alarm readiness and planner-only rule plan."""
    metric_plan = build_readonly_plan(args, "ListMetrics")
    alarm_plan = build_readonly_plan(args, "ListAlarmRules")
    missing = [
        name
        for name in ("alarm_name", "namespace", "metric_name", "threshold")
        if getattr(args, name) in (None, "")
    ]
    rule_spec = alarm_rule_spec(args) if not missing else None
    return {
        "success": bool(metric_plan.get("success")) and bool(alarm_plan.get("success")),
        "mode": "execute" if args.execute else "plan",
        "planning_only": not args.execute,
        "service": "CES",
        "metric_discovery_plan": metric_plan,
        "existing_alarm_rules_plan": alarm_plan,
        "alarm_rule_planner": {
            "success": not missing,
            "missing_fields": missing,
            "rule_spec": rule_spec,
            "executable": False,
            "submit_command": None,
            "risk": {
                "level": "medium",
                "reason": "Alarm rule changes can affect notification noise and incident handling; this planner never submits changes.",
            },
        },
        "next_steps": [
            "Discover metric namespace, metric_name, and dimensions before finalizing any alarm rule.",
            "Review existing alarm rules to avoid duplicates and notification noise.",
            "Use a separate reviewed change planner before creating or modifying CES alarm rules.",
        ],
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", help="Explicit cli-region for generated commands.")
    parser.add_argument("--project-id", help="Optional project_id for generated commands.")
    parser.add_argument("--profile", help="Optional cli-profile for generated commands.")
    parser.add_argument("--limit", type=int, default=50, help="Read-only discovery limit when supported.")
    parser.add_argument("--alarm-name", help="Draft alarm rule name.")
    parser.add_argument("--namespace", help="Draft CES metric namespace.")
    parser.add_argument("--metric-name", help="Draft CES metric name.")
    parser.add_argument("--dimension", action="append", default=[], help="Draft metric dimension as name=value. Can be repeated.")
    parser.add_argument("--comparison-operator", default=">", help="Draft comparison operator.")
    parser.add_argument("--threshold", type=float, help="Draft alarm threshold.")
    parser.add_argument("--period", type=int, default=300, help="Draft period in seconds.")
    parser.add_argument("--evaluation-periods", type=int, default=3, help="Draft consecutive evaluation periods.")
    parser.add_argument("--statistic", default="average", help="Draft statistic, for example average/max/min.")
    parser.add_argument("--notification-enabled", action="store_true", help="Draft notification flag; planner-only.")
    parser.add_argument("--execute", action="store_true", help="Execute approved read-only CES discovery commands.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per executed read-only command.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be greater than 0.")
    if args.timeout < 1:
        parser.error("--timeout must be greater than 0.")
    if args.period < 1:
        parser.error("--period must be greater than 0.")
    if args.evaluation_periods < 1:
        parser.error("--evaluation-periods must be greater than 0.")
    return args


def main() -> int:
    """Build the planner-only CES alarm plan."""
    args = parse_args()
    result = build_plan(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
