# Script Entry Points

This file contains detailed script usage for `huaweicloud-skill`. Keep `SKILL.md` focused on routing and behavior rules; load this reference only when you need exact command templates or script-specific boundaries.

## Shared Script Helpers

Most command-line scripts use `scripts/hcloud_common.py` for repository paths, registry loading, JSON output, and secret redaction. Keep new scripts on this shared layer unless they have a clear reason to own their own parsing or output path.

`hcloud_safe_exec.py` still exports the redaction helpers for compatibility, but the implementation lives in `hcloud_common.py`. Use `hcloud_common.redact_*` in new code.

## Script Audience Manifest

Use `references/script-audience-manifest.json` during maintenance or upgrade review to decide whether a script is a normal runtime entry point, a guarded-change tool, a runtime supplement, a maintenance/regression utility, an internal library, or a compatibility shim. v0.6 documents these boundaries without physically merging scripts.

Do not treat file count alone as a reason to merge tools. Merge candidates should wait for a separately scoped v0.6.x change when the target wrapper, tests, compatibility behavior, and safety boundaries are clear.

## Context And Metadata

### Context Inspection

```bash
python3 scripts/hcloud_context_inspect.py --pretty
```

Use this first for real cloud tasks. It reports whether `hcloud` exists, active profile hints, configured region/project/domain values, and local metadata cache status. If `hcloud.found=false`, stop real cloud execution and direct the user to install KooCLI from Huawei Cloud's quickstart documentation.

### Environment Doctor

```bash
python3 scripts/hcloud_environment_doctor.py --pretty
```

Use this when the user asks about installation, local setup, credential readiness, Terraform readiness, SDK availability, obsutil setup, or MaaS image generation prerequisites. It is check-only: it does not install packages, modify credentials, write config, run `terraform init/plan/apply`, or call Huawei Cloud APIs.

Mark task-specific requirements so optional tools become blockers only when needed:

```bash
python3 scripts/hcloud_environment_doctor.py \
  --need terraform \
  --need obsutil \
  --pretty
```

The output separates required blockers from optional missing tools and includes copyable install/check commands. Use `hcloud_context_inspect.py` for deeper hcloud metadata details and `hcloud_terraform_context_inspect.py` for deeper Terraform cache/provider details.

### Scenario Router

```bash
python3 scripts/hcloud_scenario_router.py \
  "创建一套 ECS Web 服务，包含 VPC、ELB、监控和成本治理" \
  --pretty
```

Use this before deep execution when the user describes a broad cloud goal. It maps natural language to local playbooks, service guides, planners, SDK supplements, and Terraform candidates. The router also expands compact Chinese service aliases from `references/service-aliases.json`, for example `云耀云` -> `FLEXUS-L` and `云监控` -> `CES`. The router is local and planner-only: it does not install official skills, execute hcloud, call SDK APIs, or create Terraform files.

You can pass a service/category hint when the user's wording is short:

```bash
python3 scripts/hcloud_scenario_router.py \
  "公网入口和安全组检查" \
  --category network \
  --service VPC \
  --pretty
```

### Cache Prewarm

```bash
python3 scripts/hcloud_prewarm_cache.py --pretty
```

Use when the agent will run several Huawei Cloud tasks in a row. It attempts to download offline metadata packages and prewarm service/operation help.

### Local Meta Lookup

```bash
python3 scripts/hcloud_meta_lookup.py --service=ECS --pretty
python3 scripts/hcloud_meta_lookup.py \
  --service=ECS \
  --operation=ListFlavors \
  --region=cn-north-4 \
  --pretty
```

Use this to inspect the local KooCLI metadata cache: service presence, operation count, operation detail, endpoint, and region metadata. Operation detail files are parsed as JSON first; YAML parsing is attempted only when PyYAML is available.

### SDK Supplement Metadata

```bash
python3 scripts/hcloud_sdk_catalog.py --service ECS --operation ListFlavors --pretty
```

Use this only as an hcloud supplement. Runtime discovery prefers installed `huaweicloudsdk*` Python packages such as `huaweicloudsdkecs`. The optional `--sdk-root` points to a `huaweicloud-sdk-python-v3` source tree for maintenance and tests; user machines are not expected to have that source tree.

The script reads SDK client/request/region files to expose method, resource path, query/path parameters, request types, sensitive fields, and static region examples. It does not execute cloud calls.

### SDK Supplement Registry Audit

```bash
python3 scripts/hcloud_sdk_supplement_audit.py --pretty
```

Use this during maintenance before adding or changing any SDK supplement entry. It checks `references/sdk-supplement-registry.json` for hcloud-first boundaries, fallback runner existence, low-risk executable entries, and optional SDK metadata consistency. Add `--require-metadata` only on machines with installed SDK packages or the maintenance source tree available.

### Terraform Asset Routing

```bash
python3 scripts/hcloud_terraform_context_inspect.py --pretty
```

Use this before generating or applying Terraform. It reports Terraform CLI availability, hcloud availability, redacted Terraform/Huawei Cloud environment variable status, local provider cache hints, catalog presence, and forbidden runtime artifacts such as `.terraform/`, `terraform.tfstate*`, real `*.tfvars`, and `crash.log`.

```bash
python3 scripts/hcloud_terraform_router.py \
  "用 Terraform 创建一套 ECS 和 EIP 测试环境" \
  --pretty
```

