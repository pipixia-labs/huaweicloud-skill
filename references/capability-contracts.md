# 可选机器能力契约

`capabilities.json` 是本 Skill 提供的可选、平台无关机器契约。它让支持声明式
capability 的 Agent runtime 在不解析自然语言指令的情况下了解固定入口、参数边界、
凭据类别和结构化结果；不支持该文件的 runtime 可以忽略它，直接调用对应
`scripts/` 脚本。

## 职责边界

- Skill 拥有 capability ID、只读/变更风险、业务参数、固定脚本入口和输出语义。
- Runtime 拥有工具注册、审批、进程隔离、网络、凭据投影、日志和审计实现。
- Agent 根据当前任务和实际可用工具决定是否使用 capability；不得假设某个特定
  平台 Tool 名称存在。
- Runtime 可以机械校验契约，但不得根据命令文本替 Agent 选择业务工具、解释业务
  结果或制定业务重试策略。

## `json_outcome_v1`

声明 `result_contract=json_outcome_v1` 的 capability 必须把 `entrypoint` 与
`fixed_args` 视为一个完整调用。该调用把一个 JSON object 作为完整 stdout，并在
真实 execute 模式中返回：

- `outcome_status=succeeded`：所有已请求检查成功；
- `outcome_status=partially_succeeded`：至少一个检查成功且至少一个检查失败；
- `outcome_status=failed`：没有检查成功。

`success` 如果存在，必须与 `outcome_status=succeeded` 一致。当前账号盘点
capability 的固定参数包含 `--strict`，因此满足这一约束；脱离 manifest 直接调用
脚本并省略 `--strict` 时，`success` 仍保留旧 CLI 的继续执行语义，业务判断必须以
`outcome_status` 为准。Runtime 应分别保留进程退出状态和上述业务结果，不得仅凭
退出码 `0` 合成业务成功。

只生成命令而不访问云 API 的 plan 模式返回 `planning_status`，不返回
`outcome_status`。这样可以避免把“计划构造成功”误写成“云查询已经成功”。
