# Release Notes

## v0.3.2 / 0.3.2 - 2026-06-06

v0.3.2 is a lifecycle closure patch on top of v0.3.1. It does not expand catalog breadth. Instead, it turns the P0 service set into task-level planner coverage for common 上云、用云、管云 workflows: VPC/security group, EIP, EVS, ELB, RDS, OBS, DNS, SCM, CDN, and CES/LTS.

### Changes Since v0.3.1

- Adds `hcloud_lifecycle_closure_plan.py`:
  - Planner-only and non-executing by default.
  - Builds six-stage closure plans: context/dependency discovery, operation/parameter planning, risk/security gates, controlled execution/error handling, post-change verification, and governance/audit follow-up.
  - Reuses `hcloud_service_change_plan.py`, `hcloud_service_readiness.py`, and `hcloud_security_policy.py` rather than opening a new submit path.
- Improves VPC/security group closure:
  - Adds `ShowSecurityGroupRule` to service readiness.
  - Keeps unrestricted SSH/Web ingress hard-blocked before submit planning.
- Improves EIP closure guidance:
  - Treats binding as public exposure and cost-impacting change.
  - Calls out same-region target, single binding, bandwidth, billing, `ShowPublicip`, and security group reachability checks.
- Improves EVS closure guidance:
  - Separates cloud-side volume state from guest filesystem readiness.
  - Keeps device discovery, partition/filesystem, mountpoint, `fstab`, and write-test evidence as required readiness concepts.
- Improves ELB closure guidance:
  - Treats listener, pool, member, and health monitor as staged resources.
  - Requires backend ECS/security group checks, member health, and protocol probes before claiming application readiness.
- Adds RDS closure guidance:
  - Checks instance, backup, backup policy, configuration, connection, restart-impact, and rollback evidence before database-affecting changes.
- Adds OBS closure guidance:
  - Routes bucket work through the OBS/obsutil adapter instead of generic OpenAPI-style assumptions.
  - Checks bucket stat, policy, lifecycle, public exposure, and object-retention/data-loss boundaries.
- Adds DNS, SCM, and CDN closure guidance:
  - DNS focuses on record conflicts, TTL/propagation, rollback values, and resolution verification.
  - SCM focuses on certificate state, domain/SAN matching, expiry, deployment target, and HTTPS chain validation.
  - CDN focuses on domain/origin/HTTPS/cache behavior plus CDN-vs-origin protocol probes and refresh/preheat planning.
- Adds CES/LTS health-evidence closure guidance:
  - Combines CES metric discovery with bounded LTS log evidence planning.
  - Keeps LTS as read-only metadata-backed evidence planning and does not create a generic mutation path.

### Validation

- `python3 -m unittest discover -s huaweicloud-skill/tests`: 185 tests passed.
- `python3 -m compileall -q huaweicloud-skill/scripts`: passed.
- `git diff --check`: passed.

### Compatibility and Safety Notes

- v0.3.2 does not make P0 writes auto-executable.
- The new lifecycle closure planner is a task-level planner. Real dry-run, submit, and verification still go through the existing guarded flows and require explicit confirmation.
- CES/LTS closure is evidence planning only; it does not create alarms, mutate logs, or submit observability changes.
- Broader governance services beyond this P0 set remain candidate/planner/read-only coverage until curated smoke evidence and guarded paths are added.

## v0.3.1 / 0.3.1 - 2026-06-06

v0.3.1 is a catalog coverage patch on top of v0.3.0. It updates the generated hcloud metadata catalog from the older English-only generation path to an operation-level English-first plus Chinese-fallback merge. The goal is to reflect the real KooCLI metadata breadth more accurately while keeping the same safety model: broader catalog coverage does not make registry-outside services deeply curated or executable by default.

### Changes Since v0.3.0

- Expands generated catalog coverage:
  - Current catalog audit reports 198 local metadata services and 15,666 hcloud operations.
  - The maintainer machine's `hcloud --help` shows 203 visible services; after excluding HCS/ManageOne related services, this is 199 visible services.
  - `APIExplorer` is visible in `hcloud --help` but has no local metadata template in `metaRepo`, so it is not counted as a generated catalog service.
