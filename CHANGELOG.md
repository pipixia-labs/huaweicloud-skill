# Changelog

## Unreleased

## 0.9.7 - 2026-08-18

- Defined a minimum Agent CLI contract across the 54 real runtime entrypoints while keeping the richer artifact receipt limited to large or selected structured results.
- Added one internal read-only accessor for paired operation behavior and dependency evidence, preserving the existing profile files as authoritative sources.

## 0.9.6 - 2026-08-18

- Added portable POSIX and Windows `hcloud-skill` entrypoints so bundled scripts can run independently of the host working directory.
- Added maintained-document CLI drift checks and corrected stale EIP, IAM safe-exec, and OBS planner examples.
- Added a credential-free Linux CI workflow for offline tests, Ruff, compilation, entrypoint smoke, and whitespace checks.
- Added scope-bound private checkpoints and optional per-run time budgets for account inventory and Billing pagination, allowing interrupted reads to resume without repeating completed checks or accepted pages.

## 0.9.5 - 2026-08-18

- 新增 operation-specific 批量/异步行为证据和本地覆盖矩阵入口；ECS 创建/批量删除与 EIP 批量删除的 submit receipt 不再被解释为逐项完成，Agent 可直接按 profile 轮询和回读，无需公共轮询框架。
- 扩展 EVS、ELB、RDS、DNS 的批量/异步结果语义；新增高频资源结构化依赖证据、本地 inspector 和跨 Agent 场景/记录/汇总工具，均不执行工作流或真实云操作。

- 重写后端选择契约：默认优先级为 `hcloud > SDK > Terraform`，SDK 成为受支持的程序化路径，
  Terraform 只由 IaC/import/drift/长期纳管意图触发；高频脚本是可选捷径，不是第四种后端。
- 将任务持久化、场景路由和确认交互改为宿主能力自适应：优先复用宿主持久 task state，有 workspace
  时可保存最小任务文件，明确目标可跳过 router，Skill 不要求平台专属函数名。
- 将 `hcloud_sdk_readonly.py` 和 `sdk-supplement-registry.json` 收窄为便捷只读 runner 契约；registry
  不再被描述为 Agent 任务专用 SDK 代码的全局白名单。
- 新增公共脚本分类和 `huaweicloud_skill_public_result_v1` 回执；11 个高价值查询、盘点、验证和验收
  入口支持 `--output-file`，未指定时保持完整 JSON stdout，指定时完整结果私有落盘并返回紧凑回执。
- 统一公共 outcome 为 `planned`、`succeeded`、`partially_succeeded`、`failed`、`outcome_unknown`，
  并区分脚本 `success`、环境 `ready` 和领域完成状态；账号盘点与账单入口复用同一回执实现。
- 新增可移植的任务级依赖契约；environment doctor 只检查当前声明的 hcloud、服务 SDK、Terraform、
  OBS、网络和 artifact 目录，SDK 未声明具体服务时不执行无边界 package 扫描。
- 新增纯本地 KooCLI 请求预检：复用 resolver 的精确 API 版本与官方 SDK 静态嵌套 schema，在
  dry-run/submit 前发现 JSON 外层、参数位置、required 和类型错误；SDK 缺失/截断保持部分证据，
  未知字段只告警。通用 change plan 对 JSON 请求自动附带预检结果。
- 修复区域 `project_id` 的 IAM fallback 参数传递：以单 token 传递带连字符的 hcloud 子参数，并优先按
  结构化错误类型分类，避免本地 argparse 帮助文本中的 `--timeout TIMEOUT` 被误报为 IAM 网络超时。

## 0.9.4 - 2026-08-17

- 账号盘点与账单查询改为可移植的 Skill CLI 入口，不再依赖 runtime 专属的只读 capability Function Calling；删除两项只读 `capabilities.json` 声明。
- 两个宽泛查询入口新增 `--output-file`：完整 JSON 原样、原子地写入 `0600` 文件，stdout 返回紧凑状态、摘要和文件回执；未指定时继续输出完整 JSON。
- 账号盘点在执行模式按区域只解析一次 `project_id`，默认用有限并发完成独立服务查询，IAM 解析失败时一次性标记该区域的项目级检查，不再由每个 hcloud 子进程重复探测。
- Billing live-read 现在在固定页数、记录数、payload 和总超时上限内自动完成 BSS 分页，跨页校验 scope、币种、顶层金额元数据与 `total_count`，完整后用 Decimal 生成 `verified_monetary_totals`；后续页失败或不一致时返回 `partially_succeeded`，不再把第一页小计暴露为可声明总额。
- Billing live-read 的 execute 结果新增与 `success` 一致的 `outcome_status`，可由 runtime 区分业务成功与进程退出状态；hcloud 仍是主后端，未引入 SDK 替代路径。

