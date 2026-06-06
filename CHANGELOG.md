# Changelog

## 0.3.2 - 2026-06-06

- Added `hcloud_lifecycle_closure_plan.py`, a planner-only six-stage lifecycle closure planner for the P0 task set: VPC/security group, EIP, EVS, ELB, RDS, OBS, DNS, SCM, CDN, and CES/LTS.
- The new planner composes service change planning, service readiness planning, OBS/LTS adapters, and local policy checks into one task-level output: context/dependency discovery, parameter planning, risk gates, controlled execution, post-change verification, and governance audit.
- Extended readiness coverage for VPC/security group, RDS, and OBS with target-scoped readback such as `ShowSecurityGroupRule`, RDS backup/configuration checks, and OBS bucket policy/stat checks.
- Strengthened EIP, VPC, EVS, ELB, RDS, DNS, SCM, and CDN service change hints around public exposure, same-region/single EIP binding, guest filesystem readiness, backend health, backup/connection posture, TTL propagation, certificate deployment, origin/cache behavior, and protocol verification.
- Added CES/LTS health-evidence closure planning so metric discovery and bounded log evidence can be planned together without opening a generic mutation path.
- Updated README, SKILL, script reference docs, architecture, implementation details, technical overview, coverage, and lifecycle scenario docs to describe the v0.3.2 P0 closure model.

## 0.3.1 - 2026-06-06

- Expanded generated hcloud metadata catalog generation to merge English and Chinese KooCLI metadata at operation level.
- Current committed catalog audit reports 198 local metadata services and 15,666 operations, while `hcloud --help` shows 199 non-HCS/ManageOne visible services on the maintainer machine.
- Added source language metadata to catalog services and operations so Chinese fallback coverage remains visible during audits and future curation.
- Updated local metadata lookup to read `services_cn.json`, `apis_cn.json`, `*_cn.yaml`, and `endpoints_cn.json` when English cache entries are absent.
- Updated Billing/Cost probing so newly discoverable `BSS` is treated as a metadata-backed candidate, not default live billing query support.
- Kept curated registry coverage unchanged at 19 services and 311 registered operations; broader catalog coverage remains metadata-backed and subject to existing planner/read-only/guarded-change boundaries.

## 0.3.0 - 2026-06-06

- Upgraded lifecycle coverage around 上好云、用好云、管好云 with account inventory, idle-resource audit, teardown review planning, observability readiness, Billing/Cost request planning, and governance candidate profiles.
- Hardened change execution safety: generated safe-exec paths are workspace-stable, guarded submits require a plan-bound token, run journals are redacted, delete verification supports expected-absent semantics, and resource verifier fallback IDs are service-scoped.
- Added `hcloud_account_inventory.py`, `hcloud_idle_audit.py`, `hcloud_teardown_plan.py`, `hcloud_observability_plan.py`, `hcloud_ces_alarm_plan.py`, `hcloud_lts_readonly.py`, `hcloud_billing_cost_probe.py`, and `hcloud_billing_readonly.py`.
- Expanded idle/governance analysis to flag security-group sensitive ingress, empty or unhealthy ELB posture, weak RDS backup posture, and conservative VPC/security group review candidates without generating destructive commands.
- Added planner-only CES alarm drafting and bounded LTS read-only log query planning; alarm creation and log mutations remain outside generic submit paths.
- Added Billing/Cost API request-spec planning for official monthly bill summary, cost analysis, and resource record APIs. The planner does not sign requests, accept credentials, or send HTTP traffic.
- Added candidate profiles and playbooks for CTS, TMS, CBR, RMS, Config, and LTS, plus value metadata and audit output for tenant-goal ranking.
- Final local verification passed with 172 unit tests, script compile checks, and clean `git diff --check`.

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
