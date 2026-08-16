# 可选机器能力契约

`capabilities.json` 是本 Skill 提供的可选、平台无关机器契约。它让支持声明式
capability 的 Agent runtime 在不解析自然语言指令的情况下了解固定入口、参数边界、
凭据类别和结构化结果；不支持该文件的 runtime 可以忽略它，直接调用对应
`scripts/` 脚本。

## 职责边界

- Skill 拥有 capability ID、只读/变更风险、业务参数、固定脚本入口和输出语义。
- Runtime 拥有工具注册、审批、进程隔离、网络、凭据投影、日志和审计实现。
- Agent 仍根据当前任务自主决定使用哪个业务能力；一旦选中的能力已声明 capability，
  且 runtime 支持该机器契约，就必须调用 runtime 的 capability 入口。只有 capability
  不存在或 runtime 不支持时，才允许直接脚本 fallback；不得假设不存在的平台 Tool 名称。
- Runtime 可以机械校验契约，但不得根据命令文本替 Agent 选择业务工具、解释业务
  结果或制定业务重试策略。

## `json_outcome_v1`

声明 `result_contract=json_outcome_v1` 的 capability 必须把 `entrypoint` 与
`fixed_args` 视为一个完整调用。该调用把一个 JSON object 作为完整 stdout，并在
真实 execute 模式中返回：

- `outcome_status=succeeded`：所有已请求检查成功；
- `outcome_status=partially_succeeded`：至少一个检查成功，同时存在失败检查或影响
  完整性的跳过项；
- `outcome_status=failed`：没有检查成功。

`success` 如果存在，必须与 `outcome_status=succeeded` 一致。当前账号盘点
capability 的固定参数包含 `--strict`，因此满足这一约束；脱离 manifest 直接调用
脚本并省略 `--strict` 时，`success` 仍保留旧 CLI 的继续执行语义，业务判断必须以
`outcome_status` 为准。Runtime 应分别保留进程退出状态和上述业务结果，不得仅凭
退出码 `0` 合成业务成功。

账号盘点 capability 省略 `regions` 时，Skill 入口先通过 IAM
`KeystoneListRegions` 与 `KeystoneListAuthProjects` 获取区域目录和当前身份可访问的
项目映射。区域级服务只查询带可用 `project_id` 的区域；CDN、DNS、SCM、OBS 等
不要求调用方区域的服务只执行一次。无法访问项目的区域必须进入 `skipped_checks`，
不能执行盲查，也不能当作空区域或成功。显式传入 `regions` 时保留定向查询兼容性。

区域级服务在执行前读取本地 KooCLI endpoint 元数据。元数据明确未列出某个区域时，
该服务/区域组合进入 `skipped_checks`，`reason=service_region_not_supported` 且
`affects_completeness=false`，表示该范围不适用而不是查询失败。endpoint 元数据缺失、
为空或无法解析时，只能标记支持范围未知并继续实际查询，不能据此跳过或声称没有资源。

账号盘点 `summary` 必须分别提供 attempted、succeeded、failed、skipped 数量、
影响完整性的跳过数、不适用跳过数、结构化失败/跳过范围和 `complete`。只有失败项或
`affects_completeness=true` 的跳过项会让 `complete=false`；调用方只有在
`complete=true` 时才能把结果表述为完整清单，`partially_succeeded` 必须报告覆盖率与
缺口影响。

`inventory_scope` 声明本次实际覆盖的已登记核心服务、operation 和区域作用域。
`complete=true` 只表示 `complete_claim_scope=selected_services_and_regions` 范围内完整，
不表示已经枚举华为云账号可能使用的所有产品。最终回复必须同时披露这个服务范围。

只生成命令而不访问云 API 的 plan 模式返回 `planning_status`，不返回
`outcome_status`。这样可以避免把“计划构造成功”误写成“云查询已经成功”。

账单 capability 的普通总额查询由 Skill 入口在安全上限内自动完成底层 BSS
分页。只有从 `offset=0` 开始、跨页 scope/币种/总记录数一致且全部记录已取得时，
才返回 `pagination.complete=true`、`complete_result_claim_allowed=true` 和
`verified_monetary_totals`。后续页失败、空页不前进、跨页元数据变化或触及上限时，
必须返回 `partially_succeeded`，保留可用的部分摘要但不生成可声明为完整的总额。

## 变更 capability