Use this when the user explicitly asks for Terraform/IaC, environment replication, import/drift review, or long-term resource management. The router selects a small set of examples and references from `references/terraform/catalog/` and `examples/terraform/`; it does not run `terraform`, create files, call hcloud, or apply changes. If the query is only readback, status checking, or troubleshooting without IaC intent, the router returns `recommended_runtime=hcloud`.

```bash
python3 scripts/hcloud_terraform_catalog.py --write --pretty
```

Use this during maintenance after changing `examples/terraform/` or `references/terraform/`. It rebuilds `terraform-example-catalog.json` and `terraform-reference-catalog.json`. Do not manually edit generated catalog JSON unless you are fixing a temporary local experiment.

```bash
python3 scripts/hcloud_terraform_provider_inventory.py --write --pretty
python3 scripts/hcloud_terraform_provider_inventory.py --fail-on-drift --pretty
python3 scripts/hcloud_terraform_provider_inventory.py \
  --signal-kind resources \
  --signal-name rds_instance \
  --pretty
```

Use this during maintenance after updating the local `reference-projects/terraform-provider-huaweicloud` checkout. It rebuilds provider resource/data-source inventories from `docs/resources` and `docs/data-sources`, records the local changelog snapshot, and detects inventory drift. `--signal-kind/--signal-name` reads the provider Markdown for one resource or data source and returns docs-first ForceNew, Import, and sensitive-field hints. These inventories and signals are review aids only; they do not grant execution permission and must not run `terraform import` or `terraform apply`.

### Terraform Workflow Reference

Terraform is documented in `references/terraform-workflow.md` and indexed in `references/terraform/README.md`, not exposed as a generic SDK runner. Read it when the user explicitly wants repeatable IaC, environment replication, import/drift review, or long-term resource management. The workflow requires hcloud discovery before plan generation and hcloud verification after apply.

### Catalog Audit And Rebuild

Generated catalog is a compressed skill-owned catalog built from hcloud `metaRepo`. It is committed inside this skill as the lightweight `hcloud-service-catalog.index.json` plus per-service files under `hcloud-service-catalog/`, and must not depend on `huaweicloud-data` or a source metaRepo at runtime. The full `hcloud-service-catalog.generated.json` is no longer committed; generate it only as a temporary local artifact when a full operation-level diff is required.

As of v0.3.1, catalog generation merges `apis_en.json` and `apis_cn.json` at operation level. English metadata remains preferred for stable existing entries; Chinese metadata fills missing services, operations, and detail files. The current committed catalog source reports 198 local metadata services and 15,666 operations; use `hcloud_catalog_audit.py` as the current fact source rather than hard-coding these numbers elsewhere.

Do not read a full generated catalog directly in an agent run. Access catalog data through scripts such as `hcloud_catalog_audit.py`, `hcloud_resource_discovery.py`, `hcloud_resource_query.py`, or `hcloud_service_change_plan.py`.

```bash
python3 scripts/hcloud_catalog_audit.py --pretty
```

Use this to check registry drift, read generated catalog counts, read curated registry operation counts, and list metadata-backed services outside the curated registry. Treat its `catalog`, `registry`, and `metadata_backed` fields as the documentation fact source for coverage summaries.

```bash
python3 scripts/hcloud_catalog_diff.py \
  --old <old-catalog-or-fingerprint-json> \
  --new <new-catalog-or-fingerprint-json> \
  --pretty
```

Use this during hcloud metadata upgrades to review added/removed services, added/removed operations, and required business parameter changes without manually reading a large generated catalog. Compact fingerprints produce hash-level service changes and are the default review artifact. Full catalogs produce operation-level details only when you temporarily generate them with `build_hcloud_catalog.py --output`; do not commit that output, and do not pass the lazy index to this script.

When rebuilding the catalog from a prepared metaRepo:

```bash
python3 scripts/build_hcloud_catalog.py \
  --source-meta-repo <path-to-hcloud-metaRepo> \
  --fingerprint-output <catalog-fingerprint-json> \
  --index-output <catalog-index-json> \
  --service-output-dir <per-service-catalog-dir>
```

Add `--output <temporary-full-catalog-json>` only when you need a local full catalog for operation-level diff review. `hcloud-service-catalog.fingerprint.json` is the committed review aid. `hcloud-service-confidence.json` stores human/live evidence such as smoke confidence, dry-run support, and operation-level CLI shape exceptions such as unsupported optional args.

## Safe Execution

### Safe hcloud Wrapper

```bash
python3 scripts/hcloud_safe_exec.py \
  --service ECS \
  --operation ListFlavors \
  --arg=--cli-region=cn-north-4 \
  --arg=--project_id=example-project-id \
  --arg=--limit=20 \
  --expect-json \
  --pretty
```

Use this for real `hcloud` calls instead of raw shell execution when possible. It redacts sensitive command/stdout/stderr/JSON fields, parses JSON, classifies common errors, and returns `error_details` for auth, region/project, permission, quota, parameter, not found, and network failures.

For permission failures, `error_details.permission_hint` may include best-effort action hints from `references/iam-actions-catalog.json`. Treat those hints as a review checklist: exact IAM policy syntax, enterprise-project scope, agency trust, service enablement, SCP/custom deny rules, and tenant-side role design still need verification before asking the user to change permissions.

For KooCLI system commands:

```bash
python3 scripts/hcloud_safe_exec.py \
  --command-part=configure \
  --command-part=show \
  --expect-json \
  --pretty
```

## Read-Only Query Paths

### Resource Discovery

```bash
python3 scripts/hcloud_resource_discovery.py \
  --service ECS \
  --operation ListServersDetails \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --limit=50 \
  --pretty
```

