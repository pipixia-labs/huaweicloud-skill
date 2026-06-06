# Script Entry Points

This file contains detailed script usage for `huaweicloud-skill`. Keep `SKILL.md` focused on routing and behavior rules; load this reference only when you need exact command templates or script-specific boundaries.

## Shared Script Helpers

Most command-line scripts use `scripts/hcloud_common.py` for repository paths, registry loading, JSON output, and secret redaction. Keep new scripts on this shared layer unless they have a clear reason to own their own parsing or output path.

`hcloud_safe_exec.py` still exports the redaction helpers for compatibility, but the implementation lives in `hcloud_common.py`. Use `hcloud_common.redact_*` in new code.

## Context And Metadata

### Context Inspection

```bash
python3 scripts/hcloud_context_inspect.py --pretty
```

Use this first for real cloud tasks. It reports whether `hcloud` exists, active profile hints, configured region/project/domain values, and local metadata cache status. If `hcloud.found=false`, stop real cloud execution and direct the user to install KooCLI from Huawei Cloud's quickstart documentation.

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

### Catalog Audit And Rebuild

Generated catalog is a compressed skill-owned catalog built from hcloud `metaRepo`. It is committed inside this skill and must not depend on `huaweicloud-data` or a source metaRepo at runtime. Runtime readers default to the lightweight `hcloud-service-catalog.index.json` plus per-service files under `hcloud-service-catalog/`; the full `hcloud-service-catalog.generated.json` remains for compatibility and full operation-level diffs.

Do not read `references/hcloud-service-catalog.generated.json` directly in an agent run. Access it through scripts such as `hcloud_catalog_audit.py`, `hcloud_resource_discovery.py`, `hcloud_resource_query.py`, or `hcloud_service_change_plan.py`.

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

Use this during hcloud metadata upgrades to review added/removed services, added/removed operations, and required business parameter changes without manually reading the large generated catalog. Full catalogs produce operation-level details; compact fingerprints produce hash-level service changes. Do not pass the lazy index to this script; compare `hcloud-service-catalog.generated.json` or `hcloud-service-catalog.fingerprint.json`.

When rebuilding the catalog from a prepared metaRepo:

```bash
python3 scripts/build_hcloud_catalog.py \
  --source-meta-repo <path-to-hcloud-metaRepo> \
  --output <catalog-output-json> \
  --fingerprint-output <catalog-fingerprint-json> \
  --index-output <catalog-index-json> \
  --service-output-dir <per-service-catalog-dir>
```

`hcloud-service-catalog.fingerprint.json` is a review aid. `hcloud-service-confidence.json` stores human/live evidence such as smoke confidence, dry-run support, and operation-level CLI shape exceptions such as unsupported optional args.

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

### Account Inventory

```bash
python3 scripts/hcloud_account_inventory.py \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --limit=50 \
  --pretty
```

Use this for a read-only account inventory plan across core services such as ECS, VPC, EIP, ELB, EVS, NAT, RDS, CCE, CDN, DNS, SCM, and OBS. Default mode only builds commands. Add `--execute` only after read-only collection is approved.

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

Use this to discover CES metrics and existing alarm rules, then draft an alarm rule spec. The result is planner-only: it does not create or update CES alarms.

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

If no direct billing/cost service is present, treat Billing/Cost as unsupported in the current skill version and research official Huawei Cloud docs before adding any live probe.

### Billing And Cost Read-Only Request Planner

```bash
python3 scripts/hcloud_billing_readonly.py \
  --operation monthly-sum \
  --bill-cycle 2026-05 \
  --service-type-code hws.service.type.ec2 \
  --pretty
```

```bash
python3 scripts/hcloud_billing_readonly.py \
  --operation cost-data \
  --begin-time 2026-05-01 \
  --end-time 2026-05-31 \
  --group-by CLOUD_SERVICE_TYPE \
  --pretty
```

Use this to build a planner-only request spec for official Huawei Cloud Billing/Cost APIs such as monthly bill summary, cost analysis, and resource records. The script does not sign requests, accept credentials, or send HTTP traffic. Execute the generated spec only through a reviewed signed-request runner, Huawei Cloud SDK, or API Explorer after the user confirms account scope, time range, enterprise project scope, and permission boundary.

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
  --operation=CreateServers \
  --region=cn-north-4 \
  --pretty
```

Use before ECS creation. It blocks placeholders, missing required fields, unsafe security-group ingress, and missing login credential choices. Default mode generates a dry-run safe-exec command. To generate a non-dry-run submit command, require:

```bash
python3 scripts/hcloud_ecs_create_plan.py \
  --json-input-file=<path-to-json> \
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

## MaaS Image Assets

Only use this for Huawei Cloud web/static-site deployment tasks that need local image assets through Huawei Cloud ModelArts MaaS. Do not use it as a generic image-generation entry point.

```bash
MAAS_API_KEY=<key> python3 scripts/maas_text_to_image.py \
  --prompt-file <prompts.json> \
  --out-dir <site-assets-dir> \
  --model qwen-image \
  --format webp
```

`scripts/qwen_text_to_image.py` remains a compatibility entry point for existing workflows. API keys are read only from `MAAS_API_KEY` or `MODELARTS_MAAS_API_KEY`; they must not be written to files, logs, site code, or manifests. If MaaS fails, report the Huawei Cloud authentication/quota/service error and do not fall back to non-Huawei image APIs.