- Improves catalog generation:
  - `build_hcloud_catalog.py` now reads `services_en.json`/`services_cn.json`, `apis_en.json`/`apis_cn.json`, and `*_en.yaml`/`*_cn.yaml`.
  - English metadata remains preferred for existing operation summaries and details.
  - Chinese metadata fills missing services, missing operations inside existing services, and missing detail files.
  - Catalog services and operations now carry metadata language fields for auditability.
- Improves local metadata lookup:
  - `hcloud_meta_lookup.py` now uses Chinese metadata fallback for services, operations, operation detail, and endpoints.
  - Versioned detail files such as `ListHosts_v5_cn.yaml` are matched to their operation names.
- Keeps Billing/Cost conservative with the wider catalog:
  - `BSS` is now discoverable as a metadata-backed direct candidate.
  - `hcloud_billing_cost_probe.py` keeps live billing query support disabled by default until curated registry coverage, read-only smoke evidence, and an approved execution path are added.

### Validation

- `python3 -m unittest discover -s tests`: 175 tests passed.
- `python3 -m compileall -q scripts`: passed.
- `python3 scripts/build_hcloud_catalog.py --source-meta-repo ~/.hcloud/metaRepo`: generated 198 services and 15,666 operations.
- `python3 scripts/hcloud_catalog_audit.py --fail-on-drift --pretty`: passed and reported 198 catalog services, 15,666 operations, 19 curated registry services, and 180 metadata-backed services.
- `git diff --check`: passed.

### Compatibility and Safety Notes

- Curated registry coverage is unchanged: 19 services and 311 registered operations.
- Registry-outside services remain metadata-backed. They can support discovery, explicit-parameter read-only queries, and planner-only mutation plans, but they are not promoted to curated coverage by catalog presence alone.
- Billing/Cost, identity, security, key, teardown, and other sensitive mutations remain behind existing planner and guarded-change boundaries.

## v0.3.0 / 0.3.0 - 2026-06-06

v0.3.0 is the lifecycle governance upgrade after v0.2.4. It keeps the hcloud metadata-backed breadth from v0.2.4, then adds safer multi-step operation tracking, account inventory, idle-resource review, teardown review planning, observability readiness, Billing/Cost request planning, and the next governance candidate profiles. The release goal is to help users 上好云、用好云、管好云 without turning broad metadata coverage into unsafe default execution.

### Changes Since v0.2.4

- Hardens execution safety:
  - Generated safe-exec commands use bundled script paths instead of cwd-relative script names.
  - EIP and generic guarded submits require a plan-bound token.
  - EIP, generic guarded flow, and ECS create planning can append redacted run-journal events.
  - Delete/detach/disassociate verification can treat expected `not_found` as successful absent-state verification.
  - Resource verifier fallback ID extraction is scoped by service.
- Adds account governance tools:
  - `hcloud_account_inventory.py` builds a read-only cross-service inventory plan.
  - `hcloud_idle_audit.py` analyzes saved JSON results for conservative idle candidates.
  - `hcloud_teardown_plan.py` creates a dependency-aware teardown review plan and never generates submit commands.
- Extends observability:
  - `hcloud_observability_plan.py` combines resource-state checks with CES metric discovery.
  - `hcloud_ces_alarm_plan.py` discovers CES metrics/alarm rules and drafts alarm intent, but does not create or update alarms.
  - `hcloud_lts_readonly.py` discovers LTS log groups/streams and builds bounded read-only log queries.
  - `references/playbooks/observability-readiness.md` documents the resource state + CES + LTS readiness flow.
- Adds Billing/Cost request planning:
  - `hcloud_billing_cost_probe.py` remains a local catalog feasibility check.
  - `hcloud_billing_readonly.py` builds planner-only request specs for official Billing/Cost APIs such as monthly bill summary, cost analysis, and resource records.
  - The Billing/Cost planner does not accept credentials, sign requests, send HTTP traffic, or infer spend from resource inventory.
- Expands curation grooming:
  - Candidate profiles and playbooks were added for CTS, TMS, CBR, RMS, Config, and LTS.
  - Curation audit now surfaces optional lifecycle, user-value, tenant-goal, and scenario metadata.
  - CTS/TMS/CBR/RMS/Config/LTS remain metadata-backed candidates until live read-smoke evidence is collected.