Use for list/count style discovery. Curated registry services use registered query operations. Registry-outside services use generated catalog metadata and only auto-select read-only discovery operations without required business parameters. `--execute` is required for real cloud queries.

### SDK Read-Only Bridge

```bash
python3 scripts/hcloud_sdk_readonly.py \
  --service ECS \
  --operation ListFlavors \
  --region=cn-north-4 \
  --pretty
```

Use this only for curated, stable SDK read-only operations where SDK request models make the hcloud path easier to validate. It defaults to plan mode and includes the equivalent hcloud fallback plan. `--execute` imports the installed SDK package and calls the SDK only when the operation is allowlisted. Do not use this as a generic SDK mutation runner.

### Account Inventory

```bash
python3 scripts/hcloud_account_inventory.py \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --limit=50 \
  --pretty
```

Use this for a read-only account inventory plan across core services such as ECS, VPC, EIP, ELB, EVS, NAT, RDS, CCE, CDN, DNS, SCM, and OBS. Default mode only builds commands. Add `--execute` only after read-only collection is approved.

Use repeated `--region` or `--region-file` for cross-region reviews, and `--enterprise-project-id` when the tenant needs EPS-scoped inventory. EPS is appended only when the operation metadata supports `enterprise_project_id`; unsupported operations keep the scope visible instead of pretending it was applied.

```bash
python3 scripts/hcloud_account_inventory.py \
  --service EIP \
  --service EVS \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --execute \
  --pretty
```

Save executed JSON output when you need follow-up idle-resource analysis.

`hcloud_idle_audit.py` preserves region, project, enterprise-project, and tag dimensions from inventory output so idle candidates can be reviewed by owner/scope before any release, delete, stop, or downsize discussion.

### Idle Candidate Audit

```bash
python3 scripts/hcloud_idle_audit.py \
  --inventory-json-file <saved-inventory-output.json> \
  --pretty
```

Use this to analyze saved read-only JSON and identify review candidates such as unbound EIPs, unattached EVS volumes, stopped/abnormal ECS instances, unhealthy ELB resources, and RDS/NAT lifecycle review targets. The script does not generate delete, release, unsubscribe, stop, or resize commands; candidates require owner, tag, metric, backup, dependency, and billing checks before any action.

You can also pass service-specific query output directly:

```bash
python3 scripts/hcloud_idle_audit.py \
  --input-json-file EIP=<list-publicips-result.json> \
  --input-json-file EVS=<list-volumes-result.json> \
  --pretty
```

### Teardown Review Plan

```bash
python3 scripts/hcloud_teardown_plan.py \
  --idle-audit-json-file <saved-idle-audit-output.json> \
  --pretty
```

Use this after idle audit to produce a dependency-aware teardown review checklist. It is planner-only: every step has `executable=false` and `submit_command=null`. Build mutating commands only after fresh read-only evidence and explicit approval for each exact resource action.

### Observability Readiness Plan

```bash
python3 scripts/hcloud_observability_plan.py \
  --service ECS \
  --target-id <server-id> \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

Use this before declaring a resource healthy or idle based on partial evidence. It builds a service-specific resource state check when a target ID is provided, plus a CES `ListMetrics` discovery plan. The planner intentionally does not assume exact namespace, metric names, or dimensions; discover them first, then choose the time range and period.

`--execute` runs only approved read-only state and metric discovery commands. Alarm creation or notification-policy changes are not in this planner.

### CES Datapoint Planner

```bash
python3 scripts/hcloud_ces_datapoint_plan.py \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --namespace SYS.ECS \
  --metric-name cpu_util \
  --dimension instance_id=<server-id> \
  --period 300 \
  --lookback-minutes 30 \
  --pretty
```

Use this after `ListMetrics` to build or run a bounded `BatchListMetricData` read-only query for one CES metric. The planner validates required namespace, metric name, dimensions, project/region, period, and the official batch window rule `metric_count * ((to - from) / 1000) / period <= 3000`.

Add `--execute` only when the user approves a real read-only metric query. The output summarizes safe_exec status and datapoint counts; it does not return raw datapoints. Use `--result-json-file <safe_exec-result.json>` to interpret a saved result and distinguish `datapoints_present`, `empty_datapoints`, `empty_metric_result`, and likely Agent/namespace/period/dimension causes.

### CES Alarm Planner

```bash
python3 scripts/hcloud_ces_alarm_plan.py \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --alarm-name cpu-high \
  --namespace SYS.ECS \
  --metric-name cpu_util \
  --dimension instance_id=<server-id> \
  --threshold 80 \
  --pretty
```

Use this to discover CES metrics and existing alarm rules, then draft an alarm rule spec. The result includes `metric_guidance` from `references/observability/ces-ecs-metric-guidance.json`, including SYS.ECS vs AGT.ECS, minimum period, Agent requirement, canonical metric-name hints, and known caveats. The result is planner-only: it does not create or update CES alarms.

### LTS Read-Only Logs

```bash
python3 scripts/hcloud_lts_readonly.py \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --log-group-id <group-id> \
  --log-stream-id <stream-id> \
  --start-time <start> \
  --end-time <end> \
  --keyword ERROR \
  --pretty