## 0.9.3 - 2026-08-04

- 修复 `hcloud_safe_exec.py` 直接 CLI 的裸 `--arg` 参数：service/operation 模式自动补齐缺失的 `--`，已有长/短选项保持不变；generic command-part 继续保留 `obs://` 等位置参数，空值、首尾空白和多行 token 在启动 hcloud 前拒绝。
- 新增外部执行层回归清单，将参数、脱敏、错误、输出、版本、变更门禁、受控 live、MaaS 兼容性和性能观察分层记录，并要求精确 commit、环境、分子/分母和责任归因，不沿用不可复算的单一总分。
- 将业务 API 默认经 safe_exec、代码直调仅限版本/帮助/元数据预热的边界写入 machine-readable audience manifest；仍保留有证据的窄范围 Agent fallback，不新增服务/API/参数顺序白名单。
- 澄清普通 task/证据 artifact 与 `0600` 受限 credential artifact 的边界；修复旧 Qwen MaaS 兼容入口可能从 HTTP 错误正文泄露 API Key 的问题。
- 成熟度审计新增 curation、目标闭环档案和 live-smoke 证据来源摘要；缺时间和来源时明确 freshness unknown，不把规划档案描述成最近实测。
- 修复 Progress 模板与统一契约的字段词面漂移，保留“阻塞、未知或遗留”的细分语义，同时恢复统一“当前缺口”标签。
- metadata-backed 只读 smoke 的 record 与 confidence suggestion 现在共用观测时间，并自动携带受限的 Skill revision、工作树状态和非敏感运行环境；无独立 Git 身份时保持 unknown，不借用父仓库 commit，也不保存 profile、project ID、binary path 或原始版本输出。
- 成熟度审计把普通 evidence source 与具体 source revision 分开计数；只有时间、来源、源码 revision 和环境均存在时才计为完整 provenance。

## 0.9.2 - 2026-08-02

- 为复杂任务增加可移植 task 身份：运行时 task ID 对 Agent 可见时原样记录，不可见时首次建档生成稳定描述符并标记 `task_id_source`，后续轮次从 workspace 复用；描述符不冒充平台 ID，也不用于平台 API。
- 增加 Plus 行为评测协议、固定场景和逐次证据口径，记录 task 落盘、多轮更新、任务隔离、副作用收敛、自主调整、简单任务负担和未观察项；小样本结论不外推到未覆盖的 Agent、模型或场景。
- 恢复企业网站、跨服务资源盘点和成本治理的可选目标能力指南，并明确它是引用既有事实源的派生视图，不固定服务组合、API、参数或调用顺序。
- 新增 Goal、Option、Progress、Recovery、Completion 按需用户投影，以及目标、完成条件、证据、未知和遗留事项的轻量组织建议；不新增五个强制文件或固定状态机。
- 扩展知识所有权和渐进披露：区分权威事实、编写知识、派生视图和运行时事实，明确 registry、catalog、router、guide、playbook、task/artifact 的单一事实来源和六层加载路径。
- 将 Plus 范围收敛为一个对话/task 内的跨服务、跨场景和多轮一致性，统一 `task -> phase -> step -> operation` 术语，subtask 保持 Agent 自主可选；不建设跨 task workload、长期偏好、跨 Agent 交接、Agent 适配，也不继续扩展现有 P2 能力。
- 在主架构文档增加共享机制因果矩阵，说明共享原则、task 记忆、逻辑资源收敛、目标组织、用户投影和知识管线如何改善一致性，同时保留 Agent 自主执行和 v0.8.2 大输出保护。

## 0.9.1 - 2026-08-02

