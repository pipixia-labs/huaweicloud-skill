#!/usr/bin/env python3
"""Build planner-only Huawei Cloud billing and cost specs plus hcloud command plans."""

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
SEMANTIC_CATALOG_PATH = hcloud_common.REFERENCES_DIR / "billing" / "semantic-catalog.json"
BSS_CLI_REGION = "cn-north-1"
BSS_CLI_LANG = "cn"

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
SOURCE_OPERATION_TO_PLANNER = {
    f"BSS/{metadata['title']}": operation for operation, metadata in OPERATIONS.items()
}


def load_semantic_catalog(path: Path = SEMANTIC_CATALOG_PATH) -> dict[str, Any]:
    """Load the local billing semantic catalog."""
    if not path.exists():
        return {"entry_points": {}, "entities": {}}
    return hcloud_common.load_json(path)


def semantic_entry_point_names() -> list[str]:
    """Return known billing semantic entry point names."""
    return sorted(load_semantic_catalog().get("entry_points", {}))


def build_semantic_route(entry_point: str | None, catalog: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return semantic billing route metadata for an entry point."""
    if not entry_point:
        return None
    catalog = catalog or load_semantic_catalog()
    entry = catalog.get("entry_points", {}).get(entry_point)
    if not isinstance(entry, dict):
        return {
            "entry_point": entry_point,
            "found": False,
            "error": "Unknown billing semantic entry point.",
        }

    entities = catalog.get("entities", {})
    entity_details = {
        name: entities.get(name, {})
        for name in entry.get("ontology_entities", [])
    }
    source_operations = sorted(
        {
            operation
            for details in entity_details.values()
            for operation in details.get("source_operations", [])
        }
    )
    supported_operations = sorted(
        set(entry.get("supported_planner_operations", []))
        | {
            SOURCE_OPERATION_TO_PLANNER[operation]
            for operation in source_operations
            if operation in SOURCE_OPERATION_TO_PLANNER
        }
    )
    supported_source_operations = sorted(
        operation for operation in source_operations if operation in SOURCE_OPERATION_TO_PLANNER
    )
    return {
        "entry_point": entry_point,
        "found": True,
        "required_context": entry.get("required_context", {}),
        "triggers": entry.get("triggers", []),
        "money_basis": entry.get("required_context", {}).get("money_basis", []),
        "ontology_entities": entry.get("ontology_entities", []),
        "entity_details": entity_details,
        "source_operations": source_operations,
        "supported_planner_operations": supported_operations,
        "supported_source_operations": supported_source_operations,
        "unsupported_source_operations": [
            operation for operation in source_operations if operation not in set(supported_source_operations)
        ],
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


def cli_defaults(catalog: dict[str, Any]) -> dict[str, str]:
    """Return fixed BSS KooCLI defaults."""
    defaults = catalog.get("bss_cli_defaults", {})
    return {
        "cli_region": str(defaults.get("cli_region") or BSS_CLI_REGION),
        "cli_lang": str(defaults.get("cli_lang") or BSS_CLI_LANG),
    }


def operation_name(raw_operation: str) -> str:
    """Resolve a user-facing operation name or alias."""
    return OPERATION_ALIASES.get(raw_operation, raw_operation)


def scalar_cli_value(value: Any) -> str:
    """Return a stable KooCLI scalar argument value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def flatten_cli_args(prefix: str, value: Any) -> list[str]:
    """Flatten a JSON-like body into KooCLI dot-notation arguments."""
    if value in (None, "", []):
        return []
    if isinstance(value, dict):
        args: list[str] = []
        for key, child in value.items():
            args.extend(flatten_cli_args(f"{prefix}.{key}", child))
        return args
    if isinstance(value, list):
        args = []
        for index, child in enumerate(value, start=1):
            args.extend(flatten_cli_args(f"{prefix}.{index}", child))
        return args
    return [f"--{prefix}={scalar_cli_value(value)}"]


def hcloud_safe_exec_command(operation: str, args: list[str], defaults: dict[str, str]) -> list[str]:
    """Return a safe_exec wrapped read-only BSS command."""
    command = hcloud_common.safe_exec_command_prefix() + [
        "--service",
        "BSS",
        "--operation",
        operation,
        "--arg=--cli-output=json",
        "--expect-json",
    ]
    command.append(f"--arg=--cli-region={defaults['cli_region']}")
    command.append(f"--arg=--cli-lang={defaults['cli_lang']}")
    command.extend(f"--arg={item}" for item in args)
    return command


def build_hcloud_command_plan(
    operation: str,
    metadata: dict[str, Any],
    request_spec: dict[str, Any],
    body_source: str | None,
    defaults: dict[str, str],
) -> dict[str, Any]:
    """Return a reviewed hcloud read-only command plan or a blocked reason."""
    blocked_reasons: list[str] = []
    cli_args: list[str] = []

    if metadata["method"] == "POST" and body_source != "generated":
        blocked_reasons.append("Explicit JSON bodies are kept as request specs; this planner only maps generated safe fields to KooCLI dot notation.")

    for key, value in request_spec.get("query", {}).items():
        if value not in (None, "", []):
            cli_args.append(f"--{key}={scalar_cli_value(value)}")
    body = request_spec.get("body")
    if body and not blocked_reasons:
        for key, value in body.items():
            cli_args.extend(flatten_cli_args(key, value))

    safe_exec_command = hcloud_safe_exec_command(metadata["title"], cli_args, defaults) if not blocked_reasons else None
    return {
        "supported": not blocked_reasons,
        "blocked_reasons": blocked_reasons,
        "read_only": True,
        "service": "BSS",
        "operation": metadata["title"],
        "cli_defaults": defaults,
        "hcloud_args": cli_args,
        "safe_exec_command": safe_exec_command,
        "execution_requires_user_approval": True,
        "sensitivity": {
            "level": "high",
            "reason": "Billing data can expose account identifiers, resource identifiers, order data, and spend.",
        },
        "output_boundary": {
            "summarize_by_default": True,
            "raw_output_allowed_only_after_scope_confirmation": True,
            "protected_identifiers": load_semantic_catalog().get("protected_identifiers", []),
        },
    }


def pagination_scope(query: dict[str, Any], body: dict[str, Any] | None) -> dict[str, Any]:
    """Return pagination completeness metadata for billing queries."""
    source = body if body is not None else query
    offset = source.get("offset") if isinstance(source, dict) else None
    limit = source.get("limit") if isinstance(source, dict) else None
    return {
        "offset": offset,
        "limit": limit,
        "complete_result_claim_allowed": False,
        "reason": "A single billing page is partial until total_count and all intended pages are reviewed.",
    }


def billing_period_fields(query: dict[str, Any], body: dict[str, Any] | None) -> list[str]:
    """Return fields that define the billing period or time window."""
    fields: list[str] = []
    for key in ("bill_cycle", "cycle", "bill_date_begin", "bill_date_end"):
        if query.get(key) not in (None, "", []):
            fields.append(key)
    if isinstance(body, dict):
        for key in ("cycle", "bill_date_begin", "bill_date_end"):
            if body.get(key) not in (None, "", []):
                fields.append(key)
        time_condition = body.get("time_condition")
        if isinstance(time_condition, dict):
            for key in ("begin_time", "end_time", "time_measure_id"):
                if time_condition.get(key) not in (None, "", []):
                    fields.append(f"time_condition.{key}")
    return sorted(set(fields))


def scope_fields(query: dict[str, Any], body: dict[str, Any] | None) -> list[str]:
    """Return fields that narrow the account, service, region, or resource scope."""
    known_scope_keys = {
        "method",
        "sub_customer_id",
        "enterprise_project_id",
        "service_type_code",
        "cloud_service_type",
        "resource_type",
        "region",
        "region_code",
        "res_instance_id",
        "resource_id",
        "charge_mode",
        "bill_type",
    }
    fields = [key for key, value in query.items() if key in known_scope_keys and value not in (None, "", [])]
    if isinstance(body, dict):
        fields.extend(key for key, value in body.items() if key in known_scope_keys and value not in (None, "", []))
        for group in body.get("groupby", []) if isinstance(body.get("groupby"), list) else []:
            if isinstance(group, dict) and group.get("key"):
                fields.append(f"groupby:{group['key']}")
        for item in body.get("filters", []) if isinstance(body.get("filters"), list) else []:
            factor = item.get("filter_factor") if isinstance(item, dict) else None
            if isinstance(factor, dict) and factor.get("key"):
                fields.append(f"filter:{factor['key']}")
    return sorted(set(fields))


def semantic_grains(semantic_route: dict[str, Any] | None) -> list[str]:
    """Return grain descriptions from the selected semantic route."""
    if not semantic_route or not semantic_route.get("found"):
        return []
    grains = [
        str(details.get("grain"))
        for details in semantic_route.get("entity_details", {}).values()
        if details.get("grain")
    ]
    return sorted(set(grains))


def billing_semantic_discipline(
    metadata: dict[str, Any],
    semantic_route: dict[str, Any] | None,
    query: dict[str, Any],
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the billing answer discipline tuple required before summaries."""
    route_context = semantic_route.get("required_context", {}) if semantic_route and semantic_route.get("found") else {}
    return {
        "required_tuple": ["fact", "grain", "money_basis", "scope", "billing_period"],
        "selected_fact": metadata["title"],
        "semantic_entry_point": semantic_route.get("entry_point") if semantic_route else None,
        "grain_candidates": semantic_grains(semantic_route),
        "money_basis": route_context.get("money_basis", []),
        "scope_fields": scope_fields(query, body),
        "billing_period_fields": billing_period_fields(query, body),
        "non_additive_rule": (
            "Do not add or compare billing outputs unless fact, grain, money_basis, scope, "
            "and billing_period are compatible."
        ),
        "separate_fact_examples": [
            "monthly_summary",
            "resource_fee_record",
            "resource_detail",
            "cost_analysis",
            "order_or_refund",
            "coupon_or_stored_value",
        ],
    }


def build_request_spec(args: argparse.Namespace) -> dict[str, Any]:
    """Build a planner-only billing/cost API request specification."""
    operation = operation_name(args.operation or "monthly-sum")
    metadata = OPERATIONS[operation]
    semantic_catalog = load_semantic_catalog()
    defaults = cli_defaults(semantic_catalog)
    semantic_route = build_semantic_route(getattr(args, "entry_point", None), semantic_catalog)
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
    command_plan = build_hcloud_command_plan(operation, metadata, request_spec, body_source, defaults)

    warnings = [
        "This script does not sign or send HTTP requests.",
        "Billing and cost data can contain account, resource, and spend-sensitive information; keep output scope narrow.",
        "Do not infer spend from resource inventory when billing APIs are unavailable.",
        "BSS hcloud templates must use --cli-region=cn-north-1 and --cli-lang=cn regardless of normal project region.",
        "Do not claim full-account totals from one page unless pagination has been completed and checked.",
    ]
    if semantic_route and semantic_route.get("found") and operation not in semantic_route.get("supported_planner_operations", []):
        warnings.append(
            "The selected operation is not the first-fit planner operation for the semantic entry point; review semantic_route.supported_planner_operations."
        )

    return {
        "success": not errors,
        "mode": "plan",
        "planning_only": True,
        "operation": operation,
        "title": metadata["title"],
        "semantic_route": semantic_route,
        "billing_semantic_discipline": billing_semantic_discipline(metadata, semantic_route, query, body),
        "bss_cli_defaults": defaults,
        "request_spec": request_spec,
        "hcloud_command_plan": command_plan,
        "pagination_scope": pagination_scope(query, body),
        "validation": {
            "errors": errors,
            "warnings": warnings,
        },
        "execution_supported": bool(command_plan.get("supported")) and not errors,
        "official_docs": {
            "url": metadata["doc_url"],
            "permission": metadata["permission"],
            "freshness": metadata["freshness"],
        },
        "next_steps": [
            "Confirm the account scope, enterprise project scope, time range, and permission boundary with the user.",
            "If live billing access is approved, run only the generated hcloud_command_plan.safe_exec_command and summarize the redacted result.",
            "Summarize billing output instead of pasting full raw records unless the user explicitly asks for the raw data scope.",
        ],
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=sorted(list(OPERATIONS) + list(OPERATION_ALIASES)))
    parser.add_argument("--entry-point", choices=semantic_entry_point_names(), help="Optional billing semantic entry point.")
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
    if args.operation is None and args.entry_point:
        route = build_semantic_route(args.entry_point)
        supported = route.get("supported_planner_operations", []) if route else []
        args.operation = supported[0] if supported else "monthly-sum"
    args.operation = operation_name(args.operation or "monthly-sum")
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