```

Use this to discover LTS log groups/streams and build bounded read-only log queries. Logs may contain sensitive application data; keep time ranges and keywords narrow and summarize results.

### Billing And Cost Capability Probe

```bash
python3 scripts/hcloud_billing_cost_probe.py --pretty
```

Use this as a local feasibility spike before promising billing or cost analysis. It inspects the bundled catalog and curated registry for direct BSS/Billing/Cost-style service support and separates direct service matches from weak keyword operation matches. It does not call live billing APIs and does not access invoice, order, payment, subscription, or spend data.

In v0.3.1, the generated catalog can discover `BSS` from merged local metadata. Treat that as a metadata-backed candidate only: live billing queries still require curated registry coverage, reviewed read-only smoke evidence, and an approved execution path. If no direct billing/cost service is present, treat Billing/Cost as unsupported in the current skill version and research official Huawei Cloud docs before adding any live probe.

### Billing And Cost Read-Only Request Planner

```bash
python3 scripts/hcloud_billing_readonly.py \
  --entry-point monthly_spend \
  --operation monthly-sum \
  --bill-cycle 2026-05 \
  --service-type-code hws.service.type.ec2 \
  --pretty
```

```bash
python3 scripts/hcloud_billing_readonly.py \
  --entry-point monthly_spend \
  --operation cost-data \
  --begin-time 2026-05-01 \
  --end-time 2026-05-31 \
  --group-by CLOUD_SERVICE_TYPE \
  --pretty
```

```bash
python3 scripts/hcloud_billing_readonly.py \
  --entry-point reconciliation \
  --operation billing-statements \
  --bill-cycle 2026-05 \
  --pretty
```

```bash
python3 scripts/hcloud_billing_readonly.py \
  --entry-point entitlement_and_deduction \
  --operation free-resource-usages \
  --free-resource-id <free_resource_id> \
  --pretty
```

```bash
python3 scripts/hcloud_billing_readonly.py \
  --entry-point charge_attribution \
  --operation usage-summary \
  --bill-cycle 2026-05 \
  --service-type-code hws.service.type.vpc \
  --resource-type hws.resource.type.bandwidth \
  --usage-type 95Peak \
  --limit 10 \
  --pretty
```

```bash
python3 scripts/hcloud_billing_readonly.py \
  --entry-point pricing_inquiry \
  --operation on-demand-pricing \
  --project-id <project_id> \
  --pricing-preset ecs \
  --resource-spec s6.small.1 \
  --pricing-region cn-north-4 \
  --pretty
```

```bash
python3 scripts/hcloud_billing_readonly.py \
  --entry-point pricing_inquiry \
  --operation period-pricing \
  --project-id <project_id> \
  --pricing-preset evs \
  --resource-spec GPSSD \
  --resource-size 100 \
  --size-measure-id 17 \
  --period-type month \
  --period-num 1 \
  --pretty
```

Use this to build a planner-only request spec and a reviewed `hcloud_command_plan.safe_exec_command` for official Huawei Cloud Billing/Cost APIs such as balance/debt, monthly bill summary, cost analysis, billing statements, resource records, usage summaries/details, pricing inquiry, resource packages, coupon ledgers, order evidence, enterprise/sub-customer scope, partner ledgers, and reference dimensions. `--entry-point` attaches the local billing semantic catalog from `references/billing/semantic-catalog.json`, including scope/time/money basis, ontology entities, source operations, and currently supported planner operations. BSS hcloud command plans always fix `--cli-region=cn-north-1` and pass language as `--X-Language=zh_CN` or `--X-Language=en_US`; do not replace the BSS region with the user's normal project region.

The script does not sign requests, accept credentials, send HTTP traffic, or execute hcloud by default. Run the generated safe_exec command only after the user confirms account scope, time range, enterprise project scope, permission boundary, and raw-output handling. Treat `pagination_scope.complete_result_claim_allowed=false` as a hard reminder that one page cannot support full-account conclusions. For enterprise-project ranking, use `operation=cost-data` with `--filter ENTERPRISE_PROJECT_ID=<id>`; `ShowCustomerMonthlySum` does not support enterprise-project filtering.

For 95th-percentile usage checks, use `usage-summary` first with `bill_cycle`, `service_type_code`, `resource_type`, and `usage_type`; then use `usage-detail` with the selected `resource_id`. These operations cover CDN/OBS/IEC/VPC-style usage dimensions and should not be mixed with cash bill totals without stating the fact/grain difference.

For pricing inquiry, use `pricing_inquiry` with `on-demand-pricing` or `period-pricing`. These operations produce point-in-time quote request specs for reviewed presets such as `ecs`, `evs`, `eip-bw`, `eip-flow`, `eip-ip`, `obs`, `sfs`, `nat`, `elb`, and `bms`; they are not historical billing evidence, purchase orders, renewal quotes, or proof of actual discounted spend.

### Billing Live Read Wrapper

```bash
python3 scripts/hcloud_billing_live_read.py \
  --entry-point monthly_spend \
  --operation monthly-sum \
  --bill-cycle 2026-05 \
  --limit 10 \
  --pretty
```

Use this to turn a reviewed Billing/BSS request plan into a guarded live read workflow. By default it only returns the plan and the reviewed `hcloud_safe_exec.py` command. To execute, the user must explicitly confirm the sensitive read:

```bash
python3 scripts/hcloud_billing_live_read.py \
  --entry-point monthly_spend \
  --operation monthly-sum \
  --bill-cycle 2026-05 \
  --limit 10 \
  --execute \
  --confirm-live-billing-read READ_BILLING_DATA \
  --pretty
