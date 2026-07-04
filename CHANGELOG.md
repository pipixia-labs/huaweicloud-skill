# Changelog

## Unreleased

- 新增 `hcloud_billing_live_read.py`，把 Billing/BSS request planner、safe_exec 和脱敏 summarizer 串成显式确认的只读 live-read wrapper；默认只计划，执行时要求 `READ_BILLING_DATA` 确认并限制分页。

## 0.7.0 - 2026-07-03

- 收敛工具入口：新增统一 acceptance closure 入口和统一 closure planner 入口，保留旧脚本兼容但把首选路径收敛到单一命令。
- 精简 `SKILL.md`，把入口聚焦到统一大 Skill 定位、安全红线、默认工作流和 10 个以内首选入口；详细脚本清单继续放在 `references/scripts.md`。
- 新增 live validation 规划能力，面向 ECS、VPC/EIP、OBS、ELB、RDS 生成真实账号证据、回读、probe 和晋级缺口计划。
- 扩展 MaaS 用量治理：支持 `HUAWEI_*` 环境变量别名，并为 ShowStatistics 增加受控 `--execute` 只读查询路径。
- 大幅强化 Billing/BSS 能力：扩展余额、账单流水、摊销、资源包、券、订单、企业/伙伴和参考字典只读 planner，并固化 `fact × grain × money_basis × scope/billing_period` 账单语义纪律。
- 完善云操作 playbook：MaaS 用量统计、CES/ECS Agent 与 `ces.0014`、OBS `SYS.OBS` 指标、COC 临时凭证模式、Flexus L 控制面观察、CCE/UCS/SWR 治理和 DWS/数据库诊断方法。
- 补充 `CLI_ERROR` 识别、KooCLI 日志排查、凭据本地化处理和结果叙事真实性边界，减少误判、过度宣称和密钥泄露风险。
- 更新 Terraform guardrails，明确生成、plan、apply、hcloud readback 和业务验收之间的状态边界。

## 0.6.2 - 2026-07-03

- Added scenario-level playbooks for OBS static website hosting, Flexus-style low-cost hosting, ECS monitoring troubleshooting, EIP cost optimization, IAM permission diagnostics, CCI workload readiness, SWR image readiness, FunctionGraph readiness, production Web/API readiness, MaaS usage governance, and CCE cloud-native assessment.
- Added safe local planners for MaaS usage statistics and CCE assessment so agents can collect required inputs and evidence without printing credentials or changing cloud resources.
- Added a built-in acceptance probe runner for HTTP, TCP, DNS, and TLS probe templates, plus a live regression runbook and planner for true-account validation.
- Added Terraform operations guidance and a gated Terraform import/drift/remote-state planner that keeps hcloud discovery/readback as the live-state source and requires explicit confirmation before state-changing import execution.
- Updated scenario routing, script audience boundaries, Terraform references, and tests so the new scenario assets remain local to the single-skill architecture.

## 0.6.1 - 2026-06-22

- Added Huawei Cloud MaaS API-first support for model catalog lookup, V2/OpenAI-compatible chat, image understanding, image generation/editing, and asynchronous video generation.
- Added MaaS model call references, a local MaaS model catalog, scenario routing, readiness playbook, and offline helper tests while keeping MaaS outside the KooCLI service registry.
- Updated environment doctor checks to report MaaS API Key readiness through `MAAS_API_KEY` or `MODELARTS_MAAS_API_KEY` without exposing secret values.

## 0.6.0 - 2026-06-18

- Added BSS/Billing semantic routing, fixed `cn-north-1`/`cn` hcloud read-only command plans, pagination warnings, and a protected-identifier result summarizer.
- Added v0.6 acceptance scenarios for beginner setup, low-cost website hosting, cost governance, CES metric troubleshooting, mid-enterprise governance, Terraform plan-review, and security-group reuse.
- Added a script audience manifest so runtime, guarded-change, supplement, maintenance, internal-library, and compatibility scripts have explicit review boundaries before any future consolidation.
- Moved long runtime safety rules from `SKILL.md` into `references/runtime-safety-boundaries.md` and added `references/versioning-policy.md` so release docs remain the version truth source.
- Added cross-region/EPS inventory planning, scoped idle-audit summaries, and an IAM action hint catalog used by permission-error diagnostics.
- Added COC readiness and entry-level web-hosting playbooks so low-cost OBS/Flexus/ECS website choices and remote-execution fallback paths are explicit.
- Added Terraform generation guardrails for hcloud-first IaC generation, plan review, sensitive-data handling, example promotion checks, and post-apply hcloud verification.
- Added five sanitized Terraform examples from the Huawei upstream asset library: `vpc_security_group_stack`, `vpc_peering_stack`, `nat_vpc_peering_stack`, `cce_addon_stack`, and `elb_as_stack`.
- Added thirteen P0/P1 Terraform examples for reuse workflows, end-to-end topologies, CCE variants, and RDS engine shapes: `elb_reuse_stack`, `nat_reuse_stack`, `cce_node_pool_reuse_stack`, `ecs_elb_rds_stack`, `obs_cdn_dns_stack`, `cce_coredns_addon_stack`, `cce_turbo_cluster_stack`, `cce_node_partition_stack`, `rds_mysql_stack`, `rds_postgresql_ha_stack`, `rds_read_replica_stack`, `rds_mysql_eip_stack`, and `rds_sqlserver_stack`.
- Added Terraform provider validation guidance and routed it as a core Terraform reference.
- Enhanced Terraform context inspection with read-only CLI config, provider mirror, and global provider cache hints without adding installer or provider download behavior.

