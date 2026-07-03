# Billing Cost Governance

Use this playbook when the user asks for billing, cost analysis, chargeback, resource fee records, or cost-governance evidence.

## Inputs

- Billing cycle, for example `YYYY-MM`.
- Cost analysis begin/end time and grouping dimension.
- Enterprise project, service type, resource type, region, or resource ID filters when available.
- Permission scope for billing and cost data.

## Read-Only Flow

1. Use `hcloud_billing_readonly.py` to generate official Billing/Cost request specs and reviewed hcloud command plans.
2. For monthly summaries, plan `ShowCustomerMonthlySum` with an explicit billing cycle.
3. For cost analysis, plan `ListCosts` with a bounded time window and grouping dimension.
4. For resource details, plan `ListCustomerselfResourceRecordDetails` or `ListCustomerselfResourceRecords` with cycle and scope filters.
5. Execute only `hcloud_command_plan.safe_exec_command` after the user approves live billing access, account scope, time range, and output handling. BSS hcloud command templates must use `--cli-region=cn-north-1` and `--cli-lang=cn`.
6. Summarize saved safe_exec output with `hcloud_billing_result_summarize.py` before showing data to the user. Use `--include-redacted-records` only when raw row-level evidence is needed and the scope is confirmed.

## Semantic Discipline

Every billing answer must identify the tuple `fact × grain × money_basis × scope/billing_period` before calculating totals, comparisons, or rankings.

- `fact`: the source fact, such as monthly summary, cost analysis, resource fee record, resource detail, order, refund, balance, or coupon.
- `grain`: the row level, such as billing cycle × service, resource detail row, daily cost bucket, order row, or point-in-time balance.
- `money_basis`: billed, paid, outstanding, amortized, or not applicable. Do not mix these bases in one total.
- `scope`: account, enterprise project, sub-customer, cloud service, resource type, region, resource ID, or other filters.
- `billing_period`: bill cycle, date range, point-in-time, or not applicable.

Do not add monthly summary, resource detail, amortized cost, orders, refunds, and coupon deductions as if they were the same fact. If two outputs use different `fact`, `grain`, `money_basis`, `scope`, or `billing_period`, present them as separate evidence and explain the relationship instead of forcing one number.

## Guardrails

- The bundled planner does not sign requests, accept credentials, send HTTP traffic, or execute hcloud by default.
- Billing and cost data can expose account, resource, and spend-sensitive fields.
- Do not infer cost from resource inventory when billing APIs are unavailable.
- Summarize counts, totals, filters, and major drivers before sharing raw records.
- A single page is partial. Do not claim full-account totals or complete rankings until `total_count`, `offset`, `limit`, and all intended pages have been reviewed.
- Protected identifiers such as account, customer, resource, order, transaction, coupon, quota, and card IDs must be redacted or hashed before display.

## Promotion Gaps

- Collect read-only smoke evidence for safe BSS metadata-backed query shapes.
- Document freshness, permission, and enterprise-project scope limits for each supported request type.