```

The wrapper only allows reviewed BSS `List*` and `Show*` operations from `hcloud_billing_readonly.py`, keeps `--cli-region=cn-north-1`, passes language through `--X-Language`, rejects pages larger than 50 rows, and returns a redacted billing summary instead of the raw safe_exec result. Use `--include-redacted-records` only when row-level evidence is necessary; raw identifiers still remain hashed.

### Billing Operation Gap Audit

```bash
python3 scripts/hcloud_billing_operation_gap.py --pretty
```

Use this during skill maintenance to compare local `hcloud_billing_readonly.py` coverage with official `huaweicloud-skills-by-huawei` billing-scout and business-support-query references. The audit is local-only: it reads markdown and script filenames, reports supported operations, P1/P2 missing operations, pricing API gaps, and enhanced pricing helper references, but does not run `hcloud`, read credentials, or query billing data.

### Billing Result Summarizer

```bash
python3 scripts/hcloud_billing_result_summarize.py \
  --json-file <saved-safe-exec-result.json> \
  --offset 0 \
  --limit 10 \
  --pretty
```

Use this after an approved BSS safe_exec read. The summarizer accepts either a full `hcloud_safe_exec.py` result JSON or a direct BSS payload. By default it returns only field/record counts, money-field presence, pagination completeness, and redaction metadata. Add `--include-redacted-records` only when row-level evidence is needed; protected identifiers such as account/customer/resource/order/coupon IDs are replaced with stable hash markers.

### Explicit Resource Query

```bash
python3 scripts/hcloud_resource_query.py \
  --service EIP \
  --operation ShowPublicip \
  --param publicip_id=<publicip-id> \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

Use when a read operation needs explicit target parameters. Do not guess resource IDs. Sensitive reads such as `ShowServerPassword` and certificate private-key reads are blocked unless `--allow-sensitive-read` is explicit.

### OBS Read-Only Adapter

```bash
python3 scripts/hcloud_obs_readonly.py \
  --operation ListBuckets \
  --limit=20 \
  --pretty
```

Use OBS through `hcloud obs`/obsutil rather than ordinary OpenAPI-style `hcloud OBS Operation` commands. Bucket-level operations require `--bucket`, for example `--bucket obs://example-bucket`.

### Service Readiness

```bash
python3 scripts/hcloud_service_readiness.py \
  --service VPC \
  --service ELB \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

Use to run or plan per-service read-only readiness checks. Target-specific checks are skipped when required IDs are missing. `--execute` is required for live queries.

### Live Validation Plan

```bash
python3 scripts/hcloud_live_validation_plan.py \
  --service ECS \
  --service VPC \
  --service EIP \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --param server_id=<server-id> \
  --param publicip_id=<publicip-id> \
  --param probe_url=https://example.com/health \
  --pretty
```

Use this before true-account regression or curated-service promotion work. It reads `references/live-validation-profiles.json` for the high-frequency services ECS, VPC, EIP, OBS, ELB, and RDS, then composes existing `hcloud_service_readiness.py` readback plans with service-specific acceptance evidence, probe candidates, and promotion gates. The script is planner-only: it does not execute hcloud, run network probes, mutate cloud resources, import Terraform state, or read secrets. Real collection still goes through `hcloud_service_readiness.py --execute` and `hcloud_acceptance_closure.py` after review.

### Closure Plan

```bash
python3 scripts/hcloud_closure_plan.py \
  --tier lifecycle \
  --service VPC \
  --param security_group_id=<sg-id> \
  --param direction=ingress \
  --param protocol=tcp \
  --param remote_ip_prefix=<approved-cidr> \
  --param port_range_min=443 \
  --param port_range_max=443 \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

```bash
python3 scripts/hcloud_closure_plan.py \
  --tier governance \
  --service Billing \
  --param bill_cycle=<yyyy-mm> \
  --pretty
```

```bash
python3 scripts/hcloud_closure_plan.py \
  --tier scenario \
  --group CCE \
  --param cluster_id=<cluster-id> \
  --pretty
```

Use this as the default closure-planning entry. It wraps P0 lifecycle, P1 governance, and P2 scenario closure planners without changing their safety gates. The tier-specific scripts remain compatibility modules for existing workflows and focused tests.

### Lifecycle Closure Plan Compatibility

```bash
python3 scripts/hcloud_lifecycle_closure_plan.py \
  --service VPC \
  --param security_group_id=<sg-id> \
  --param direction=ingress \
  --param protocol=tcp \
  --param remote_ip_prefix=<approved-cidr> \
  --param port_range_min=443 \
  --param port_range_max=443 \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

Use this when the user asks for a task-level closure plan rather than a single low-level command. v0.3.2 covers the P0 closure set: VPC/security group, EIP, EVS, ELB, RDS, OBS, DNS, SCM, CDN, and CES/LTS. Without `--service`, it generates closure profiles for all P0 services. The planner returns six stages: context/dependency discovery, operation/parameter planning, risk/security gates, controlled execution/error handling, post-change verification, and governance/audit follow-up.

The script is planner-only. It composes `hcloud_service_change_plan.py`, `hcloud_service_readiness.py`, OBS/LTS adapters, and local policy checks, but it does not execute hcloud calls or submit changes. Unsafe VPC ingress such as `0.0.0.0/0` on SSH/Web ports is hard-blocked before any submit path exists. EVS output separates cloud-side `ShowVolume` evidence from guest filesystem/mount/read-write readiness. ELB output keeps listener/pool/member creation separate from backend health and protocol probes. RDS adds backup/configuration/connection evidence, OBS routes through obsutil-style planning, DNS/SCM/CDN add propagation/certificate/origin verification, and CES/LTS keeps health evidence read-only. The `post_change_verification` stage includes an `acceptance_evidence_plan` with service-specific evidence items and missing-input status; it plans acceptance evidence but does not run live probes.

### Acceptance Closure

```bash
python3 scripts/hcloud_acceptance_closure.py plan \
  --plan-file=<lifecycle-plan.json> \
  --pretty
