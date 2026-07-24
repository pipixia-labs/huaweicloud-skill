---
name: huaweicloud-skill
description: 使用 hcloud 命令行工具执行华为云资源查询、分析、规划和变更；也支持通过华为云 MaaS API 规划和调用大模型、图像理解、图片生成/编辑与视频生成任务。适用于 CLI/KooCLI 云资源操作、MaaS API 调用、认证排查、命令构造、执行验证和安全变更规划。
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
   - 若 `hcloud.found=false`，停止真实云查询和变更，只能给本地方案草稿和安装指引。
2. 宽泛目标先路由：
   - 用 `hcloud_scenario_router.py` 找到本地 playbook、guide、planner、SDK supplement 和 Terraform 候选。
   - 网站部署任务先读取顶层 `architecture_decision`，再看 `matches`。`explicit_constraints` 是用户约束，不是成本优化提示；用户指定机器、ECS、公网 IP、SSH、Nginx 或 Docker 时，不得自动改成 OBS。
   - `change_execution_blocked=true` 时，原样围绕 `clarification_question` 澄清运行载体或动态能力；确认前禁止生成或执行创建、购买、上传、公开访问等变更。
   - 只读取命中的少量资料，不全量浏览 catalog、Terraform 示例或长 reference。
3. 查询类默认稳定化：
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
4. 变更类先计划再执行：
   - 先查现状证据，再生成 change plan / dry-run / guarded submit。
   - 真实 submit 必须有本次操作的明确用户确认；安全、身份、密钥、治理类 mutation 默认 hard guard。
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
| 凭据、AK/SK、API Key、私钥 | 不在对话、日志、manifest、站点代码中回显或保存；让用户使用本地环境变量/profile。 |
| 安全组入口 | SSH/Web 常见端口不得自动开放到 `0.0.0.0/0`；复用已有安全组也要读回规则。 |
| 异步云任务 | 跟到 job 终态，再做资源状态、协议或业务验收。 |
| Terraform 状态 | import/state/remote state 是高影响操作；必须显式确认，不能自动 apply/destroy。 |
| MaaS 视频和异步任务 | `task_id` 只是受理凭据，必须查询终态。 |
| 账单/成本 | 不从资源清单推断费用；账单结果要脱敏、区分 fact/grain/money basis/scope。 |
| 自动 live probe | 只执行 plan 派生的 HTTP/TCP/DNS/TLS；元数据/link-local 目标拒绝，内网/localhost 需显式确认。 |
| 结果叙事 | 只描述真实发生的命令、输出和验证；不要编造失败-恢复过程或把计划态写成已执行。 |

## 首选入口

完整脚本说明和命令模板在 `references/scripts.md`。这里仅保留默认入口，避免在运行时让模型浏览长脚本表。

| 任务 | 首选入口 |
| --- | --- |
| 环境、认证、profile、region/project | `hcloud_environment_doctor.py`、`hcloud_context_inspect.py` |
| 自然语言场景路由 | `hcloud_scenario_router.py` |
| hcloud 版本选择、真实查询或受控系统命令 | `hcloud_operation_resolver.py`、`hcloud_safe_exec.py` |
| 多服务发现、目标查询、readiness/live validation（含 CCI 工作负载前检） | `hcloud_resource_discovery.py`、`hcloud_resource_query.py`、`hcloud_service_readiness.py`、`hcloud_live_validation_plan.py`、`hcloud_cci_workload_plan.py` |
| 创建/变更计划和 guarded flow | `hcloud_change_plan.py`、`hcloud_service_change_plan.py`、`hcloud_guarded_change_flow.py` |
| P0/P1/P2 闭环计划和验收 | `hcloud_closure_plan.py`、`hcloud_acceptance_closure.py` |
| 盘点、闲置、成本、治理 | `hcloud_account_inventory.py`、`hcloud_idle_audit.py`、`hcloud_billing_readonly.py`、`hcloud_billing_live_read.py` |
| Terraform/IaC | `hcloud_terraform_context_inspect.py`、`hcloud_terraform_router.py`、`hcloud_terraform_operations_plan.py` |
| MaaS 模型调用、图片/视频、用量治理 | `maas_models.py`、`maas_chat.py`、`maas_image_generation.py`、`maas_video_generation.py`、`maas_usage_request_plan.py` |
| 脚本边界、维护分层、完整命令模板 | `references/scripts.md`、`references/script-audience-manifest.json` |

## 资料入口

按任务需要读取，不要一次性加载所有资料：

- 基础流程和安全：`references/workflow.md`、`references/runtime-safety-boundaries.md`、`references/auth-and-context.md`
- 场景路由和服务资料：`references/scenario-router.json`、`references/guides/`、`references/playbooks/`
- 命令构造和错误处理：`references/command-construction.md`、`references/error-playbook.md`、`references/output-and-query.md`、`references/hcloud-output-policies.json`
- 脚本索引和受众边界：`references/scripts.md`、`references/script-audience-manifest.json`
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