### Validation

- `python3 -m unittest discover -s huaweicloud-skill/tests`: 172 tests passed.
- `python3 -m compileall -q huaweicloud-skill/scripts`: passed.
- `python3 scripts/hcloud_curated_promotion_audit.py --include-curated --pretty`: reported 19 curated services with 0 blocked curated-health findings.
- `git diff --check`: passed.

### Compatibility and Safety Notes

- v0.3.0 does not make teardown, Billing/Cost, CES alarm, or LTS mutation workflows executable by default.
- Idle audit and teardown planning identify review candidates only; they are not delete, release, unsubscribe, stop, or resize authorization.
- Billing/Cost support is request-spec planning only until a reviewed signed-request runner or SDK path is added.
- CTS, TMS, CBR, RMS, Config, and LTS are candidate profiles, not curated registry coverage.

## v0.2.4 / 0.2.4 - 2026-06-06

v0.2.4 is the hcloud metadata coverage upgrade after v0.2.3. It adds a skill-owned hcloud catalog, metadata-backed broad coverage, confidence/audit tooling, lazy catalog loading, and the first read-only curated promotions from the new metadata work. The release keeps the safety boundary unchanged: generated catalog coverage does not mean all services are curated, and registry-outside mutation plans remain planner-only unless a dedicated guarded flow exists.

### Changes Since v0.2.3

- Adds a bundled hcloud metadata catalog owned by this skill:
  - Catalog summary: 125 metadata services and 10,194 operations.
  - Runtime does not depend on `huaweicloud-data`; copied metadata is used only as an input source for generated skill assets.
  - Curated registry remains the primary route when a service is registered.
- Adds metadata-backed coverage for registry-outside services:
  - Safe discovery can generate read-only `List*` style commands where required business parameters are absent.
  - Resource query requires explicit target parameters and does not guess resource IDs.
  - Mutation plans are planner-only by default, with dry-run support represented as `unknown` unless proven.
- Adds confidence and audit layers:
  - `catalog-derived` means operation shape comes from hcloud metadata only.
  - `live-read-smoked` means a real read-only hcloud command reached `command_shape_ok`.
  - Sanitized smoke fixtures omit raw stdout, stderr, token material, and full response bodies.
  - Curated promotion audit checks live-smoke evidence, curation profiles, playbooks, risk profiles, readiness operations, and resource-query candidates.
- Adds catalog maintenance tooling:
  - Catalog audit reports registry/catalog/metadata-backed summary fields.
  - Catalog diff and smoke-candidate tools support future metadata upgrades.
  - Runtime catalog loading now uses an index plus per-service JSON files; the full generated catalog is retained for compatibility and complete diffs.
- Expands curated coverage:
  - DCS, RFS, and UCS are promoted to read-only curated registry coverage.
  - Curated registry count is now 19; metadata-backed service count is 107.
  - DCS/RFS/UCS have `change_operations=[]`; write support still requires dedicated guarded flows before any generic submit path can exist.
- Adds live-smoke confidence:
  - DCS: `ListAvailableZones`, `ListMaintenanceWindows`.
  - RFS: `ListPrivateHooks`, `ListPrivateModules`.
  - UCS: `ListAddonTemplates`, `ListPolicyDefinitions`.
  - WAF: `ListAntileakagePolicyRules`, `ListInstance`.
  - CodeArtsRepo: `ListCurrentUserRepositories`, `ListGroups`.
  - DLI: `ListAuthInfo`, `ListCatalogs`.
  - AOS: `ListPrivateHooks`.
  - ModelArts: `ListAlgorithms`.
  - CBR: `ListAgent`.
  - CFW `ListDnsServers` remains evidence-only because the cloud response is not_found-shaped.
- Consolidates MaaS image asset naming:
  - `scripts/maas_text_to_image.py` and `references/maas-image-generation.md` are now the primary entrypoint/docs.
  - The old qwen entrypoint and doc remain as compatibility wrappers.