```

```bash
python3 scripts/hcloud_acceptance_closure.py run \
  --probe-plan-file=<probe-plan.json> \
  --value probe_url=https://example.com \
  --execute \
  --pretty
```

Private tenant paths require an explicit target confirmation:

```bash
python3 scripts/hcloud_acceptance_closure.py run \
  --probe-plan-file=<probe-plan.json> \
  --value host=10.0.1.25 \
  --value port=8080 \
  --execute \
  --allow-private-targets \
  --pretty
```

```bash
python3 scripts/hcloud_acceptance_closure.py evaluate \
  --plan-file=<lifecycle-plan.json> \
  --evidence-file=<local-evidence-status.json> \
  --pretty
```

```bash
python3 scripts/hcloud_acceptance_closure.py chain \
  --plan-file=<lifecycle-plan.json> \
  --value probe_url=https://example.com \
  --pretty
```

Use this after lifecycle closure planning. The `plan` subcommand turns `acceptance_evidence_plan` items into probe templates, `run` prepares or runs only supported HTTP/TCP/DNS/TLS probes, `evaluate` reads local evidence status JSON, and `chain` composes the three stages. Without `--execute`, `run` and `chain` only report prepared probes and missing evidence. Metadata and link-local targets such as `169.254.169.254` are blocked even when a placeholder value renders them. Private, loopback, or `.local` targets require `--allow-private-targets` after the user confirms the target belongs to the tenant acceptance path. The compatibility entry points `hcloud_acceptance_probe_plan.py`, `hcloud_acceptance_probe_run.py`, and `hcloud_acceptance_evidence_result.py` remain available for focused workflows and tests, but new user-facing flows should prefer this unified command.

### Governance Closure Plan Compatibility

```bash
python3 scripts/hcloud_governance_closure_plan.py \
  --service Billing \
  --param bill_cycle=<yyyy-mm> \
  --param begin_time=<yyyy-mm-dd> \
  --param end_time=<yyyy-mm-dd> \
  --pretty
```

Use this when the user asks for a P1 governance closure plan instead of a single governance command. The default service set is TMS, CTS, CBR, RMS/Config, Billing/BSS, WAF, DLI, and CodeArtsRepo. The planner returns five stages: governance scope, read-only evidence, risk/privacy gate, review plan, and promotion readiness. The read-only evidence stage includes generated evidence command plans for supported non-billing services and missing target-parameter gaps for target-scoped queries.

The script is planner-only and does not execute `hcloud`, sign Billing/Cost requests, write tags, update trackers, change backup policies, modify WAF rules, execute DLI workloads, or mutate repositories. Billing/BSS output reuses `hcloud_billing_readonly.py` request specs and reviewed hcloud command plans while keeping credentials outside the planner. Promotion readiness reuses `hcloud_curated_promotion_audit.py` so each P1 service shows live-smoke and profile gaps before curated promotion.

### P2 Scenario Closure Plan Compatibility

```bash
python3 scripts/hcloud_p2_scenario_closure_plan.py \
  --group CCE \
  --param cluster_id=<cluster-id> \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

Use this when the user asks to continue P2 scenario closure after the P0/P1 lifecycle and governance planners. Without `--group`, it plans all P2 groups: CCE, NAT, DCS, RFS, UCS, IAM/KPS/IMS dependencies, security posture, and database family. The planner returns four stages: scenario scope, read-only evidence, risk boundary, and next closure steps.

The script is planner-only and does not execute `hcloud` or submit cluster, NAT, cache, stack, fleet, security, key, IAM, or database changes. Curated-profile services generate discovery and target-scoped read-only command plans when enough parameters exist. Security posture services (`HSS`, `SecMaster`, `CFW`, `DBSS`, `KMS`) and database-family services (`GaussDB`, `GaussDBforNoSQL`, `GaussDBforopenGauss`, `DDS`, `DDM`, `DWS`) stay metadata-backed evidence-gap plans in this release; that status is intentional and must not be described as curated maturity.

### Closure Maturity Audit

```bash
python3 scripts/hcloud_closure_maturity_audit.py --pretty
```

Use this before status reports or promotion planning to summarize current closure maturity tiers. The audit is local and planner-only: it reports ECS as the current end-to-end sample, P0 as task-level planner maturity with `acceptance_evidence_plan`, P1/P2 as planner-only, and metadata-backed services as evidence gaps until smoke, playbooks, risk profiles, and verifiers are complete. It does not execute `hcloud`, call SDK APIs, or inspect Terraform state.

### Registry Read-Only Smoke

```bash
python3 scripts/hcloud_readonly_smoke.py \
  --service EIP \
  --service VPC \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

Use for a small multi-service read-only smoke plan. Live failures are not treated as script failures by default; add `--strict` for strict failure behavior.

### Metadata-Backed Read-Only Smoke

```bash
python3 scripts/hcloud_catalog_readonly_smoke.py \
  --service UCS \
  --service RFS \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --output tests/fixtures/hcloud-catalog-readonly-smoke-plan.json \
  --pretty
