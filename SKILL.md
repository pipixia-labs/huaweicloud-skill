---
name: huaweicloud-skill
description: 使用 hcloud 命令行工具执行华为云资源查询、分析和变更规划；也支持 MaaS 模型、图像和视频任务的计划与只读治理查询。它是可被任意 Agent 直接加载的标准 Skill；当前未接入 Skill 内部受控入口的变更一律为 plan-only，适用于 CLI/KooCLI 云资源操作、认证排查、命令构造、执行验证和安全变更规划。
---

# Huawei CLI Skill

## 核心定位

- 单一 skill 覆盖华为云上云、用云、管云场景，默认以租户体验和可验证闭环为中心。
- `hcloud` 是云资源查询、执行、回读和验收的主链路；没有可用 `hcloud` 时，不宣称已经查询或修改云资源。
- Agent 默认不要自行拼接或直接执行裸 `hcloud` 命令；优先调用本 skill 提供的脚本，让脚本统一处理版本选择、参数构造、脱敏、输出收敛、错误分类和纠正重试。
- SDK 只做窄范围补充，例如参数、region/endpoint、错误结构、凭证来源线索，或 allowlist 内的稳定只读查询。
- Terraform 是辅助 IaC 面，只在用户明确需要可重复创建、环境复制、长期纳管、import 或 drift review 时进入；不能跳过 hcloud 发现和后置验证。
- MaaS 是 API-first 能力面。模型调用使用 MaaS API Key；用量统计是治理查询，按本地 AK/SK 签名规划处理。不要让用户在对话里粘贴密钥。
- 目标不是背命令，而是稳定完成：识别上下文 -> 发现资源/operation -> 构造安全命令 -> 查询或变更 -> 回读验证 -> 处理错误。
- **M2.5 运行时边界**：通用 hcloud mutation、旧 guarded submit/dry-run、Terraform 状态变更和 MaaS 生成目前均由代码强制为 `plan_only`。用户对当前计划的明确确认是未来受控提交的必要条件，但当前不会触发真实提交；只有已证明只读的查询可执行。ECS 密钥对私网子集与 DNS A 记录已有本地请求映射准备；当前 handoff 试验产物不属于目标架构、也不能提升为提交权限。后续提交、回读和验证将由 Skill 内部入口完成，不要求任何 Agent 改造。

## 什么时候使用

优先在这些场景使用本 skill：

- 用户提到华为云、`hcloud`、KooCLI、CLI、命令行、云资源查询、创建、变更、排障或治理。
- 用户需要查看 service/operation、构造 `--cli-jsonInput`、使用 `--cli-query`、`--dryrun`、`--cli-waiter` 等 CLI 能力。
- 用户需要华为云认证、region/project、profile、meta cache、网络或输出格式排查。
- 用户明确需要 Terraform/IaC、MaaS 大模型/图像/视频，或华为云 Web/OBS/CDN/ECS 站点资产辅助。

不要把本 skill 当成通用云知识问答、通用 SDK 执行器、通用 Terraform apply 器，或非华为模型服务兜底。

## 默认工作流

1. 先确认环境和上下文：
   - 首选 `python3 scripts/hcloud_environment_doctor.py --pretty` 或 `python3 scripts/hcloud_context_inspect.py --pretty`。
   - doctor/context 只能观察当前进程环境和本地 profile；未观察到 AK/SK 或 MaaS API Key 只表示配置状态未知，不得断言用户未配置。使用凭据 broker 的运行时可能只在受授权的执行子进程中注入凭据。
   - 需要项目级服务的 `project_id` 时，用 `python3 scripts/hcloud_project_resolve.py --region=<region> --pretty`，按显式值、环境变量、本地 profile 缓存、IAM `KeystoneListProjects` 的顺序解析；不要因为 IAM SDK 未安装而改写签名请求。
   - 若 `hcloud.found=false`，停止真实云查询和变更，只能给本地方案草稿和安装指引。