### Validation

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests`: 144 tests passed before release.
- `python3 scripts/hcloud_catalog_audit.py --fail-on-drift --pretty`: passed with 125 catalog services, 10,194 operations, 19 curated services, and 107 metadata-backed services.
- `python3 scripts/hcloud_curated_promotion_audit.py --service DCS --service RFS --service UCS --service WAF --service CodeArtsRepo --service DLI --min-live-ops 2 --include-curated --pretty`: passed with DCS/RFS/UCS `already_curated`, WAF/CodeArtsRepo/DLI `eligible`, and 19/19 curated services healthy.
- `python3 scripts/check_materials_drift.py --pretty`: passed.
- `python3 scripts/check_question_coverage.py --pretty`: passed.
- JSON parse checks, sensitive-field scans over smoke fixtures/confidence/manual validation, local absolute-path scan, and `git diff --check`: passed.

### Compatibility and Safety Notes

- v0.2.4 does not claim all 125 catalog services are deeply curated. Catalog-derived coverage is broad but shallower than curated registry coverage.
- Registry-outside metadata-backed mutation plans remain planner-only; security/identity/key/governance mutations can trigger hard guards.
- DCS/RFS/UCS are read-only curated services in this release. Enabling writes for them requires service-specific guarded flows, explicit confirmation, and post-change readback.
- B2 distribution-size cleanup is intentionally not included in this release.

## v0.2.3 / 0.2.3 - 2026-06-05

v0.2.3 improves practical Huawei Cloud deployment workflows on top of v0.2.2. It keeps the existing safety posture while strengthening hcloud JSON error handling, ECS in-guest execution guidance, storage/load-balancer readiness guidance, KooCLI installation guidance, and Huawei Cloud ModelArts MaaS image asset generation for Huawei-hosted web/static-site deployments.

### Changes Since v0.2.2

- Improves `hcloud_safe_exec.py` JSON and error handling:
  - Parses JSON payloads even when stdout has leading diagnostic text before the JSON object or array.
  - Treats nested cloud error payloads, such as `{ "error": { ... } }`, as logical failures even when the local process exits with code `0`.
  - Uses UTF-8 replacement decoding for safer cross-platform subprocess output handling, including Windows-style output edge cases.
- Adds generic in-guest execution guidance:
  - ECS-backed tasks must distinguish cloud-side resource state from OS/application state.
  - Agents should continue through saved SSH keys, exportable keypairs, reset password, or cloud-init reinstall/rebuild when the resource is new, test, demo, deployment-oriented, stateless, or otherwise replaceable.
  - Agents should stop and request authorization before destructive recovery on existing stateful resources.
- Expands key management guidance:
  - Agents may create task-scoped KPS keypairs and save returned `private_key` values into restricted local artifacts.
  - New ECS resources that need later installation, mounting, or service startup should be created with a usable management path from the start.
- Expands EVS readiness:
  - EVS `in-use` is not enough to declare `/data` or any mount point ready.
  - The skill now documents naming/capacity inference, duplicate-disk avoidance, SSH fallback, idempotent filesystem mounting, and write-test verification.
- Expands ELB HTTP backend readiness:
  - Adds canonical VPC/subnet topology prechecks before listener/pool/member churn.
  - Clarifies when cross-VPC IP targets are valid and when backend ECS should be rebuilt into a reachable topology.
  - Requires backend service startup and member `ONLINE` evidence before declaring end-to-end HTTP completion.
- Adds Huawei Cloud ModelArts MaaS image asset generation support:
  - Adds `scripts/qwen_text_to_image.py` for generating local WebP/PNG site assets from Huawei Cloud MaaS `b64_json` image responses.
  - Reads credentials only from `MAAS_API_KEY` or `MODELARTS_MAAS_API_KEY` and writes a local manifest without secrets.
  - Defaults to the Huawei Cloud MaaS endpoint `api.modelarts-maas.com` and model `qwen-image`.
  - Adds `references/qwen-image-generation.md` and `references/playbooks/static-site-generated-assets-readiness.md`.
  - Keeps this workflow as auxiliary Huawei Cloud site-asset support, not a generic image-generation route and not a KooCLI service registry entry.
- Adds KooCLI installation guidance:
  - If `hcloud` is missing from PATH, agents should stop real cloud queries/changes and direct the user to the official KooCLI installation documentation.

### Validation

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests`: 109 tests passed before release.
- `git diff --check` passed before release.
- `tests/test_qwen_text_to_image.py` covers request shape, dry-run behavior, API-key handling, base64/data-URI decoding, manifest redaction, output filename safety, and size normalization.