- 根据 CloudClaw 真实多轮任务反馈，补充复杂任务记忆的精简生命周期：同一 task 从简单查询升级后立即重新分类，并在下一项实质规划或执行前建立记录；重要变化及时更新，恢复时先读取。默认保持单任务入口和 Agent 自主执行，云/API 大输出继续只保存为独立 artifact。
- 为付费、有副作用、异步和恢复类任务增加轻量资源生命周期摘要，按需记录逻辑角色、预期数量、canonical 资源、待决操作和最近核验时间；结果未知时先回读收敛，避免为同一用户目标重复创建资源。
- 明确受控一换一替换边界：删除 job 和旧资源状态未确认前不创建同角色替代资源；连续替换、资源并存或数量、费用、安全暴露和破坏范围变化时重新说明并确认。
- 补充 ECS 重建前诊断和秘密输出边界：优先核验 job、网络、安全组、凭据、cloud-init、服务与日志；私钥不得经过普通 stdout/stderr 或平台普通日志。
- 扩展统一机制契约和行为场景，覆盖 task 升级、逻辑资源收敛、重复 ECS、受控替换和敏感输出，同时继续验证简单任务负担与 Agent 自主性。

## 0.9.0 - 2026-08-01

- 新增轻量跨服务共享原则，统一目标变化、事实来源、信息时效、完成语义和证据表达，同时明确这些语义不是固定状态机，也不替 Agent 选择服务、工具、参数和调用顺序。
- 新增 Agent task workspace 指南和可选任务模板：复杂、多轮、跨服务、有副作用、异步或可中断任务必须实际写入 Agent 自己的 workspace；同时支持运行时 task 级 workspace 和多个 task 共用 workspace 两种隔离方式。
- 新增企业网站目标—能力组织样例，演示如何从用户目标组织跨服务候选、替代路径、前置条件、缺口和验收，而不是从单一服务或固定服务链出发。
- 新增统一机制契约测试和多轮行为验证场景，覆盖用户修改目标、未知环境变化、上下文恢复、任务隔离、结论依据和简单任务负担。
- 根据 CloudClaw 本地验证反馈进一步强调：运行时待办、对话 context 和平台自动日志不能代替 Skill 要求的 workspace 任务记录。
- 补充 v0.9.0 当前实施文档并同步开发者架构、技术概览、实现边界和收益分析；现有 hcloud-first、大输出保护、变更确认、脱敏和后置验证门禁保持不变。

## 0.8.2 - 2026-07-31

- MaaS 批量站点图片脚本支持为每个图片声明稳定 `id`，逐项输出开始、成功和失败进度；单项完整落盘后才发送成功检查点，方便宿主平台安全保留已完成图片并只重试缺失项。
- 网站部署场景新增结构化架构决策：优先保留用户明确指定的机器、ECS、OBS 和公网 IP 约束；托管方式不明确或约束冲突时先澄清并阻止资源变更；补齐 ECS + EIP 部署闭环和 OBS 正式交付边界。
- Billing planner 改为按 BSS operation 能力生成 `X-Language`：支持该 Header 的接口保留 `zh_CN` / `en_US`，其余接口省略；`cli-lang` 只作为 KooCLI profile 配置，不再进入 API 命令。
- 新增运行时中立的可选账号盘点 capability 契约；支持声明式 capability 的运行时可使用固定入口和结构化结果，不支持时保持脚本直调兼容。
- 明确大输出 operation 必须先进入输出策略，且确认公网网站方案后仅允许规划精确的 TCP `80/443` 公网入口；原有确认、回读和协议验证门禁保持不变。

## 0.8.1 - 2026-07-24

- Skill 默认运行不再发现父目录中的参考仓库：账单差距检查改用内置规范化基线，问题覆盖使用内置最小回归样例，SDK/Provider/完整问题集仅接受显式维护路径；同时增加独立安装架构契约。
- 生成 catalog 现在保留 operation 的逐版本参数和请求信息；新增 `hcloud_operation_resolver.py`，让普通直接 `hcloud` 命令按实参生成显式 `Operation/vN`，高风险大输出读操作则生成带显式版本的 safe-exec 命令。
- `hcloud_safe_exec.py` 和 `hcloud_resource_query.py` 接入统一版本解析；只读命令仅在明确的版本/参数使用错误时允许一次受限纠正，mutation 不自动重放。
- 新增机器可读的大输出策略，覆盖大列表、日志/事件、时序指标、全租户记录和内容/下载操作；`hcloud_safe_exec.py` 默认自动分页、摘要或落盘，并对不安全的 full 请求返回可执行纠正命令。
- 成功解析的 JSON 不再和 raw stdout 重复回显；超阈值 `parsed_json` 会变成包含 schema、数组计数和少量样本的摘要。LTS `ListLogs` 现在会把入口 `--limit` 传到实际查询。