```

Use for registry-outside metadata-backed smoke. Default mode only builds a matrix. `--execute` performs live read-only queries and buckets results into command shape, auth/permission, service subscription, region/endpoint, missing parameter, network, or unknown cloud error. Default stdout contains execution summaries, not raw response bodies. `--include-raw-execution` is only for local debugging. `--output` writes a sanitized evidence record that intentionally omits raw stdout, stderr, and parsed response bodies. `--confidence-output` writes only suggested `live-read-smoked` confidence entries for successful executed operations; review those suggestions before merging them into `hcloud-service-confidence.json`. Do not store AK/SK, tokens, or full sensitive responses in smoke records.

```bash
python3 scripts/hcloud_catalog_smoke_candidates.py \
  --limit 12 \
  --operations-per-service 2 \
  --pretty
```

Use this before expanding the metadata-backed live smoke matrix. It combines generated question frequency, generated catalog discovery operations, curated-registry exclusion, and existing `live-read-smoked` confidence entries to suggest the next services and read-only operations to test.

When you already have a review-approved candidate pool, restrict the selector instead of scanning the full catalog:

```bash
python3 scripts/hcloud_catalog_smoke_candidates.py \
  --service CBR \
  --service DLI \
  --service ModelArts \
  --service CodeArtsRepo \
  --limit 8 \
  --pretty
```

### Curated Promotion Audit

```bash
python3 scripts/hcloud_curated_promotion_audit.py \
  --service DCS \
  --service RFS \
  --service UCS \
  --service WAF \
  --service CodeArtsRepo \
  --service DLI \
  --service CTS \
  --service TMS \
  --service CBR \
  --service RMS \
  --service Config \
  --service LTS \
  --min-live-ops 2 \
  --include-curated \
  --pretty
```

Use this before promoting metadata-backed services into `references/service-registry.json`. The audit checks the medium-coverage gate: enough `live-read-smoked` read operations, at least one target-scoped read candidate, at least one readiness discovery candidate, a complete `references/service-curation-profiles.json` candidate entry, existing playbook files, and complete risk-profile fields. A blocked result means the service should stay metadata-backed until the missing items are completed.

Add `--include-curated` to audit the existing curated registry services for profile, playbook, and risk-profile completeness. This does not execute hcloud calls; it is a local maintenance gate.

The audit also returns `value_ranked_candidates`, which scores candidates by promotion readiness and tenant-goal fit across 上好云、用好云、管好云. Use this ranking to choose the next grooming target; do not treat a high value score as permission to bypass missing evidence or playbooks.

## Change Planning And Guarded Flows

### Generic Change Plan

```bash
python3 scripts/hcloud_change_plan.py \
  --service ECS \
  --operation CreateServers \
  --region=cn-north-4 \
  --json-input-file=<path-to-json> \
  --pretty
```

Use for a non-executing risk plan for mutating operations. It classifies operation risk, applies security-group ingress policy checks, generates plan/dry-run and submit commands, and records confirmation/verification requirements. Optional `--metadata-category` applies catalog category risk floors for metadata-backed services.

### Service-Aware Change Plan

```bash
python3 scripts/hcloud_service_change_plan.py \
  --service EIP \
  --operation CreatePublicip \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

Use for planner-only changes across curated services and catalog-backed mutating operations. Registry-outside mutations are metadata-backed, planning-only, and never auto-submitted. Their dry-run state defaults to `unknown`; unless `hcloud-service-confidence.json` marks an operation as supported, the planner does not add `--dryrun`.

Metadata category risk floors are applied here. Security/compliance and identity/key/governance services can set `risk.hard_guard=true`; generic guarded flows must not execute submit for those plans.

### Generic Guarded Change Flow

```bash
python3 scripts/hcloud_guarded_change_flow.py \
  --service VPC \
  --operation CreateSecurityGroupRule \
  --verify-param security_group_rule_id=<rule-id> \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

Use for non-ECS ordinary services with service-aware risk planning, optional dry-run execution, guarded submit, resource-level verification, and post-change read-only readiness. `--execute-submit` must be paired with `--confirm-submit`; medium/high risk also requires a successful dry-run or explicit `--skip-dryrun`. If `risk.hard_guard=true`, submit execution is blocked even with confirmation.

This does not replace dedicated planners. EIP uses `hcloud_eip_change_flow.py`, OBS uses `hcloud_obs_change_plan.py`, and ECS creation uses ECS-specific scripts.

### EIP Guarded Flow

```bash
python3 scripts/hcloud_eip_change_flow.py \
  --operation UpdatePublicip \
  --publicip-id=<publicip-id> \
  --arg=--publicip_id=<publicip-id> \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

Use for EIP Plan -> dry-run -> guarded submit -> ShowPublicip verification. Default mode only builds the plan and verification plan. Real submit requires explicit confirmation for the exact operation.

### OBS Change Plan

```bash
python3 scripts/hcloud_obs_change_plan.py \
  --operation PutBucketLifecycle \
  --bucket=<bucket-name> \
  --local-file=<lifecycle-json-file> \
  --pretty
```

Use for OBS bucket, lifecycle, and policy changes. It produces planner-only commands and read-only verification guidance; it does not execute real bucket changes.

## ECS-Specific Flow

### ECS Create Plan

```bash
python3 scripts/hcloud_ecs_create_plan.py \
  --json-input-file=<path-to-filled-json> \
  --security-group-evidence-file=<list-security-group-rules-or-show-security-group-json> \
  --operation=CreateServers \
  --region=cn-north-4 \
  --pretty
```