## v0.2.2 / 0.2.2 - 2026-06-03

v0.2.2 is a safety and communication patch release on top of v0.2.1. It strengthens ECS login readiness, tightens security group ingress behavior, and adds Mermaid topology diagrams as a standard way to clarify cloud resource relationships with users.

### Changes Since v0.2.1

- Adds an ECS SSH credential readiness flow:
  - Linux ECS creation must choose exactly one login mode: `key_name` with a locally available private key, or `adminPass` saved to a restricted local credential artifact.
  - ECS `ACTIVE` is no longer enough to call a server login-ready; agents must validate SSH with the selected credential before reporting that login is ready.
  - Password-based Linux ECS creation must not rely on retrieving the root password after creation.
- Adds a guarded security group fallback for restricted accounts:
  - If `CreateSecurityGroupRule` / `vpc:securityGroupRules:create` is explicitly denied by SCP or IAM, agents should stop retrying the forbidden operation.
  - Agents may reuse an existing security group only when it matches the required VPC, enterprise project, target ports, and risk boundary; any naming difference must be explained in the final result.
- Blocks unsafe SSH/Web ingress:
  - Security group ingress rules for SSH `22` and common Web ports `80`, `443`, `3000`, `5000`, `8000`, and `8080` must not use `0.0.0.0/0`.
  - `hcloud_change_plan.py`, service change plans, guarded VPC flows, and ECS create JSON validation now surface these violations before dry-run or submit.
  - SSH, VPC, and ELB playbooks now require restricted source CIDRs for exposed SSH/Web ports.
- Adds Mermaid resource topology guidance:
  - Agents can use Mermaid `flowchart` diagrams to clarify requirements, confirm plans, present task results, or debug connectivity.
  - Diagrams must distinguish planned resources from verified facts and should focus on resource type, name, short ID, IP, status, port, CIDR, security group source, binding relationship, and blockers.
  - README includes a public access -> EIP -> security group -> ECS topology example with EVS, IMS, and CES relationships.