`risk=write` 或 `risk=destructive` 的 capability 不是直接执行 API。支持该契约的
runtime 必须把固定 Skill 入口、规范化参数、风险等级、凭据 scope 和
`json_outcome_v1` 绑定为普通审批提案，再由既有执行器在确认后运行。只读 capability
执行器不得加载这些条目。

每个变更 capability 必须通过 `runtime_bundle` 引用顶层 `runtime_bundles` 中的一个
最小运行包。运行包的 `include` 只声明固定入口实际依赖的 Skill 内文件，可以使用
末级文件名 glob 表达同一目录中的同类运行数据。入口脚本本身必须包含在运行包中；
文档、测试、示例和其他非运行材料不得因为实现方便而整套复制。Runtime 应对展开后的
路径和内容生成稳定摘要，把该摘要与入口一起绑定到审批提案，并从用户工作区之外的
不可变存储只读提供。这样 Skill 升级后旧提案仍能使用原运行包，同时用户工作区不承担
平台运行文件的所有权和生命周期。

| capability ID | 用途 | 风险 |
| --- | --- | --- |
| `huaweicloud.ecs.create.v2` | ECS 创建（托管状态、提交确认、job 收敛和 ACTIVE 回读） | `write` |
| `huaweicloud.ecs.create.v1` | ECS 创建旧接口，仅兼容既有 plan/token/state 调用 | `write` |
| `huaweicloud.eip.change.v1` | 公网 EIP 创建/更新和 ShowPublicip 回读 | `write` |
| `huaweicloud.eip.destructive_change.v1` | 公网 EIP 精确 ID 删除和缺失回读 | `destructive` |
| `huaweicloud.kps.import_keypair.v1` | 从工作区 OpenSSH 公钥幂等导入 KPS 密钥对并精确回读 | `write` |
| `huaweicloud.kps.delete_keypair.v1` | 按精确名称删除 KPS 密钥对并验证缺失 | `destructive` |
| `huaweicloud.resource.change.v1` | registry 支持的通用非 ECS/EIP 变更 | `write` |
| `huaweicloud.ecs.guest_delivery.v1` | ECS 目录交付、依赖/服务收敛和 HTTP 验收 | `write` |

执行顺序固定为：选择最新已登记 capability；准备 manifest 声明的业务输入；调用 runtime
创建提案；确认后调用平台执行器；若结果为 `partially_succeeded`，使用同一 capability 和
逻辑资源角色继续 job/resource/application 回读。`submitted`、`submit_unknown` 或
`verification_failed` 都禁止重新 submit。对于 `huaweicloud.ecs.create.v2`，state、ledger、
workflow/step、fingerprint 和 submit token 全部由 Skill/runtime 内部管理，Agent 不参与搬运。
KPS import 只接收 `region`、可选 `project_id`、`keypair_name` 和工作区相对
`public_key_file`；Agent 不需要生成 hcloud 参数、状态文件或确认 token。删除只接收目标
region/project/name。两个 capability 都在 runtime 内先查现状、执行一次 submit，再进行精确
回读；同名同公钥或目标已不存在时幂等成功，同名异钥时拒绝覆盖。
平台执行器的 Agent 可见调用只接收 `proposal_id`。提案的 `action_hash` 和 runtime bundle
摘要由 runtime 持有、校验并投影到执行环境，Agent 不负责在工具调用之间搬运这些不透明
标识；即使模型输出了 hash，runtime 也不得把它当作权威执行参数。

只有 capability manifest 明确声明 legacy plan artifact 时，本地 planner 才可以通过
`exec` / `process` 运行，且必须是 plan-only 命令，不能包含任何 execute/confirm 开关。
最新 capability 未声明 token/state/ledger 参数时，不得引用旧示例额外生成这些参数。EIP 创建必须同时提供 ledger、resource role 和与创建操作匹配的
cleanup operation；更新既有 EIP 只记录 step 状态，不得把既有资源登记为本任务新建资源。

`hcloud_resource_ledger.py` 只记录当前 workflow 明确取得的 canonical ID，不按名称或
全账号扫描猜测归属。清理计划按依赖反序，只使用台账中的精确 ID；缺 ID 时阻止清理，
不自动发现替代目标。ECS 来宾交付只接收工作区内制品和认证文件路径，密码内容不得进入
argv、manifest、state 或返回结果。

只有 capability 未登记、runtime 不提供变更 capability 工具，或工具返回
`GUARDED_CHANGE_CAPABILITY_NOT_REGISTERED` 时允许 fallback。其他错误应修正参数、继续
同一 workflow、回读外部状态或报告限制，不能改用裸 hcloud、临时 SDK 或通用命令提案。
