# Changelog

## 0.2.4 - 2026-06-06

- Added a bundled hcloud metadata catalog covering 125 services and 10,194 operations without depending on `huaweicloud-data`.
- Added metadata-backed discovery, explicit-parameter resource query, and planner-only mutation planning for registry-outside services.
- Added catalog confidence tiers, sanitized read-only live smoke evidence, catalog diff/smoke-candidate tools, and curation promotion audits.
- Split runtime catalog loading into index/per-service lazy files while retaining the full catalog for compatibility and complete diffs.
- Promoted DCS, RFS, and UCS into read-only curated registry coverage, bringing curated services to 19 and metadata-backed services to 107.
- Added live-read-smoked confidence for AOS `ListPrivateHooks`, ModelArts `ListAlgorithms`, and CBR `ListAgent`; CFW `ListDnsServers` remains evidence-only because the cloud response is not_found-shaped.
- Consolidated MaaS image asset naming around `maas_text_to_image.py` while keeping the old qwen entrypoint compatible.

## 0.2.3 - 2026-06-05

- Fixed `hcloud_safe_exec.py` JSON parsing and cloud-error detection for polluted stdout, nested error payloads, byte output, and Windows-safe UTF-8 replacement decoding.
- Strengthened generic in-guest execution guidance for ECS-backed tasks when COC/remote command is unavailable.
- Allowed agents to create task-scoped keypairs and save returned private keys as restricted local artifacts for SSH validation and follow-up operations.
- Added SSH fallback guidance using saved keys, exportable keypairs, reset password, restricted temporary SSH ingress, and cloud-init reinstall/rebuild for replaceable resources.
- Expanded EVS readiness guidance to distinguish cloud-side attachment from in-guest filesystem readiness, including `/data` mount verification and idempotent mount scripts.
- Expanded ELB HTTP backend readiness guidance with topology prechecks, cross-VPC/IP-target boundaries, backend service startup handling, and health-check service fallback.
- Added stable semantic naming and capacity inference guidance for resources whose names or sizes are not explicitly specified by the user.
- Added Huawei Cloud ModelArts MaaS image asset generation support for Huawei-hosted web/static-site deployments, including `scripts/qwen_text_to_image.py`, generated-asset readiness guidance, local manifest output, and tests.
- Clarified that MaaS image generation is auxiliary Huawei Cloud site-asset support, not a generic image-generation route or a KooCLI service registry entry.
- Added KooCLI installation guidance for cases where `hcloud` is not available in PATH.

## 0.2.2 - 2026-06-03

- Added an ECS SSH credential readiness flow, including keypair/password selection, local credential artifact requirements, and post-`ACTIVE` SSH validation guidance.
- Added guidance for reusing existing security groups when `CreateSecurityGroupRule` is blocked by SCP/IAM, while preserving port, VPC, enterprise project, and risk boundaries.
- Added a security group ingress policy that blocks `0.0.0.0/0` for SSH `22` and common Web ports `80`, `443`, `3000`, `5000`, `8000`, and `8080`.
- Added offline planner checks so `hcloud_change_plan.py`, service change plans, guarded VPC flows, and ECS create JSON validation surface unsafe ingress violations before dry-run or submit.
- Added Mermaid resource topology guidance for requirement clarification, plan confirmation, result presentation, and troubleshooting.

## 0.2.1 - 2026-05-29

- Strengthened large-output handling guidance for `IMS ListImages`, `ECS ListFlavors`, and `ECS ListFlavorSellPolicies`.
- Added explicit recommendations to use filtering, field projection, result files, parsed JSON files, and small summaries instead of sending full large JSON payloads back into the conversation.
- Updated IMS and ECS readiness playbooks with large-result handling patterns for image discovery, flavor selection, and flavor sell policy analysis.

## 0.2.0 - 2026-05-28

Full release note: see `RELEASE_NOTES.md`.

- Expanded from the v0.1 ECS-focused baseline to a data-driven multi-service skill covering ECS, VPC, RDS, IMS, EVS, EIP, ELB, NAT, KPS, IAM, CCE, CDN, DNS, SCM, OBS, and CES through registry-backed query/readiness/planner routes.
- Added `references/service-registry.json` plus `scripts/check_question_coverage.py` to validate generated question coverage, Excel E2E validation paths, CRUD risk labels, and executable route coverage.
- Added multi-service read-only execution tools: `hcloud_resource_discovery.py`, `hcloud_resource_query.py`, `hcloud_service_readiness.py`, `hcloud_readonly_smoke.py`, and `hcloud_resource_detail_probe.py`.
- Strengthened ECS completion semantics with ECS create count guards, placeholder checks, JSON-friendly command output, `hcloud_ecs_wait_job.py` job-only scope, and `hcloud_ecs_verify_active.py` ACTIVE resource verification.
- Added guarded change flows: EIP-specific Plan -> dry-run -> submit -> `ShowPublicip` verify, plus generic VPC/ELB/EVS/NAT/RDS/CDN/DNS/SCM Plan -> dry-run -> guarded submit -> resource Show* verify -> service smoke.
- Added OBS `hcloud obs`/obsutil adapters for bucket read-only checks and planner-only bucket/lifecycle/policy changes.
- Added structured `error_details` to `hcloud_safe_exec.py`, covering credential, permission, region/project, quota, parameter, not found, network, metadata, timeout, and cloud API failures.
- Added broad playbooks, service coverage docs, manual validation records, architecture contracts, and 94 passing unit tests.

## 0.1.0

- Initial hcloud/KooCLI skill with context inspection, safe execution, metadata lookup, ECS create planning, ECS job polling, references, playbooks, examples, and baseline tests.