### Validation

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests`: 102 tests passed.
- `git diff --check`: passed.
- Planner smoke for `22` + `0.0.0.0/0`: returned `success=false` and generated no submit commands.
- Planner smoke for `22` + `203.0.113.10/32`: generated the expected dry-run and submit plan.

## v0.2.1 / 0.2.1 - 2026-05-29

v0.2.1 is a documentation and agent-guidance patch release focused on large hcloud query outputs. It does not change runtime script behavior.

### Changes

- Marks `IMS ListImages`, `ECS ListFlavors`, and `ECS ListFlavorSellPolicies` as high-risk large-output APIs in the default workflow.
- Recommends filtering, `--cli-query`, `--result-file`, and `--parsed-json-file` patterns so agents can keep full results on disk while returning only counts, key samples, summaries, and file locations to the conversation.
- Adds IMS image discovery guidance for large `ListImages` responses.
- Adds ECS create readiness guidance for large flavor and sell policy responses, including file-backed join/filter analysis.

### Validation

- Documentation-only change.
- `git diff --check` passed before release.

## v0.2 / 0.2.0 - 2026-05-28

v0.2 把 `huaweicloud-skill` 从一个以 ECS 和基础 KooCLI 工具为主的技能，升级为面向多服务、可审计、可回归的华为云执行型 skill。核心变化是：查询路径更广，变更路径更安全，验证路径更具体，错误原因更容易被 agent 读取和解释。

### 和 v0.1 相比

| 维度 | v0.1 | v0.2 |
| --- | --- | --- |
| 服务覆盖 | 以 hcloud 上下文、安全执行、本地 metadata、ECS 创建计划和 ECS job 轮询为主 | 增加 ECS、VPC、RDS、IMS、EVS、EIP、ELB、NAT、KPS、IAM、CCE、CDN、DNS、SCM、OBS、CES 的 registry、只读查询、readiness 或专项适配 |
| 查询能力 | 主要依赖通用 hcloud 命令和 ECS 相关脚本 | 增加 registry 驱动的 list 查询、显式参数的 Show*/detail 查询、大小写/别名 operation 解析、list-then-detail 抽样 |
| 变更安全 | ECS 创建计划和 dry-run 防护较完整，其他服务主要靠人工判断 | 增加 EIP 专用 Plan -> dry-run -> guarded submit -> verify flow，以及 VPC/ELB/EVS/NAT/RDS/CDN/DNS/SCM 通用 guarded change flow |
| 后置验证 | ECS job 轮询为主，容易把 job 终态和资源可用性混在一起 | 明确区分 job terminal state 和资源终态；新增 ECS ACTIVE 验证、多服务 JSON verifier、资源级 Show* 后置验证和服务级 readiness |
| OBS | 不作为普通服务处理 | 新增 `hcloud obs`/obsutil 专用只读和 planner-only 变更适配器，并记录 OBS 独立凭证配置要求 |
| 错误处理 | 能包装执行和脱敏，但失败原因偏粗 | `hcloud_safe_exec.py` 增加机器可读 `error_details`，覆盖 credential、permission、region/project、quota、parameter、not_found、network、metadata 等常见类别 |
| 数据驱动回归 | 基础单测和参考资料 | 增加 `generated_questions`、`data.xlsx` 覆盖检查、materials drift、registry 契约、CLI mock、多服务工具测试和手工验证记录 |

### 主要新增能力

#### 1. 多服务 registry 和数据集覆盖

- 新增 `references/service-registry.json`，统一登记服务覆盖、query operation、resource query operation、change operation、planner、change flow、verifier 和 known limits。
- 新增 `scripts/check_question_coverage.py`，用 `generated_questions` 和 `data.xlsx` 检查 schema、风险分类、registry 覆盖、人工验证步骤风险线索和已注册验证 operation 的执行路径。
- 当前数据集检查覆盖 26 个 generated question 文件、448 个唯一 operation、38 条 Excel E2E 记录；已注册 validation operation 的执行路径错误数为 0。

#### 2. 只读查询和 readiness 广度扩展

- 新增 `scripts/hcloud_resource_discovery.py`，按 registry 生成或执行 list-only 查询。
- 新增 `scripts/hcloud_resource_query.py`，对需要资源 ID 的 Show*/detail 查询要求显式参数，避免猜测目标资源。
- 新增 `scripts/hcloud_service_readiness.py`，按服务批量生成或执行只读 readiness 检查。
- 新增 `scripts/hcloud_readonly_smoke.py` 和 `scripts/hcloud_resource_detail_probe.py`，用于多服务 smoke 和 list-then-detail 抽样。
- 默认 readiness 顺序按高频服务广度优先覆盖 ECS、VPC、RDS、IMS、EVS、EIP、ELB、NAT、KPS、IAM，并补充 CCE、CDN、DNS、SCM、OBS、CES。

#### 3. ECS 执行闭环加强

- `scripts/hcloud_ecs_create_plan.py` 增加创建数量风险保护、占位符检测、JSON-friendly 命令输出和 shell 命令输出。
- 新增 `scripts/hcloud_ecs_verify_active.py`，用 `ListServersDetails` 验证 ECS 实例进入 `ACTIVE`。
- `scripts/hcloud_ecs_wait_job.py` 明确输出 `verification_scope=job_terminal_only`，避免把 job 成功误报为 ECS 可用。

#### 4. 变更类安全门禁

- 新增 `scripts/hcloud_change_plan.py` 和 `scripts/hcloud_service_change_plan.py`，提供通用风险分类、dry-run/submit 命令生成、服务上下文和后置验证建议。
- 新增 `scripts/hcloud_eip_change_flow.py`，把 EIP 变更串成 Plan -> dry-run -> guarded submit -> `ShowPublicip` verify。
- 新增 `scripts/hcloud_guarded_change_flow.py`，为 VPC、ELB、EVS、NAT、RDS、CDN、DNS、SCM 提供通用 P0 风险门禁。
- 通用 guarded flow 现在支持资源级 Show* 后置验证：可通过 submit 结果提取资源 ID，也可用 `--verify-param KEY=VALUE` 显式传入；没有目标 ID 时返回 `missing_params`，不会猜测资源。
- 所有真实 submit 仍需要显式 `--execute-submit --confirm-submit`；medium/high 风险操作需要先 dry-run 或显式 `--skip-dryrun`。

#### 5. OBS 专项适配

- 新增 `scripts/hcloud_obs_readonly.py`，支持 OBS `ListBuckets`、`StatBucket`、`GetBucketLifecycle`、`GetBucketPolicy`。
- 新增 `scripts/hcloud_obs_change_plan.py`，支持 OBS bucket/lifecycle/policy 变更的 planner-only 命令和后置验证计划。
- 明确 OBS 使用 `hcloud obs`/obsutil 命令形态，不走普通 `hcloud <Service> <Operation>` metadata 路线。
- README 已补充用户需要协助配置的普通 hcloud OpenAPI profile 和 OBS obsutil 凭证项。

#### 6. 错误诊断和可审计执行

- `scripts/hcloud_safe_exec.py` 增加结构化脱敏和 `error_details`。
- 新增 `scripts/hcloud_run_journal.py`，支持 JSONL run journal 汇总。
- 常见错误会被归类并给出下一步建议，方便 agent 判断是配置、权限、区域、项目、参数、配额、网络还是云 API 问题。

#### 7. 文档、playbook 和验证资产

- 新增或扩展 ECS、EIP、ELB、EVS、RDS、OBS、VPC、IMS、KPS、Docker Remote API、resource idempotency 等 playbook。
- README、SKILL、service coverage 和 manual validation 记录已同步更新。
- 新增架构契约测试、多服务工具测试、ECS 创建/等待/ACTIVE 验证测试、safe exec 测试和 metadata lookup 测试。

### 验证结果

v0.2 发布前已完成以下验证：

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests`：94 个单测通过。
- `python3 -m json.tool references/service-registry.json`：registry JSON 校验通过。
- `python3 scripts/check_materials_drift.py --pretty`：整理后的 references 与原始材料映射未发现漂移。
- `python3 scripts/check_question_coverage.py --pretty`：generated_questions 和 data.xlsx 覆盖检查通过，执行路径错误数为 0。
- `git diff --check`：无空白格式问题。
- VPC / ELB / EVS / NAT / RDS / CDN / DNS / SCM guarded flow plan-mode 矩阵通过，均能生成对应资源级 Show* 验证计划。
- 多轮 live read-only 抽样已覆盖 VPC、EIP、RDS、ELB、EVS、NAT、CCE、CDN、DNS、SCM、CES、ECS、IMS、KPS、IAM；OBS 在用户重新配置 obsutil 凭证后通过 bucket list 和 bucket stat 只读验证。

### 兼容性和迁移

- `SKILL.md` 元数据版本为 `0.2.0`。
- v0.1 的核心入口仍保留，包括 context inspect、safe exec、metadata lookup、ECS create plan、ECS job wait、references 和 examples。
- 新增脚本默认都是 plan-only 或 read-only；真实云资源创建、修改、绑定、解绑、删除仍必须显式确认。
- 对需要资源 ID 的 detail 查询，v0.2 更严格：缺少目标 ID 会返回缺参，不会用模糊列表结果代替目标资源验证。

### 已知限制

- 非 ECS 服务的很多 KooCLI operation detail 在本地 metadata 中仍不完整，v0.2 因此采用显式参数白名单和 planner-first 策略。
- 通用 guarded flow 只能确认基础资源级 Show* 状态；复杂业务语义仍需要服务专用 verifier 继续扩展。
- OBS 使用 obsutil 凭证体系，可能与普通 OpenAPI hcloud profile 不一致。
- CDN KooCLI 查询需要使用支持的 CLI region，registry 会把不支持的区域解析到 `cn-north-1` 或其它登记区域。
- 当前发布没有自动执行真实写操作；所有写类能力都保留确认门禁。
