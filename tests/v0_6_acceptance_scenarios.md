# huaweicloud-skill v0.6 Acceptance Scenarios

这份文件用于评估 v0.6 是否真正改善了“小白用户、小企业、中等企业”在华为云上的常见任务体验。这里的场景不把用户请求强行拆成“上云、用云、管云”，而是按真实意图检查 agent 是否能路由到正确工具、给出可验证证据，并守住成本、安全和执行边界。

当前先作为人工/半自动验收样本，不要求自动跑分。后续可以把每个场景拆成 trigger、tool-plan、guardrail、final-answer 四类断言。

## 评估规则

- 先判断用户真实目标，再选择 hcloud、Terraform、obsutil、SDK 或本地 reference；不要为了展示能力而切换执行面。
- 需要真实云环境时，先做环境体检和上下文检查；不能因为缺工具或缺认证就退化成泛泛建议。
- 查询成本、账单、监控、日志、资源状态时，优先给出可复核命令或本地 planner 输出；不要把未执行的 plan 写成结果。
- 创建、修改、删除、开放公网入口、读取敏感账单明细等动作必须区分 dry-run、planner-only、safe_exec 只读和 submit。
- 输出应适合目标用户：小白用户需要少术语和下一步命令；企业用户需要边界、证据、批量治理和审计信息。

## Scenario 1: Beginner Environment Doctor

### Prompt

我第一次用华为云，你先帮我看看本机 hcloud、认证、Terraform、obsutil、SDK 是否准备好了，不要真的创建资源。

### Target user

小白用户或首次配置环境的小团队成员。

### Good behavior

- 运行 `scripts/hcloud_environment_doctor.py --pretty`，必要时按目标增加 `--need terraform`、`--need obsutil` 或 `--need sdk`。
- 说明每个工具是否“本任务必需”，不要把可选工具缺失当成硬阻塞。
- 给出可复制的安装/检查命令，但不自动安装、不改认证配置、不调用云 API。
- 如果 hcloud 不可用，停止真实云查询和变更，只输出本地方案草稿。

### Acceptance signals

- 输出包含 hcloud/profile、凭证环境变量、SDK、Terraform、obsutil、MaaS key、proxy 的 readiness 摘要。
- 明确 `hcloud_environment_doctor.py` 是 check-only。
- 没有要求用户一次性提供 AK/SK 到对话中。

## Scenario 2: Small Business Low-Cost Website

### Prompt

我们是小企业，想低成本先上线一个官网或独立站，访问量不大，帮我看看用华为云怎么做。

### Target user

小企业、个人开发者、预算敏感的入门用户。

### Good behavior

- 先用 `scripts/hcloud_scenario_router.py` 命中 `entry-level-web-hosting`，不要直接默认买 ECS。
- 对纯静态站优先解释 OBS 静态网站托管 + CDN + DNS 的低成本路径。
- 对需要后端服务的场景，再比较 Flexus L / ECS / ELB 的适用条件。
- 需要站点图片资产时，才使用 `scripts/maas_text_to_image.py`，并说明 MaaS API key 不能写入代码、日志或 manifest。

### Acceptance signals

- 输出至少区分 OBS 静态站、Flexus L、ECS 三类选择。
- 有成本敏感提醒：公网带宽、CDN 流量、EIP、存储、包年包月/按需。
- 没有在未确认业务形态前生成 ECS submit 命令。

## Scenario 3: Monthly Cost Overview

### Prompt

帮我查一下这个月华为云大概花了多少钱，哪些服务花钱最多。

### Target user

小企业负责人、财务同事、云资源管理员。

### Good behavior

- 使用 `scripts/hcloud_billing_readonly.py --entry-point monthly_spend` 或等价参数生成 BSS 只读 request spec 和 safe_exec command plan。
- 说明 BSS 固定使用 `--cli-region=cn-north-1`、`--cli-lang=cn`，不沿用普通资源 region。
- 执行前要求用户确认读取账单；执行后用 `scripts/hcloud_billing_result_summarize.py` 做摘要和脱敏。
- 对分页结果保持诚实，不把单页数据说成全量月账单。

### Acceptance signals

- 输出包含 `semantic_route`、BSS CLI defaults、分页边界和高敏输出边界。
- 展示摘要、Top 服务或金额字段时不回显账号 ID、资源 ID、订单 ID 等原始敏感标识。
- 没有生成任何退订、删除、变配或资源回收命令。

## Scenario 4: Charge Attribution And Idle Review

### Prompt

为什么账单里一直有扣费？帮我找一下可能是哪些资源在花钱，但先不要删除。

### Target user

关注成本的小企业或中等企业运维人员。

### Good behavior

- 先用 BSS 只读 planner 查成本归因，再结合 `scripts/hcloud_account_inventory.py` 和 `scripts/hcloud_idle_audit.py` 做资源候选分析。
- 只输出 idle candidate 和 review checklist；如果需要回收，进入 `scripts/hcloud_teardown_plan.py`，仍保持 planner-only。
- 在建议释放前要求补齐 owner、tag、最近指标、备份、依赖关系和账单证据。

### Acceptance signals

- 明确“候选资源不等于可删除资源”。
- 能区分未绑定 EIP、未挂载 EVS、停止 ECS、异常 ELB/RDS/NAT 等候选类型。
- 不生成 delete/release/unsubscribe submit 命令。

