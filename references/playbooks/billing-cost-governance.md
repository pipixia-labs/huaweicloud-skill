# Billing Cost Governance

Use this playbook when the user asks for billing, cost analysis, chargeback, resource fee records, or cost-governance evidence.

## Inputs

- Billing cycle, for example `YYYY-MM`.
- Cost analysis begin/end time and grouping dimension.
- Enterprise project, service type, resource type, region, or resource ID filters when available.
- Permission scope for billing and cost data.

## Read-Only Flow

1. Use `hcloud_billing_readonly.py` to generate official Billing/Cost request specs.
2. For monthly summaries, plan `ShowCustomerMonthlySum` with an explicit billing cycle.
3. For cost analysis, plan `ListCosts` with a bounded time window and grouping dimension.
4. For resource details, plan `ListCustomerselfResourceRecordDetails` or `ListCustomerselfResourceRecords` with cycle and scope filters.
5. Execute the request spec only through API Explorer, Huawei Cloud SDK, or a reviewed signed-request runner after the user approves live billing access.

## Guardrails

- The bundled planner does not sign requests, accept credentials, or send HTTP traffic.
- Billing and cost data can expose account, resource, and spend-sensitive fields.
- Do not infer cost from resource inventory when billing APIs are unavailable.
- Summarize counts, totals, filters, and major drivers before sharing raw records.

## Promotion Gaps

- Add a reviewed signed-request or SDK runner before live billing queries are supported.
- Collect read-only smoke evidence for safe BSS metadata-backed query shapes.
- Document freshness, permission, and enterprise-project scope limits for each supported request type.

