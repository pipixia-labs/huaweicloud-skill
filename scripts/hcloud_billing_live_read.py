#!/usr/bin/env python3
"""Run an explicitly approved read-only Huawei Cloud BSS query and summarize it."""

from __future__ import annotations

import argparse
import json
import subprocess
from types import SimpleNamespace
from typing import Any

import hcloud_billing_readonly
import hcloud_billing_result_summarize
import hcloud_common


CONFIRM_TOKEN = "READ_BILLING_DATA"
MAX_LIVE_LIMIT = 50
READ_ONLY_PREFIXES = ("List", "Show")


def billing_args(args: argparse.Namespace) -> SimpleNamespace:
    """Return the argument namespace expected by the BSS readonly planner."""
    return SimpleNamespace(
        operation=args.operation,
        entry_point=args.entry_point,
        endpoint_base=args.endpoint_base,
        language=args.language,
        bill_cycle=args.bill_cycle,
        shared_month=args.shared_month,
        begin_time=args.begin_time,
        end_time=args.end_time,
        time_measure_id=args.time_measure_id,
        group_by=args.group_by,
        filter=args.filter,
        cost_type=args.cost_type,
        amount_type=args.amount_type,
        project_id=args.project_id,
        service_type_code=args.service_type_code,
        resource_type=args.resource_type,
        resource_spec=args.resource_spec,
        usage_type=args.usage_type,
        region_code=args.region_code,
        pricing_region=args.pricing_region,
        available_zone=args.available_zone,
        pricing_preset=args.pricing_preset,
        resource_size=args.resource_size,
        size_measure_id=args.size_measure_id,
        usage_value=args.usage_value,
        subscription_num=args.subscription_num,
        inquiry_precision=args.inquiry_precision,
        period_type=args.period_type,
        period_num=args.period_num,
        fee_installment_mode=args.fee_installment_mode,
        resource_id=args.resource_id,
        enterprise_project_id=args.enterprise_project_id,
        charge_mode=args.charge_mode,
        bill_type=args.bill_type,
        method=args.method,
        sub_customer_id=args.sub_customer_id,
        customer_id=args.customer_id,
        order_id=args.order_id,
        balance_type=args.balance_type,
        status=args.status,
        free_resource_id=args.free_resource_id,
        quota_id=args.quota_id,
        include_zero_record=args.include_zero_record,
        statistic_type=args.statistic_type,
        offset=args.offset,
        limit=args.limit,
        query=args.query,
        body_json_file=args.body_json_file,
        body_json_text=args.body_json_text,
    )


def planned_int_field(request_spec: dict[str, Any], field: str, fallback: int) -> int:
    """Return an integer pagination field from the final planned BSS call."""
    for container_name in ("query", "body"):
        container = request_spec.get(container_name)
        if isinstance(container, dict) and container.get(field) not in (None, ""):
            try:
                return int(container[field])
            except (TypeError, ValueError):
                return fallback
    return fallback


def validate_live_read_plan(billing_plan: dict[str, Any], *, fallback_limit: int) -> list[str]:
    """Return blocking errors for a candidate live Billing/BSS read."""
    errors: list[str] = []
    command_plan = billing_plan.get("hcloud_command_plan", {})
    operation = str(command_plan.get("operation") or "")
    defaults = command_plan.get("cli_defaults", {})
    request_spec = billing_plan.get("request_spec", {})
    headers = request_spec.get("headers", {}) if isinstance(request_spec, dict) else {}
    x_language = str(headers.get("X-Language") or "") if isinstance(headers, dict) else ""
    limit = planned_int_field(request_spec, "limit", fallback_limit)

    if not billing_plan.get("success"):
        errors.append("Billing request plan is invalid; fix validation.errors before live read.")
    if not billing_plan.get("execution_supported") or not command_plan.get("supported"):
        errors.append("Billing request plan is not executable through the reviewed hcloud command plan.")
    if command_plan.get("service") != "BSS":
        errors.append("Only BSS live reads are allowed by this wrapper.")
    if not operation.startswith(READ_ONLY_PREFIXES):
        errors.append(f"Only read-only BSS List*/Show* operations are allowed, got {operation or '<missing>'}.")
    if defaults.get("cli_region") != hcloud_billing_readonly.BSS_CLI_REGION:
        errors.append("BSS live reads must use the reviewed fixed cli-region cn-north-1.")
    if x_language not in hcloud_billing_readonly.SUPPORTED_X_LANGUAGES:
        errors.append("BSS live reads must pass an official X-Language value: zh_CN or en_US.")
    if limit > MAX_LIVE_LIMIT:
        errors.append(f"Live BSS read limit must be <= {MAX_LIVE_LIMIT}; got {limit}.")
    if limit < 1:
        errors.append("Live BSS read limit must be greater than 0.")
    return errors