2. 宽泛目标和网站部署先路由：
   - 用 `hcloud_scenario_router.py` 找到本地 playbook、guide、planner、SDK supplement 和 Terraform 候选。
   - **任何网站部署任务**在决定架构、生成 MaaS 图片/视频、创建云资源、上传站点或暴露公网前，必须先运行路由；先读取顶层 `architecture_decision`，再看 `matches`。路由只约束对用户原话的忠实解释，不替 agent 预设 ECS、OBS、Flexus 或具体规格。
   - 网站部署任务先读取顶层 `architecture_decision`，再看 `matches`。`explicit_constraints` 是用户约束，不是成本优化提示；用户指定机器、ECS、公网 IP、SSH、Nginx 或 Docker 时，不得自动改成 OBS。
   - `change_execution_blocked=true` 时，原样围绕 `clarification_question` 澄清运行载体或动态能力；确认前禁止生成或执行创建、购买、上传、公开访问等变更。`change_execution_blocked=false` 只表示当前不需要架构澄清，**不表示用户已授权执行**。
   - 网站任务涉及资源计费、公网暴露、域名/DNS/HTTPS 或 MaaS 图片/视频调用时，先向用户给出一份合并方案再等待确认。方案至少说明：推荐架构与资源、region、网络和公网入口、域名/HTTPS 处理方式、MaaS 资产数量与用途、持续费用和主要风险；未知项优先给出保守默认值和可选改动。用户首条“帮我搭建/部署/上线”只授权规划和只读预检，不授权付费资源创建、MaaS API 调用、上传或公网暴露；即使用户确认，当前也只生成受审核计划，等待后续 Skill 内部服务专用受控入口。
   - 只读取命中的少量资料，不全量浏览 catalog、Terraform 示例或长 reference。
3. 查询类默认稳定化：
   - 账号级多服务盘点优先使用 `hcloud_account_inventory.py`。支持 Skill
     machine-readable contract 的运行时可以读取 `capabilities.json` 中的
     `huaweicloud.account_inventory.v1`；不支持时直接调用同一脚本。先检查当前
     runtime 实际提供的工具，不要臆造某个平台的 Tool 名称。
   - 调用优先级：专用场景脚本 -> `hcloud_resource_discovery.py` / `hcloud_resource_query.py` -> `hcloud_operation_resolver.py` / `hcloud_safe_exec.py`。只有帮助/诊断或脚本无法表达的窄范围操作才允许裸 `hcloud` 兜底；仍须从 resolver、meta cache 或 live help 取得版本和参数证据，不得凭猜测构造。
   - 多版本 operation 先用 `hcloud_operation_resolver.py` 按参数选择版本；普通小查询的直接 `hcloud` 命令显式写成 `Operation/vN`，命中大输出策略时解析器改为生成 `hcloud_safe_exec.py --output-mode=auto`。`hcloud_safe_exec.py` 和 `hcloud_resource_query.py` 已内置同一版本解析逻辑。
   - 以下 operation 均属于大输出；命中时禁止先执行裸 `hcloud` 试探响应大小，直接使用 `hcloud_safe_exec.py --output-mode=auto`：
     - 镜像、规格和资源列表：`IMS:ListImages`、`IMS:GlanceListImages`、`ECS:ListFlavors`、`ECS:ListFlavorSellPolicies`、`ECS:ListServersDetails`、`DNS:ListRecordSets`。
     - 日志、事件和指标：`LTS:ListLogs`、`CTS:ListTraces`、`CFW:ListAccessControlLogs`、`CFW:ListAttackLogs`、`CFW:ListFlowLogs`、`CES:BatchListMetricData`、`CES:BatchListSpecifiedMetricData`、`CES:ShowMetricData`。
     - 全租户和工作负载资源：`RMS:ListAllResources`、`RMS:ListResources`、`COC:ListResources`、`CCI:listCoreV1PodForAllNamespaces`、`CCI:listNamespacedPods`、`CCI:listCoreV1NamespacedPod`、`CCI:listCoreV1NamespacedEvent`、`CCI:listMetricsV1beta1NamespacedPodMetrics`、`SWR:ListRepositoryTags`。
     - 文件和下载：`CodeArtsRepo:ShowFileContent`、`CodeArtsRepo:ShowFileRaw`、`CodeArtsRepo:ShowReadmeFile`、`CodeArtsRepo:DownloadArchive`、`CodeArtsRepo:ShowRepositoryArchive`、`RDS:DownloadErrorlog`、`RDS:DownloadSlowlog`、`DDS:DownloadErrorlog`、`DDS:DownloadSlowlog`。
   - 以下命名规则同样直接按大输出处理，不允许先裸跑：下载/导出/文件内容/归档/diff/构建日志；日志/事件/审计/告警/历史；CES/AOM 指标、时序和采样点；BSS/RMS/COC/CONFIG/SECMASTER/HSS 的全租户 `List*`、`Search*`、`Query*`、聚合和资源历史 operation。
   - 命中大输出策略后，Agent 只读取摘要、数量、字段结构、少量样本和落盘路径；不得把完整列表、完整文件或完整 `parsed_json` 再输出到对话。
   - `OUTPUT_POLICY_REQUIRED` 不是云 API 失败；按返回的 `corrected_command` 或补齐 `corrected_command_template` 中的时间/范围参数后再执行一次，不要原样重试。
   - 返回为空不等于失败；必要时检查 region/project、过滤条件、权限和状态码。