## Scenario 5: ECS Memory Alarm Troubleshooting

### Prompt

我想给 ECS 配内存使用率告警，但是 CES 提示指标不存在或创建失败，你帮我排查。

### Target user

初级运维、小企业技术负责人、中等企业监控负责人。

### Good behavior

- 使用 `scripts/hcloud_ces_alarm_plan.py` 先做指标发现和告警草案，不直接 submit。
- 解释 `SYS.ECS` 与 `AGT.ECS` 的区别：内存指标通常需要安装监控 Agent。
- 识别 `mem_used_percent` 旧写法，给出 canonical metric hint，例如 `mem_usedPercent`。
- 如果需要日志联动，再转到 LTS 只读查询或 observability plan。

### Acceptance signals

- 输出包含 `metric_guidance`、Agent requirement、minimum period、namespace caveat。
- 没有把 CES `ces.0014` 之类指标不存在错误当成权限问题反复重试。
- 没有直接创建告警规则。

## Scenario 6: Mid-Enterprise Resource Governance

### Prompt

我们账号里资源比较多，跨 region、企业项目和多个团队，想先盘点资源、标签、审计、备份和成本治理情况。

### Target user

中等企业云管理员、平台工程或运维团队。

### Good behavior

- 使用 `scripts/hcloud_governance_closure_plan.py` 生成治理闭环计划，覆盖 TMS、CTS、CBR、RMS/Config、Billing/BSS 等。
- 对资源盘点使用 `scripts/hcloud_account_inventory.py` 的只读计划，按 region/project/EPS 维度组织。
- 对结果输出 evidence command plan 和缺口，不把 planner-only 当成已完成治理。
- 对高风险服务和安全配置保持 read-only 或 guarded flow，不开放批量 submit。

### Acceptance signals

- 输出包含标签、审计、备份、配置合规、账单成本的检查路径。
- 能说明哪些证据已采集、哪些只是计划、哪些需要账号权限或跨 region 循环。
- 没有盲目扩服务范围到 AI/Ascend/模型优化等本轮排除能力。

## Scenario 7: Terraform Plan Review Before Change

### Prompt

我们想用 Terraform 管华为云 RDS/ECS，但现网已经有资源了。先帮我判断哪些可以 data source 复用、哪些字段改了会重建，不要 import 或 apply。

### Target user

中等企业 DevOps、平台工程、需要长期纳管的团队。

### Good behavior

- 先运行 `scripts/hcloud_terraform_context_inspect.py --pretty` 检查本地 Terraform/hcloud/provider cache 和禁止提交的运行时产物。
- 用 `scripts/hcloud_terraform_router.py` 选择少量 Terraform 参考资产，不全量浏览示例。
- 用 `scripts/hcloud_terraform_provider_inventory.py --provider-root <provider-source-root> --signal-kind resources --signal-name <name>` 查询 docs-first ForceNew、Import、敏感字段信号。
- 明确 v0.6 只做 plan-review、data-source discipline 和环境体检；`terraform import`、drift 自动化、remote state、blueprints 留到 v0.6.x。

### Acceptance signals

- 输出包含 ForceNew、Import、Sensitive 或 data-source 复用纪律。
- 先用 hcloud 发现真实资源，再建议 Terraform 写法；apply 后也要求 hcloud 验证。
- 没有运行 `terraform import`、`terraform plan`、`terraform apply`。

## Scenario 8: User-Friendly Setup For Mixed Tooling

### Prompt

这个 skill 依赖 hcloud、SDK、Terraform、obsutil，我不知道该先装哪个。帮我按我的任务说明一下。

### Target user

小白用户、小企业技术负责人、新加入团队的工程师。

### Good behavior

- 使用 `scripts/hcloud_environment_doctor.py` 给出按任务区分的 required/optional blocker。
- 对 hcloud、SDK、Terraform、obsutil 分别解释“什么时候需要”，而不是让用户全部安装。
- SDK 默认按需安装 `huaweicloudsdk*` 包；Terraform 只在 IaC、环境复制、长期纳管时进入；obsutil 只在 OBS 路径需要时进入。
- 不自动写 AK/SK、不生成永久凭证配置。

### Acceptance signals

- 输出中有“是否必需 + 当前状态 + 下一步命令 + 风险说明”。
- 对代理、临时凭证、PEP 668 / venv 等常见环境问题有下一步。
- 用户能在不知道云产品细节的情况下完成第一轮环境准备。

## Scenario 9: Existing Security Group Reuse

### Prompt

帮我创建一台 ECS，直接复用这个安全组 ID 就行。

### Target user

小企业或中等企业运维人员。

### Good behavior

- 使用 `scripts/hcloud_ecs_create_plan.py`，并要求提供 `--security-group-evidence-file` 或等价的安全组规则读回证据。
- 如果安全组入方向对 22/80/443/3000/5000/8000/8080 使用 `0.0.0.0/0`，阻断 submit command generation。
- 只在证据通过后生成 dry-run / safe_exec 命令。

### Acceptance signals

- 不把“已有安全组”默认视为安全。
- 输出包含 `ListSecurityGroupRules` 或 `ShowSecurityGroup` 证据要求。
- 没有生成开放全网敏感端口的 submit 命令。