def safe_exec_command(command_plan: dict[str, Any], args: argparse.Namespace) -> list[str] | None:
    """Return the safe_exec command with runtime bounds attached."""
    command = command_plan.get("safe_exec_command")
    if not isinstance(command, list):
        return None
    return [str(item) for item in command] + [
        "--timeout",
        str(args.timeout),
        "--max-output-chars",
        str(args.max_output_chars),
    ]


def parse_safe_exec_stdout(stdout: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse a safe_exec JSON result from stdout."""
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if not isinstance(value, dict):
        return None, "safe_exec stdout must decode to a JSON object."
    return value, None


def safe_exec_status(
    value: dict[str, Any] | None,
    completed: subprocess.CompletedProcess[str] | None = None,
) -> dict[str, Any]:
    """Return safe execution metadata without embedding raw BSS payload rows."""
    if not isinstance(value, dict):
        return {
            "success": False,
            "return_code": completed.returncode if completed is not None else None,
        }
    return {
        "success": bool(value.get("success")),
        "return_code": value.get("return_code"),
        "duration_seconds": value.get("duration_seconds"),
        "service": value.get("service"),
        "operation": value.get("operation"),
        "command": value.get("command"),
        "error_type": value.get("error_type"),
        "error_details": value.get("error_details"),
        "advice": value.get("advice"),
        "stdout_truncated": value.get("stdout_truncated"),
        "stderr_truncated": value.get("stderr_truncated"),
    }


def run_safe_exec(command: list[str], args: argparse.Namespace, request_spec: dict[str, Any]) -> dict[str, Any]:
    """Run safe_exec and return a redacted summary of the BSS payload."""
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=args.timeout + 5,
    )
    safe_exec_result, parse_error = parse_safe_exec_stdout(completed.stdout)
    if parse_error:
        return {
            "executed": True,
            "success": False,
            "safe_exec_status": safe_exec_status(None, completed),
            "safe_exec_parse_error": parse_error,
            "stderr": completed.stderr,
            "summary": None,
        }

    summary = hcloud_billing_result_summarize.build_summary(
        safe_exec_result,
        offset=planned_int_field(request_spec, "offset", args.offset),
        limit=planned_int_field(request_spec, "limit", args.limit),
        include_redacted_records=args.include_redacted_records,
    )
    return {
        "executed": True,
        "success": bool(safe_exec_result.get("success")) and bool(summary.get("success")),
        "safe_exec_status": safe_exec_status(safe_exec_result, completed),
        "safe_exec_parse_error": None,
        "summary": summary,
    }


def build_live_read(args: argparse.Namespace) -> dict[str, Any]:
    """Build or execute a guarded read-only Billing/BSS live-read workflow."""
    plan = hcloud_billing_readonly.build_request_spec(billing_args(args))
    guard_errors = validate_live_read_plan(plan, fallback_limit=args.limit)
    command_plan = plan.get("hcloud_command_plan", {})
    command = safe_exec_command(command_plan, args)
    approval_ok = args.confirm_live_billing_read == CONFIRM_TOKEN

    result: dict[str, Any] = {
        "success": not guard_errors and not args.execute,
        "mode": "execute" if args.execute else "plan",
        "planning_only": not args.execute,
        "operation": plan.get("operation"),
        "title": plan.get("title"),
        "billing_request_plan": plan,
        "live_read_plan": {
            "supported": not guard_errors and command is not None,
            "guard_errors": guard_errors,
            "safe_exec_command": command,
            "max_live_limit": MAX_LIVE_LIMIT,
            "confirmation": {
                "required": True,
                "token": CONFIRM_TOKEN,
                "accepted": approval_ok,
            },
            "output_boundary": {
                "default_output": "redacted_summary_only",
                "raw_safe_exec_result_returned": False,
            },
        },
        "execution": {
            "requested": bool(args.execute),
            "executed": False,
            "result": None,
        },
    }

    if not args.execute:
        return result
    if guard_errors:
        result["success"] = False
        return result
    if command is None:
        result["success"] = False
        result["live_read_plan"]["guard_errors"].append("No safe_exec command was generated.")
        return result
    if not approval_ok:
        result["success"] = False
        result["live_read_plan"]["guard_errors"].append(
            f"Live billing read requires --confirm-live-billing-read {CONFIRM_TOKEN}."
        )
        return result

    execution_result = run_safe_exec(command, args, plan.get("request_spec", {}))
    result["execution"] = {
        "requested": True,
        "executed": True,
        "result": execution_result,
    }
    result["success"] = bool(execution_result.get("success"))
    return result


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operation",
        choices=sorted(list(hcloud_billing_readonly.OPERATIONS) + list(hcloud_billing_readonly.OPERATION_ALIASES)),
    )
    parser.add_argument("--entry-point", choices=hcloud_billing_readonly.semantic_entry_point_names())
    parser.add_argument("--endpoint-base", default=hcloud_billing_readonly.DEFAULT_ENDPOINT_BASE)
    parser.add_argument("--language", default="zh_CN")
    parser.add_argument("--bill-cycle")
    parser.add_argument("--shared-month")
    parser.add_argument("--begin-time")
    parser.add_argument("--end-time")
    parser.add_argument("--time-measure-id", type=int, default=1, choices=[1, 2])
    parser.add_argument("--group-by", action="append", default=None)
    parser.add_argument("--filter", action="append", default=[])
    parser.add_argument("--cost-type", default="ORIGINAL_COST", choices=["ORIGINAL_COST", "AMORTIZED_COST"])
    parser.add_argument("--amount-type", default="PAYMENT_AMOUNT", choices=["PAYMENT_AMOUNT", "NET_AMOUNT"])
    parser.add_argument("--project-id")
    parser.add_argument("--service-type-code")
    parser.add_argument("--resource-type")
    parser.add_argument("--resource-spec", action="append")
    parser.add_argument("--usage-type")
    parser.add_argument("--region-code")
    parser.add_argument("--pricing-region")
    parser.add_argument("--available-zone")
    parser.add_argument("--pricing-preset")
    parser.add_argument("--resource-size", type=int, action="append")
    parser.add_argument("--size-measure-id", type=int, action="append")
    parser.add_argument("--usage-value", type=float, action="append")
    parser.add_argument("--subscription-num", type=int, action="append")
    parser.add_argument("--inquiry-precision", type=int, default=1, choices=[0, 1])
    parser.add_argument("--period-type", action="append")
    parser.add_argument("--period-num", type=int, action="append")
    parser.add_argument("--fee-installment-mode", choices=["HALF_PAY", "ZERO_PAY", "NA"])
    parser.add_argument("--resource-id")
    parser.add_argument("--enterprise-project-id")
    parser.add_argument("--charge-mode")
    parser.add_argument("--bill-type", type=int)
    parser.add_argument("--method")
    parser.add_argument("--sub-customer-id")
    parser.add_argument("--customer-id")
    parser.add_argument("--order-id")
    parser.add_argument("--balance-type")
    parser.add_argument("--status")
    parser.add_argument("--free-resource-id")
    parser.add_argument("--quota-id")
    parser.add_argument("--include-zero-record")
    parser.add_argument("--statistic-type", type=int)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--body-json-file")
    parser.add_argument("--body-json-text")
    parser.add_argument("--execute", action="store_true", help="Execute the reviewed BSS safe_exec command.")
    parser.add_argument("--confirm-live-billing-read", help=f"Must equal {CONFIRM_TOKEN} when --execute is used.")
    parser.add_argument("--include-redacted-records", action="store_true", help="Include redacted BSS records in the summary.")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-output-chars", type=int, default=20000)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if args.operation is None and args.entry_point:
        route = hcloud_billing_readonly.build_semantic_route(args.entry_point)
        supported = route.get("supported_planner_operations", []) if route else []
        args.operation = supported[0] if supported else "monthly-sum"
    args.operation = hcloud_billing_readonly.operation_name(args.operation or "monthly-sum")
    args.group_by = args.group_by or ["CLOUD_SERVICE_TYPE"]
    if args.offset < 0:
        parser.error("--offset must be greater than or equal to 0.")
    if args.limit < 1:
        parser.error("--limit must be greater than 0.")
    if args.timeout < 1:
        parser.error("--timeout must be greater than 0.")
    if args.max_output_chars < 1:
        parser.error("--max-output-chars must be greater than 0.")
    return args


def main() -> int:
    """Build or execute the guarded BSS live-read workflow."""
    args = parse_args()
    result = build_live_read(args)
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