## 0.8.0 - 2026-07-24

- 为受限 sandbox 中启动的 hcloud 子进程补齐非敏感 `USER` / `HOME` 默认值，同时保留运行时已经注入的环境，避免 KooCLI 因最小环境缺少用户目录信息而启动失败。
- 深化 CCI、CCE、UCS、Flexus/COC、DWS、ModelArts 和 ICP 场景的专家证据链，补充证据顺序、语义边界、误判防护、完成状态和停止条件。
- 按既定退役节奏将 7 个旧 closure、acceptance 和 MaaS 命名入口标记为 deprecated；文件继续兼容，新的文档、路由和示例统一使用收敛后的入口。
- EIP 验收示例迁移到 `hcloud_closure_plan.py` 和 `hcloud_acceptance_closure.py`，并增加架构契约测试防止活跃文档重新引用旧入口。

## 0.7.2 - 2026-07-23

- 刷新 hcloud metadata-backed catalog：默认运行时排除 HCS/ManageOne 私有云控制面，保留 AgentArts 公有云覆盖，更新为 199 个服务、15,702 个 operation。
- BSS 写操作（包括计费周期转换）进入 hard manual gate，只读 Billing/BSS 路径保持不变。
- 生成的本地脚本命令改用当前 Python 解释器；环境体检增加 Windows PowerShell/KooCLI、Python、Terraform 和 obsutil 指引。
- 场景路由为 OBS 静态站点、可观测、成本治理和容器镜像部署返回结构化输入、证据、输出与风险契约。
- 新增 CCI 工作负载前检与证据 planner：按 namespace、Network、quota/events、workload、Pod、Service、协议探测顺序组织只读证据，并拦截删除、公网暴露、保留网段和不一致的资源 request/limit。

## 0.7.1 - 2026-07-05

- 优化 README 定位表达，突出一个大 Skill、hcloud CLI-first、风险门禁、证据闭环和 300+ 离线测试的项目价值。
- Acceptance probe 执行增加目标安全策略：元数据/link-local 目标 hard-block，内网、loopback 和 `.local` 目标需要 `--allow-private-targets` 显式确认，HTTP probe 不跟随重定向。
- `references/versioning-policy.md` 增加兼容入口退役节奏，用 v0.8/v0.9/v1.0 分阶段把 facade 过渡到真正收敛。
- 新增 `hcloud_billing_live_read.py`，把 Billing/BSS request planner、safe_exec 和脱敏 summarizer 串成显式确认的只读 live-read wrapper；默认只计划，执行时要求 `READ_BILLING_DATA` 确认并限制分页。
- 修正 Billing/BSS hcloud 命令计划的语言参数：KooCLI 7.2.2 的 BSS operation 使用 `--X-Language=zh_CN`，不是 `--cli-lang=cn`。
- 新增 `hcloud_billing_operation_gap.py`，对比官方 billing-scout / business-support-query 与本地 BSS planner 的 operation 覆盖，输出 P1/P2 缺口和 pricing helper 参考。
- 扩展 Billing/BSS 只读 planner，新增 `usage-summary` / `usage-detail`，覆盖 `ListResourceUsageSummary` 和 `ListResourceUsage` 的 95 计费用量汇总与明细查询计划。
- 扩展 Billing/BSS 只读 planner，新增 `on-demand-pricing` / `period-pricing`，覆盖官方 BSS 按需与包周期询价 API 的保守 request spec 和 reviewed safe_exec 命令计划。
- 新增 `hcloud_ces_datapoint_plan.py`，生成并可执行受限的 CES `BatchListMetricData` 只读 datapoint 查询计划，并对空数据、Agent、namespace、period、dimension 等常见排障原因做本地判读。

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