## 0.5.1 - 2026-06-17

- Added structured P0 `acceptance_evidence_plan` output to `hcloud_lifecycle_closure_plan.py` so VPC/EIP/EVS/ELB/RDS/OBS/DNS/SCM/CDN/CES+LTS plans expose cloud, runtime, protocol, observability, governance, and missing-input evidence items.
- Added `hcloud_acceptance_evidence_result.py` and `hcloud_acceptance_probe_plan.py` so P0 acceptance can move from "what to collect" to local `passed`/`warning`/`missing`/`blocked` evaluation and non-executing probe templates.
- Added `hcloud_closure_maturity_audit.py` to report current closure tiers honestly: ECS as the end-to-end sample, P0 as task-level planner, P1/P2 as planner-only, and metadata-backed services as evidence gaps until promoted.
- Updated `SKILL.md`, scenario routing, and examples so agents and users can follow the recommended offline closure chain from scenario route to lifecycle plan, probe plan, and evidence result.
- Updated SDK supplement guidance from the local Python SDK reference snapshot, including installed-package runtime assumptions, SDK auth variables, Basic/Global credential selection, region/endpoint fallback, exception fields, Pod Identity notes, and narrow read-only candidate rules.
- Refreshed Terraform provider resource/data-source inventories from the local provider `1.93.0` reference snapshot, covering 1684 resources and 2239 data sources.
- Added `hcloud_terraform_provider_inventory.py` to regenerate provider inventories and fail on drift during maintenance.
- Expanded Terraform provider auth/context guidance and `hcloud_terraform_context_inspect.py` for `HW_*`/`OS_*` aliases, shared hcloud config encryption warnings, assume role/OIDC hints, enterprise project, retry, signing, and provider context variables.

## 0.5.0 - 2026-06-13

- Absorbed Terraform Markdown and `.tf` assets from the prior Huawei Terraform skill into `references/terraform/` and `examples/terraform/`, excluding runtime artifacts such as `.terraform/`, state files, real tfvars, and crash logs.
- Added Terraform asset catalogs plus `hcloud_terraform_catalog.py`, `hcloud_terraform_context_inspect.py`, and `hcloud_terraform_router.py` so agents can select targeted examples/references without browsing all Terraform assets.
- Updated hcloud-first workflow, README, script reference docs, and architecture docs to treat Terraform as a supplemental IaC plane with hcloud discovery before plan and hcloud verification after apply.
- Cleaned active Terraform references and examples to use `hcloud` / `huaweicloud-skill` naming while keeping the original source skill only as an archive.
- Removed the unsupported `version` field from `SKILL.md` frontmatter so `skill-creator` validation passes.

## 0.4.0 - 2026-06-13

- Removed the committed full generated hcloud catalog so ClawHub packaging stays under the 10M single-file limit.
- Kept runtime catalog loading on `hcloud-service-catalog.index.json` plus per-service JSON payloads, with full catalog generation available only as an explicit local maintenance artifact.
- Updated catalog tests and documentation to use the lazy catalog path as the normal agent runtime path.
- Added an SDK supplement layer that prefers installed `huaweicloudsdk*` packages, keeps SDK as an hcloud supplement, and gates executable SDK calls through `references/sdk-supplement-registry.json`.
- Added SDK catalog, read-only bridge, and registry audit scripts, plus hcloud discovery/query integration for SDK request-type and path/query evidence.
- Added `hcloud_scenario_router.py`, `references/scenario-router.json`, and service guides under `references/guides/` so broad 上云/用云/管云 goals can route to local playbooks, planners, SDK supplements, and Terraform candidates.
- Added `references/terraform-workflow.md` to define Terraform as a separate IaC route with hcloud discovery before planning and hcloud verification after apply.

## 0.3.3 - 2026-06-06

- Completed the first P1 governance closure planner with `hcloud_governance_closure_plan.py`, covering TMS, CTS, CBR, RMS/Config, Billing/BSS, WAF, DLI, and CodeArtsRepo.
- Added read-only evidence command planning and top-level governance summaries for P1 services, including planned command counts, missing target parameters, eligible/blocked promotion status, and evidence-gap grouping.
- Added a conservative BSS curation profile and Billing/Cost governance playbook so billing/cost workflows have explicit request-spec, privacy, freshness, and no-credential/no-HTTP boundaries.
- Kept Billing/BSS request-spec-only: the governance planner does not generate hcloud BSS live query commands, sign requests, or accept billing credentials.
- Added tests for P1 default service coverage, read-only evidence command planning, Billing request specs, RMS/Config aliasing, WAF hard-gated policy posture, and unsupported-service validation.
- Added `hcloud_p2_scenario_closure_plan.py`, a planner-only four-stage scenario closure planner for CCE, NAT, DCS, RFS, UCS, IAM/KPS/IMS dependencies, security posture, and database-family services.
- Added P2 evidence command planning for services with curation profiles and explicit `metadata_evidence_gap` status for security posture and database-family services that are still metadata-backed.
- Kept P2 writes disabled: cluster, NAT, cache, stack, fleet, security, key, IAM, and database mutations require dedicated guarded flows before any submit path exists.
- Added tests for P2 default group coverage, CCE read-only evidence command planning, security/database metadata-gap boundaries, and unsupported-group validation.
- Updated README, SKILL, script references, architecture, technical overview, implementation details, service coverage, data coverage, lifecycle scenario docs, and review plan status to describe the P1/P2 planner boundaries.

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
- Split runtime catalog loading into index/per-service lazy files while retaining the full catalog for compatibility and complete diffs. The full catalog was later removed from committed assets for ClawHub packaging.
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
