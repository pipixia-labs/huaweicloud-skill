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

Generated catalog is a compressed skill-owned catalog built from hcloud `metaRepo`. It is committed inside this skill and must not depend on `huaweicloud-data` or a source metaRepo at runtime.

Do not read `references/hcloud-service-catalog.generated.json` directly in an agent run. Access it through scripts such as `hcloud_catalog_audit.py`, `hcloud_resource_discovery.py`, `hcloud_resource_query.py`, or `hcloud_service_change_plan.py`.

```bash
python3 scripts/hcloud_catalog_audit.py --pretty
```

Use this to check registry drift, read generated catalog counts, read curated registry operation counts, and list metadata-backed services outside the curated registry. Treat its `catalog`, `registry`, and `metadata_backed` fields as the documentation fact source for coverage summaries.

When rebuilding the catalog from a prepared metaRepo:

```bash
python3 scripts/build_hcloud_catalog.py \
  --source-meta-repo <path-to-hcloud-metaRepo> \
  --output <catalog-output-json> \
  --fingerprint-output <catalog-fingerprint-json>
```

`hcloud-service-catalog.fingerprint.json` is a review aid. `hcloud-service-confidence.json` stores human/live evidence such as smoke confidence and dry-run support.

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
MAAS_API_KEY=<key> python3 scripts/qwen_text_to_image.py \
  --prompt-file <prompts.json> \
  --out-dir <site-assets-dir> \
  --model qwen-image \
  --format webp
```

API keys are read only from `MAAS_API_KEY` or `MODELARTS_MAAS_API_KEY`; they must not be written to files, logs, site code, or manifests. If MaaS fails, report the Huawei Cloud authentication/quota/service error and do not fall back to non-Huawei image APIs.
