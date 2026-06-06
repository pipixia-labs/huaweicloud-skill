#!/usr/bin/env python3
"""Build planner-only Huawei Cloud billing and cost API request specs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import hcloud_common


DEFAULT_ENDPOINT_BASE = "https://bss-intl.myhuaweicloud.com"
BILL_CYCLE_RE = re.compile(r"^\d{4}-\d{2}$")

OPERATIONS: dict[str, dict[str, Any]] = {
    "monthly-sum": {
        "title": "ShowCustomerMonthlySum",
        "method": "GET",
        "path": "/v2/bills/customer-bills/monthly-sum",
        "doc_url": "https://support.huaweicloud.com/intl/zh-cn/api-oce/mbc_00008.html",
        "permission": "billing:bill:view",
        "required_query": ["bill_cycle"],
        "freshness": "Summary bill data contains consumption up to 24:00 of the previous day and supports recent 3 years.",
    },
    "cost-data": {
        "title": "ListCosts",
        "method": "POST",
        "path": "/v4/costs/cost-analysed-bills/query",
        "doc_url": "https://support.huaweicloud.com/intl/zh-cn/api-oce/costm_00014.html",
        "permission": "costCenter:costAnalysis:listCosts",
        "required_body": ["time_condition", "groupby", "cost_type", "amount_type"],
        "freshness": "Original costs have about one-hour delay; amortized costs refresh every 24 hours and may lag 24-48 hours.",
    },
    "resource-records": {
        "title": "ListCustomerselfResourceRecordDetails",
        "method": "POST",
        "path": "/v2/bills/customer-bills/res-records/query",
        "doc_url": "https://support.huaweicloud.com/intl/zh-cn/api-oce/mbc_00003.html",
        "permission": "billing:billDetail:view",
        "required_body": ["cycle"],
        "freshness": "Resource detail data can be delayed by up to 24 hours.",
    },
    "resource-fee-records": {
        "title": "ListCustomerselfResourceRecords",
        "method": "GET",
        "path": "/v2/bills/customer-bills/res-fee-records",
        "doc_url": "https://support.huaweicloud.com/intl/zh-cn/api-oce/mbc_00004.html",
        "permission": "billing:billDetail:view",
        "required_query": ["cycle"],
        "freshness": "Resource fee records are billing-period data; date filters must stay within the same cycle.",
    },
}

OPERATION_ALIASES = {
    "resource-details": "resource-records",
    "resource-detail": "resource-records",
    "resource-consumption": "resource-fee-records",
    "resource-fees": "resource-fee-records",
}


def parse_key_values(values: list[str]) -> dict[str, str]:
    """Parse repeated key=value CLI values into a dictionary."""
    parsed: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Expected key=value, got {item!r}.")
        key, value = item.split("=", 1)
        if not key:
            raise ValueError(f"Expected non-empty key in {item!r}.")
        parsed[key] = value
    return parsed


def parse_filters(values: list[str]) -> list[dict[str, Any]]:
    """Parse cost-data filters in KEY=value1,value2 form."""
    filters: list[dict[str, Any]] = []
    for item in values:
        if "=" not in item:
            raise ValueError(f"Expected KEY=value1,value2 filter, got {item!r}.")
        key, raw_values = item.split("=", 1)
        entries = [entry.strip() for entry in raw_values.split(",") if entry.strip()]
        if not key or not entries:
            raise ValueError(f"Expected non-empty key and value list in filter {item!r}.")
        filters.append(
            {
                "operator": 0,
                "filter_factor": {
                    "key": key,
                    "value": entries,
                },
            }
        )
    return filters


def optional_fields(**values: Any) -> dict[str, Any]:
    """Return fields whose values are not empty."""
    return {key: value for key, value in values.items() if value not in (None, "", [])}


def load_body_override(args: argparse.Namespace) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """Return an explicit JSON body override when supplied."""
    if args.body_json_file and args.body_json_text:
        return None, None, ["Use either --body-json-file or --body-json-text, not both."]
    if args.body_json_text:
        try:
            body = json.loads(args.body_json_text)
        except json.JSONDecodeError as exc:
            return None, "body-json-text", [f"Invalid --body-json-text: {exc}"]
        if not isinstance(body, dict):
            return None, "body-json-text", ["--body-json-text must decode to a JSON object."]
        return body, "body-json-text", []
    if args.body_json_file:
        try:
            body = json.loads(Path(args.body_json_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return None, "body-json-file", [f"Cannot read --body-json-file as JSON object: {exc}"]
        if not isinstance(body, dict):
            return None, "body-json-file", ["--body-json-file must decode to a JSON object."]
        return body, "body-json-file", []
    return None, None, []


def validate_cycle(field: str, value: str | None) -> list[str]:
    """Return validation errors for a YYYY-MM billing cycle field."""
    if not value:
        return [f"Missing required {field}."]
    if not BILL_CYCLE_RE.match(value):
        return [f"{field} must use YYYY-MM format."]
    return []


def build_monthly_sum_query(args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    """Build ShowCustomerMonthlySum query parameters."""
    errors = validate_cycle("bill_cycle", args.bill_cycle)
    query = optional_fields(
        bill_cycle=args.bill_cycle,
        service_type_code=args.service_type_code,
        enterprise_project_id=args.enterprise_project_id,
        method=args.method,
        sub_customer_id=args.sub_customer_id,
        offset=args.offset,
        limit=args.limit,
    )
    return query, errors


def build_cost_data_body(args: argparse.Namespace) -> tuple[dict[str, Any] | None, str, list[str]]:
    """Build or load a ListCosts request body."""
    body, source, errors = load_body_override(args)
    if body is not None or errors:
        return body, source or "generated", errors

    missing = [name for name in ("begin_time", "end_time") if not getattr(args, name)]
    if missing:
        return None, "generated", [f"Missing required cost-data field: {', '.join(missing)}."]

    body = {
        "amount_type": args.amount_type,
        "offset": args.offset,
        "cost_type": args.cost_type,
        "limit": args.limit,
        "groupby": [{"type": "dimension", "key": item} for item in args.group_by],
        "time_condition": {
            "time_measure_id": args.time_measure_id,
            "begin_time": args.begin_time,
            "end_time": args.end_time,
        },
    }
    if args.filter:
        body["filters"] = parse_filters(args.filter)
    return body, "generated", []


def build_resource_records_body(args: argparse.Namespace) -> tuple[dict[str, Any] | None, str, list[str]]:
    """Build or load a resource detail request body."""
    body, source, errors = load_body_override(args)
    if body is not None or errors:
        return body, source or "generated", errors

    errors = validate_cycle("cycle", args.bill_cycle)
    body = optional_fields(
        cycle=args.bill_cycle,
        cloud_service_type=args.service_type_code,
        resource_type=args.resource_type,
        region=args.region_code,
        res_instance_id=args.resource_id,
        charge_mode=args.charge_mode,
        bill_type=args.bill_type,
        enterprise_project_id=args.enterprise_project_id,
        include_zero_record=args.include_zero_record,
        method=args.method,
        sub_customer_id=args.sub_customer_id,
        offset=args.offset,
        limit=args.limit,
    )
    return body, "generated", errors


def build_resource_fee_query(args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    """Build ListCustomerselfResourceRecords query parameters."""
    errors = validate_cycle("cycle", args.bill_cycle)
    query = optional_fields(
        cycle=args.bill_cycle,
        charge_mode=args.charge_mode,
        cloud_service_type=args.service_type_code,
        region=args.region_code,
        bill_type=args.bill_type,
        res_instance_id=args.resource_id,
        enterprise_project_id=args.enterprise_project_id,
        method=args.method,
        sub_customer_id=args.sub_customer_id,
        bill_date_begin=args.begin_time,
        bill_date_end=args.end_time,
        statistic_type=args.statistic_type,
        offset=args.offset,
        limit=args.limit,
    )
    return query, errors


def build_url(endpoint_base: str, path: str, query: dict[str, Any]) -> str:
    """Return a request URL with encoded query parameters when present."""
    base = endpoint_base.rstrip("/")
    if not query:
        return f"{base}{path}"
    return f"{base}{path}?{urlencode(query)}"


def operation_name(raw_operation: str) -> str:
    """Resolve a user-facing operation name or alias."""
    return OPERATION_ALIASES.get(raw_operation, raw_operation)


def build_request_spec(args: argparse.Namespace) -> dict[str, Any]:
    """Build a planner-only billing/cost API request specification."""
    operation = operation_name(args.operation)
    metadata = OPERATIONS[operation]
    query: dict[str, Any] = {}
    body: dict[str, Any] | None = None
    body_source: str | None = None
    errors: list[str] = []

    try:
        raw_query = parse_key_values(args.query)
        if operation == "monthly-sum":
            query, errors = build_monthly_sum_query(args)
        elif operation == "cost-data":
            body, body_source, errors = build_cost_data_body(args)
        elif operation == "resource-records":
            body, body_source, errors = build_resource_records_body(args)
        elif operation == "resource-fee-records":
            query, errors = build_resource_fee_query(args)
        query.update(raw_query)
    except ValueError as exc:
        errors = [str(exc)]

    request_spec = {
        "method": metadata["method"],
        "endpoint_base": args.endpoint_base.rstrip("/"),
        "path": metadata["path"],
        "url": build_url(args.endpoint_base, metadata["path"], query),
        "headers": optional_fields(
            **{
                "Content-Type": "application/json",
                "X-Language": args.language,
            }
        ),
        "query": query,
        "body": hcloud_common.redact_json(body, set()) if body is not None else None,
        "body_source": body_source,
        "requires_auth": "customer AK/SK signature or customer token; credentials are intentionally not accepted by this planner.",
    }

    return {
        "success": not errors,
        "mode": "plan",
        "planning_only": True,
        "operation": operation,
        "title": metadata["title"],
        "request_spec": request_spec,
        "validation": {
            "errors": errors,
            "warnings": [
                "This script does not sign or send HTTP requests.",
                "Billing and cost data can contain account, resource, and spend-sensitive information; keep output scope narrow.",
                "Do not infer spend from resource inventory when billing APIs are unavailable.",
            ],
        },
        "execution_supported": False,
        "official_docs": {
            "url": metadata["doc_url"],
            "permission": metadata["permission"],
            "freshness": metadata["freshness"],
        },
        "next_steps": [
            "Confirm the account scope, enterprise project scope, time range, and permission boundary with the user.",
            "Use API Explorer, Huawei Cloud SDK, or a reviewed signed-request runner to execute this spec if live billing data is approved.",
            "Summarize billing output instead of pasting full raw records unless the user explicitly asks for the raw data scope.",
        ],
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=sorted(list(OPERATIONS) + list(OPERATION_ALIASES)), default="monthly-sum")
    parser.add_argument("--endpoint-base", default=DEFAULT_ENDPOINT_BASE, help="Billing endpoint base URL.")
    parser.add_argument("--language", default="zh_CN", help="X-Language header value.")
    parser.add_argument("--bill-cycle", help="Billing cycle in YYYY-MM format.")
    parser.add_argument("--begin-time", help="Cost begin_time or fee bill_date_begin.")
    parser.add_argument("--end-time", help="Cost end_time or fee bill_date_end.")
    parser.add_argument("--time-measure-id", type=int, default=1, choices=[1, 2], help="Cost time unit: 1 day, 2 month.")
    parser.add_argument("--group-by", action="append", default=None, help="Cost groupby dimension key.")
    parser.add_argument("--filter", action="append", default=[], help="Cost filter as KEY=value1,value2. Can be repeated.")
    parser.add_argument("--cost-type", default="ORIGINAL_COST", choices=["ORIGINAL_COST", "AMORTIZED_COST"])
    parser.add_argument("--amount-type", default="PAYMENT_AMOUNT", choices=["PAYMENT_AMOUNT", "NET_AMOUNT"])
    parser.add_argument("--service-type-code", help="Cloud service type code.")
    parser.add_argument("--resource-type", help="Resource type code.")
    parser.add_argument("--region-code", help="Billing region code filter, for example ap-southeast-1.")
    parser.add_argument("--resource-id", help="Resource instance ID filter.")
    parser.add_argument("--enterprise-project-id", help="Enterprise project ID filter.")
    parser.add_argument("--charge-mode", help="Charging mode filter.")
    parser.add_argument("--bill-type", type=int, help="Bill type filter.")
    parser.add_argument("--method", help="Query scope, for example oneself, sub_customer, or all.")
    parser.add_argument("--sub-customer-id", help="Sub-customer account ID for enterprise master-account queries.")
    parser.add_argument("--include-zero-record", help="Whether to include zero records for resource detail queries.")
    parser.add_argument("--statistic-type", type=int, help="Resource fee record statistic type.")
    parser.add_argument("--offset", type=int, default=0, help="Pagination offset.")
    parser.add_argument("--limit", type=int, default=10, help="Pagination limit.")
    parser.add_argument("--query", action="append", default=[], help="Additional raw query key=value. Can be repeated.")
    parser.add_argument("--body-json-file", help="Explicit JSON request body file for POST operations.")
    parser.add_argument("--body-json-text", help="Explicit JSON request body text for POST operations.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    args.operation = operation_name(args.operation)
    if args.offset < 0:
        parser.error("--offset must be greater than or equal to 0.")
    if args.limit < 1:
        parser.error("--limit must be greater than 0.")
    args.group_by = args.group_by or ["CLOUD_SERVICE_TYPE"]
    return args


def main() -> int:
    """Build the billing/cost request spec."""
    args = parse_args()
    result = build_request_spec(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