Use before ECS creation. It blocks placeholders, missing required fields, unsafe security-group ingress, missing security group rule evidence, and missing login credential choices. When `body.server.security_groups[*].id` references an existing security group, pass readback JSON from VPC `ListSecurityGroupRules` or `ShowSecurityGroup` through `--security-group-evidence-file`; otherwise the plan is not ready to run. Default mode generates a dry-run safe-exec command. To generate a non-dry-run submit command, require:

```bash
python3 scripts/hcloud_ecs_create_plan.py \
  --json-input-file=<path-to-json> \
  --security-group-evidence-file=<list-security-group-rules-or-show-security-group-json> \
  --operation=CreateServers \
  --region=cn-north-4 \
  --mode=submit \
  --confirm-submit \
  --pretty
```

### ECS Job Wait

```bash
python3 scripts/hcloud_ecs_wait_job.py \
  --job-id=<job-id> \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

Use after ECS create/update operations that return `job_id`. It polls `ECS ShowJob` until terminal state. Job success is not enough to declare ECS readiness.

### ECS Active Verification

```bash
python3 scripts/hcloud_ecs_verify_active.py \
  --server-id=<server-id> \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --pretty
```

Use after job success to verify the target ECS exists and reaches `ACTIVE`. Continue with SSH/application readiness when the task requires host-level or protocol-level completion.

## Verification And Regression

### Resource Verify

```bash
python3 scripts/hcloud_resource_verify.py \
  --service EIP \
  --json-file=<safe-exec-result.json> \
  --target-id=<publicip-id> \
  --expect-status BIND_ACTIVE \
  --expect-bound-to=<target-port-or-instance-id> \
  --require-match \
  --pretty
```

Use to validate resources from a safe-exec JSON result or raw service JSON. It does not query the cloud by itself.

### Offline Dataset And Coverage Check

```bash
python3 scripts/check_question_coverage.py --pretty
```

Use for offline regression over generated questions and optional E2E workbook data. It validates schema, CRUD type, read/update/delete risk gates, registry coverage, validation-step execution paths, and question coverage thresholds.

## MaaS Model APIs

Use these helpers when the task explicitly needs Huawei Cloud MaaS large-model APIs. MaaS is an API-first route: it uses `https://api.modelarts-maas.com` and a MaaS API Key from `MAAS_API_KEY` or `MODELARTS_MAAS_API_KEY`; it is not a KooCLI service registry entry.

### Model Catalog

```bash
python3 scripts/maas_models.py --capability text --pretty
python3 scripts/maas_models.py --capability image_generation --pretty
python3 scripts/maas_models.py --online --pretty
```

The first two commands read the local curated catalog. The online form only plans `GET /v2/models`; add `--execute` only after API Key readiness and user confirmation.

### Text Generation And Image Understanding

```bash
python3 scripts/maas_chat.py \
  --prompt "写一段华为云上云方案摘要" \
  --model deepseek-v3.2 \
  --dry-run \
  --pretty
```

```bash
python3 scripts/maas_chat.py \
  --image ./diagram.png \
  --prompt "总结这张架构图中的云资源" \
  --model qwen2.5-vl-72b \
  --dry-run \
  --pretty
```

Use `--endpoint openai-compatible` for `/openai/v1/chat/completions`. Keep `--dry-run` as the first step so the agent can review messages, model, token limits, and image references before sending data.

### Usage Statistics

```bash
python3 scripts/maas_usage_request_plan.py --pretty
```

The default mode builds a dry-run MaaS ShowStatistics request plan for token, request, and error statistics. Use `--execute` only for a confirmed read-only statistics query; it signs the request from local AK/SK environment variables such as `HW_*`, `HUAWEICLOUD_*`, `HUAWEI_*`, or `OS_*`, sends millisecond `start_time`/`end_time` fields, and reports only redacted credential/source metadata plus response summaries.

### Image Generation And Editing

```bash
python3 scripts/maas_image_generation.py \
  --prompt "A clean enterprise cloud dashboard illustration" \
  --file dashboard.webp \
  --out-dir ./generated-assets \
  --model qwen-image \
  --dry-run \
  --pretty
```

For editing, pass one or more `--image` values and choose an edit-capable model such as `qwen_image_edit` or `qwen-image-edit-2509`. Local image inputs are converted to data URIs in the request payload; dry-run output summarizes those data URIs instead of printing base64.

### Video Generation

```bash
python3 scripts/maas_video_generation.py \
  --prompt "A short product video showing a cloud server dashboard" \
  --model Wan2.2-T2V-A14B \
  --duration 5 \
  --dry-run \
  --pretty
```

Video generation is asynchronous. A create call returns a `task_id`; use `--action query --task-id <id>` or `--action wait --task-id <id>` to reach `succeeded` or `failed` before reporting the result. For provider-specific shapes that are not normalized yet, pass the official body through `--body-json-file` after dry-run review.

## MaaS Image Assets

Only use this legacy-compatible path for Huawei Cloud web/static-site deployment tasks that need local image assets through Huawei Cloud ModelArts MaaS. General MaaS image generation and editing should use `scripts/maas_image_generation.py`.

```bash
MAAS_API_KEY=<key> python3 scripts/maas_text_to_image.py \
  --prompt-file <prompts.json> \
  --out-dir <site-assets-dir> \
  --model qwen-image \
  --format webp
```

`scripts/qwen_text_to_image.py` remains a compatibility entry point for existing workflows. API keys are read only from `MAAS_API_KEY` or `MODELARTS_MAAS_API_KEY`; they must not be written to files, logs, site code, or manifests. If MaaS fails, report the Huawei Cloud authentication/quota/service error and do not fall back to non-Huawei image APIs.