4. 变更类先计划，当前不提交：
   - 先查现状证据，再生成 change plan / dry-run / guarded submit。
   - 按所选工具的真实结果契约解释输出。本 Skill 的 execute 脚本如果返回
     `outcome_status`，以该结构化字段为业务结果；裸 `hcloud`、帮助探测和其他
     未声明结构化结果的命令必须同时保留 stdout、stderr 和退出码，不能只因进程
     退出码为 `0` 就断言云操作成功。
   - 对可能产生费用或影响线上服务的云资源操作，先形成一套或多套候选方案。Agent 可以调用现有工具、专家能力或自行分析来制定方案；每套方案应说明目标资源、预期影响、持续费用（如适用）、主要风险和验证方式。
   - 将候选方案交由用户选择并明确确认；确认会绑定未来的执行意图，但当前不会执行对应操作。
   - 用户确认是未来真实 submit、Terraform 状态变更和计费型 MaaS 调用的必要条件，不是当前执行授权。M2.5 冻结期间，旧执行入口统一返回 `UNIFIED_RUNTIME_PLAN_ONLY`；安全、身份、密钥、治理类 mutation 另有 hard guard。
5. P0 高频服务闭环：
   - 先运行 `hcloud_closure_plan.py --tier lifecycle` 生成 lifecycle plan 和 `acceptance_evidence_plan`。
   - 再用 `hcloud_acceptance_closure.py plan/run/evaluate/chain` 做采证计划、受支持探测和 evidence 结果判定。
   - 做真实账号回归或服务晋级时，用 `hcloud_live_validation_plan.py` 列出 ECS/VPC/EIP/OBS/ELB/RDS 的目标输入、读回、probe 和晋级缺口。
6. 完成声明要诚实：
   - `job_id`、`accepted`、云侧 `ACTIVE`、Terraform plan 成功、MaaS `task_id` 都不等于业务可用。
   - 需要协议、健康、机内、日志、指标或用户路径证据时，必须说明已采集、缺失或被阻塞。

## 安全边界摘要

详细规则在 `references/runtime-safety-boundaries.md`。执行创建、变更、网络暴露、ECS 机内操作、COC/SSH fallback、应用验收或排障前先读取该 reference。

| 风险点 | 默认处理 |
| --- | --- |
| 凭据、AK/SK、API Key、私钥 | 不在对话、日志、manifest、站点代码中回显或保存；支持文档列出的同家族环境变量别名，不得跨家族拼接 AK/SK。命令/API 输出中的 `***`、`****` 或更多连续星号表示“值存在但已脱敏”，不表示缺失。 |
| 安全组入口 | SSH `22` 和开发端口不得开放到 `0.0.0.0/0`。用户确认公网网站方案后，直连 ECS 的精确 TCP `80/443` 可使用 `--allow-public-web` 规划；该参数不替代 submit 确认，复用安全组仍要读回规则并做外网协议探测。 |
| 异步云任务 | 跟到 job 终态，再做资源状态、协议或业务验收。 |
| Terraform 状态 | import/state/remote state 是高影响操作；当前统一为 plan-only，不能自动 apply/destroy。 |
| MaaS 视频和异步任务 | 生成目前为 plan-only；已存在的 `task_id` 只可查询终态，且不代表完成。 |
| 账单/成本 | 不从资源清单推断费用；账单结果要脱敏、区分 fact/grain/money basis/scope。 |
| 自动 live probe | 只执行 plan 派生的 HTTP/TCP/DNS/TLS；元数据/link-local 目标拒绝，内网/localhost 需显式确认。 |
| 结果叙事 | 只描述真实发生的命令、输出和验证；不要编造失败-恢复过程或把计划态写成已执行。 |

## 首选入口

完整脚本说明和命令模板在 `references/scripts.md`。这里仅保留默认入口，避免在运行时让模型浏览长脚本表。

