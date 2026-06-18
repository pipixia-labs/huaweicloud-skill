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
