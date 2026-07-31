# M2.5 试点提交准入准备

本记录描述 ECS 与 DNS 如何进入**提交准入准备**。它不是执行手册，也不授予云端提交权限；
真实提交仍必须等到 M2.5 收口、Skill 内部服务专用受控入口和独立验证全部完成；不得要求任一 Agent 提供专用认证/审计接口。

| 试点 | 当前 Action Spec | 准入准备所绑定的内容 | 已知缺口 | 当前结论 |
| --- | --- | --- | --- | --- |
| ECS 创建 Web 实例 | `ecs-create-server.json`，`curated` | 精确 catalog 引用、region/project、镜像/规格/子网等任务输入、费用/公网/异步预检证据、Action Plan 与确认指纹 | 旧通用分发已收口为 plan-only；仍没有 Skill 内部服务专用 hcloud 调用、提交前事实刷新和提交后验证 | 当前只能生成准备记录，不可 submit |
| DNS 创建记录集 | `dns-create-record-set.json`，`curated` | 精确 catalog 引用、region/project、zone/记录/TTL 等任务输入、记录冲突与网络范围预检证据、Action Plan 与确认指纹 | 旧通用分发已收口为 plan-only；不支持 dry-run 时还需由 Skill 内部入口明确记录替代验证路径、提交前事实刷新和读回 | 上下文仍列 `record_values` 为缺失时必须拒绝；刷新上下文后才可生成准备记录，仍不可 submit |

准备器不允许以 Execution Intent 悄悄覆盖 Cloud Context 的 `missing_inputs`。收集到输入后，
必须刷新 Context 和 Action Plan，再由确认绑定新的两个指纹。这是为了避免“用户确认的是旧计划，
实际提交的是补过参数的新目标”。

M2.5 真正完成前，以上两项仍受统一的限制：`submission_authority=not_implemented`、
`mode=plan_only`，不得把输出转换为 `hcloud` 命令、`command-part`、submit token 或旧入口调用。