| 任务 | 首选入口 |
| --- | --- |
| 环境、认证、profile、region/project | `hcloud_environment_doctor.py`、`hcloud_context_inspect.py`、`hcloud_project_resolve.py` |
| 自然语言场景路由 | `hcloud_scenario_router.py` |
| hcloud 版本选择、真实查询或受控系统命令 | `hcloud_operation_resolver.py`、`hcloud_safe_exec.py` |
| 多服务发现、目标查询、readiness/live validation（含 CCI 工作负载前检） | `hcloud_resource_discovery.py`、`hcloud_resource_query.py`、`hcloud_service_readiness.py`、`hcloud_live_validation_plan.py`、`hcloud_cci_workload_plan.py` |
| 创建/变更计划和 guarded flow（当前 plan-only） | `hcloud_change_plan.py`、`hcloud_service_change_plan.py`、`hcloud_guarded_change_flow.py` |
| P0/P1/P2 闭环计划和验收 | `hcloud_closure_plan.py`、`hcloud_acceptance_closure.py` |
| 盘点、闲置、成本、治理 | `hcloud_account_inventory.py`、`hcloud_idle_audit.py`、`hcloud_billing_readonly.py`、`hcloud_billing_live_read.py` |
| Terraform/IaC | `hcloud_terraform_context_inspect.py`、`hcloud_terraform_router.py`、`hcloud_terraform_operations_plan.py` |
| MaaS 计划、模型目录和用量治理 | `maas_models.py`、`maas_chat.py`、`maas_image_generation.py`、`maas_video_generation.py`、`maas_usage_request_plan.py`（生成/对话当前 plan-only） |
| 脚本边界、维护分层、完整命令模板 | `references/scripts.md`、`references/script-audience-manifest.json` |

## 资料入口

按任务需要读取，不要一次性加载所有资料：

- 基础流程和安全：`references/workflow.md`、`references/runtime-safety-boundaries.md`、`references/auth-and-context.md`
- 场景路由和服务资料：`references/scenario-router.json`、`references/guides/`、`references/playbooks/`
- 命令构造和错误处理：`references/command-construction.md`、`references/error-playbook.md`、`references/output-and-query.md`、`references/hcloud-output-policies.json`
- 可选机器契约：`references/capability-contracts.md`、`capabilities.json`
- 脚本索引和受众边界：`references/scripts.md`、`references/script-audience-manifest.json`、`references/controlled-adapters.md`（其中记录已废弃的宿主交接试验及 Skill 内部闭环目标）
- Terraform：`references/terraform-workflow.md`、`references/terraform/README.md`、`references/terraform/operations.md`
- MaaS：`references/maas-model-calls.md`、`references/playbooks/maas-api-readiness.md`、`references/playbooks/maas-usage-governance.md`
- 覆盖和晋级：`references/service-coverage.md`、`references/service-curation-profiles.json`、`references/live-validation-profiles.json`、`hcloud_closure_maturity_audit.py`
- 版本事实：`references/versioning-policy.md`、`CHANGELOG.md`、`RELEASE_NOTES.md`
- 溯源和材料：`references/source-map.md`、`references/materials-sources.json`

原始 KooCLI 材料在 `materials/` 下，仅作为资料源，不直接当最终指令集使用。涉及 API 字段语义时，以华为云官方文档和实际 `hcloud --dryrun`/查询结果为准。

## 能力边界

- ECS guidance 最完整，覆盖创建前校验、dry-run、job 终态、ACTIVE 回读、SSH 和应用验收。
- P0 高频服务有 lifecycle planner 和 acceptance closure；P1/P2 主要是 governance/scenario planner，不能说成完整执行闭环。
- OBS、MaaS、Billing、Terraform 都有专门边界：各自只在明确场景进入，不替代 hcloud 主链路。
- 长尾安全、数据库、治理、身份和 key 类服务多为 metadata-backed evidence gap；先做发现、计划和证据缺口，不默认执行 mutation。
- 自动 live probe 只支持内置 HTTP/TCP/DNS/TLS；内网、localhost 或 `.local` 目标必须带 `--allow-private-targets` 且来自已审阅的 evidence plan，其他 evidence 需要人工或专用工具采集后再 evaluate。
- 真实账号回归、Terraform state-changing import、计费资源创建/释放仍需要用户提供隔离环境、资源 ID、profile/region 和明确确认。
