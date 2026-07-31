# Skill 内受控操作与历史交接试验

## 架构结论

`huaweicloud-skill` 是可被任意 Agent 直接加载的标准 Skill。它不得要求任何 Agent/runtime
修改代码、增加插件、维护服务专用 adapter，才能执行某个华为云操作。

因此，真实操作闭环的所有华为云语义都必须由 Skill 自己拥有：

```text
Action Spec / Action Plan
  -> 明确确认与当前计划绑定
  -> 服务专用参数映射与预检
  -> 提交前事实刷新
  -> Skill 内部受控 hcloud / SDK / Terraform / MaaS 调用
  -> job 终态、资源读回、业务验证与结果归一化
```

Agent 的职责仅是遵循这份 Skill：展示计划、获得用户的明确回答，并通过其既有命令执行能力运行
Skill 脚本。Skill 不假设确认按钮、token 格式、身份系统或凭据注入方式。

## 确认保证的诚实边界

所有 Agent 都应遵守的通用确认是：用户已经看到当前计划的目标、范围、输入摘要、费用/风险和验证
方式，并作出明确确认；确认一旦与 Action Plan、Execution Intent 或关键预检事实不一致，就必须失效。

这能约束 Skill 的受控入口，但单靠本地 JSON 不能证明“确认者身份已认证”“确认只能使用一次”或
“审计记录不可篡改”。如果某个运行环境原生提供这些能力，Skill 可以保留其引用作为额外证据；不得
为了获得它们而改造该运行环境，也不得把它们描述为本 Skill 在所有 Agent 中都能强制的能力。

## 当前状态：所有 mutation 仍是 `plan_only`

通用 hcloud mutation、旧 guarded submit/dry-run、Terraform 状态变更和 MaaS 生成均已在运行时
收口为 `plan_only`。目前没有任何真实提交入口。

ECS 的“密钥对 + 私网 + 已有安全组”创建子集和 DNS A 记录已经具备经过审阅的本地请求映射：

| 试点 | 已具备 | 尚未具备 |
| --- | --- | --- |
| ECS 创建实例 | Action Spec、计划/确认绑定、参数与安全组规则校验、私网密钥对请求映射。 | Skill 内部受控调用、提交前事实刷新、job 终态、实例 `ACTIVE` 与登录/业务读回。 |
| DNS 创建 A 记录集 | Action Spec、计划/确认绑定、FQDN/IPv4/TTL 校验和请求映射。 | Skill 内部受控调用、提交前 zone/冲突刷新、记录集读回与 DNS 解析验证。 |

ECS 密码登录、默认安全组、公网 IP、任意 ECS body 片段和其他 DNS 记录类型仍未审核，保持
`plan_only`。

## 历史交接试验：不作为目标架构

`controlled-submit-handoff/v1`、`controlled-adapter-registry.json`、
`hcloud_controlled_submit_handoff.py` 与 `hcloud_controlled_adapter_registry.py` 是本轮曾创建的
本地试验：它们只输出无秘密指纹和 `plan_only` 结果，不会发送云请求。

其中将 `host_adapter_required` 作为真实提交前提的设计已被否决：它会让 Skill 依赖某个 Agent 的
专用改造，与标准 Skill 的目标冲突。新功能不得依赖这些交接产物；后续实现会将其中仍有价值的
服务映射和审计证据迁移到 Skill 内部受控操作资料，并退役这一条交接路线。

在替换完成前，维护者可运行下面命令检查历史试验的本地一致性；其结果不表示真实提交可用，也不应
被 Agent 当作运行入口：

```bash
python3 scripts/hcloud_controlled_submit_handoff.py --audit-adapters --pretty
```
