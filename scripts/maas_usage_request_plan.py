#!/usr/bin/env python3
"""Build a dry-run request plan for Huawei Cloud MaaS usage statistics."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import hcloud_common


DEFAULT_REGION = "cn-southwest-2"
SERVICE_TYPES = {
    "my-service": 1,
    "preset-service": 2,
    "custom-endpoint": 4,
}
INFER_TYPES = ("real_time", "batch")
PRESETS = ("last-7-days", "last-14-days", "last-30-days", "this-month")
CREDENTIAL_ENV_KEYS = (
    "HW_ACCESS_KEY",
    "HW_SECRET_KEY",
    "HW_PROJECT_ID",
    "HW_SECURITY_TOKEN",
    "HUAWEICLOUD_ACCESS_KEY",
    "HUAWEICLOUD_SECRET_KEY",
    "HUAWEICLOUD_PROJECT_ID",
)


class MaasUsagePlanError(ValueError):
    """Raised when a MaaS usage request plan cannot be built."""


@dataclass(frozen=True)
class DateRange:
    """Normalized MaaS statistics date range."""

    start: date
    end: date
    source: str

    @property
    def days(self) -> int:
        """Return the number of calendar days in the range."""
        return (self.end - self.start).days


def env_presence(keys: tuple[str, ...] = CREDENTIAL_ENV_KEYS) -> dict[str, dict[str, bool]]:
    """Return redacted credential environment presence."""
    return {key: {"set": bool(os.environ.get(key)), "empty": os.environ.get(key) == ""} for key in keys}


def parse_date(value: str, name: str) -> date:
    """Parse a YYYY-MM-DD date string."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise MaasUsagePlanError(f"{name} must use YYYY-MM-DD format: {value}") from exc


def resolve_date_range(args: argparse.Namespace, *, today: date | None = None) -> DateRange:
    """Resolve explicit or preset MaaS usage date ranges."""
    today = today or date.today()
    if args.start_date or args.end_date:
        if not args.start_date or not args.end_date:
            raise MaasUsagePlanError("--from and --to must be provided together.")
        date_range = DateRange(
            start=parse_date(args.start_date, "--from"),
            end=parse_date(args.end_date, "--to"),
            source="explicit",
        )
    elif args.preset == "this-month":
        date_range = DateRange(start=today.replace(day=1), end=today, source=args.preset)
    else:
        days = {
            "last-7-days": 7,
            "last-14-days": 14,
            "last-30-days": 30,
        }[args.preset]
        date_range = DateRange(start=today - timedelta(days=days), end=today, source=args.preset)

    if date_range.end <= date_range.start:
        raise MaasUsagePlanError("The end date must be later than the start date.")
    return date_range


def build_warnings(args: argparse.Namespace, date_range: DateRange, *, today: date | None = None) -> list[str]:
    """Return request planning warnings."""
    today = today or date.today()
    warnings: list[str] = []
    if args.region != DEFAULT_REGION:
        warnings.append("MaaS ShowStatistics is expected to be available only in cn-southwest-2; verify region support before execution.")
    if date_range.days > 30:
        warnings.append("The requested range is longer than 30 days; split into 30-day windows and aggregate results.")
    if date_range.start < today - timedelta(days=30):
        warnings.append("MaaS statistics are documented as retaining roughly 30 days of data; older data may be unavailable.")
    if args.service_type == "custom-endpoint":
        warnings.append("Custom endpoint statistics use service_type=4; do not use service_type=3.")
    return warnings


def build_plan(args: argparse.Namespace, *, today: date | None = None) -> dict[str, Any]:
    """Build a non-executing MaaS usage statistics request plan."""
    today = today or date.today()
    date_range = resolve_date_range(args, today=today)
    service_type = SERVICE_TYPES[args.service_type]
    body = {
        "service_type": service_type,
        "infer_type": args.infer_type,
        "start_time": f"{date_range.start.isoformat()} 00:00:00",
        "end_time": f"{date_range.end.isoformat()} 00:00:00",
    }
    return {
        "success": True,
        "dry_run": True,
        "method": "POST",
        "endpoint": f"https://modelarts.{args.region}.myhuaweicloud.com/v1/{{project_id}}/maas/monitoring/show-statistics",
        "region": args.region,
        "date_range": {
            "from": date_range.start.isoformat(),
            "to": date_range.end.isoformat(),
            "days": date_range.days,
            "source": date_range.source,
        },
        "auth": {
            "mode": "AK/SK signing",
            "credential_presence": env_presence(),
            "secrets_printed": False,
            "note": "Do not paste AK/SK into chat. Configure credentials locally through environment variables or an hcloud profile-derived workflow.",
        },
        "request_body": body,
        "required_permissions": [
            "modelarts:monitoring:get",
            "modelarts:service:get",
            "iam:projects:get",
        ],
        "response_notes": {
            "usage_fields": [
                "total_token",
                "total_prompt_token",
                "total_completion_token",
                "total_request_count",
                "total_error_count",
            ],
            "token_unit": "Returned token values are in thousands; multiply by 1000 before reporting actual token counts.",
            "error_rate": "total_error_count / total_request_count, when total_request_count is greater than zero.",
        },
        "warnings": build_warnings(args, date_range, today=today),
        "execution_boundary": "This planner does not sign requests, call MaaS APIs, read credential values, or query billing data.",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start_date", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--to", dest="end_date", help="End date in YYYY-MM-DD format.")
    parser.add_argument("--preset", choices=PRESETS, default="last-7-days", help="Date preset used when --from/--to are omitted.")
    parser.add_argument("--region", default=DEFAULT_REGION, help="MaaS statistics region.")
    parser.add_argument("--service-type", choices=tuple(SERVICE_TYPES), default="preset-service", help="MaaS service type to query.")
    parser.add_argument("--infer-type", choices=INFER_TYPES, default="real_time", help="Inference type.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    try:
        result = build_plan(args)
    except MaasUsagePlanError as exc:
        hcloud_common.emit_json({"success": False, "error": str(exc)}, pretty=args.pretty)
        return 2
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
