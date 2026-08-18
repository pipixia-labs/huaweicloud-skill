# Release Notes

## Unreleased

## v0.9.6 / 0.9.6 - 2026-08-18

v0.9.6 是可移植执行与长只读任务恢复版本。它为不同 Agent/宿主提供不依赖当前工作目录的稳定
Skill 入口，并让账号盘点和账单分页在进程中断或单轮时间不足时从已确认进度继续执行。

### 主要变化

- **稳定执行入口**
  - 新增 POSIX `bin/hcloud-skill` 与 Windows `bin/hcloud-skill.cmd`，按 Skill 安装位置解析内置脚本，
    不要求宿主把 Skill 复制到普通工作区，也不依赖调用时的当前目录。
  - 入口保持原脚本参数、stdout/stderr 和退出码语义；Agent 仍自主选择 hcloud、SDK、Terraform 或
    高频脚本，Skill 不引入平台专属 Function Calling。

- **文档与持续集成**
  - 新增文档/CLI 漂移测试，校验维护文档引用的脚本和参数，并修正 EIP、IAM safe-exec 与 OBS 示例。
  - 新增无需华为云凭据的 Linux CI，覆盖离线单元测试、Ruff、Python 编译、任意目录入口 smoke 和
    whitespace 检查。

- **可恢复账号盘点与账单读取**
  - 账号盘点和 Billing 自动分页支持 `--checkpoint-file`、`--resume` 与可选 `--time-budget`。
  - checkpoint 使用版本化、scope-bound 契约；恢复时拒绝区域、服务、日期、分页范围等查询范围漂移，
    只复用已经完成的盘点检查或已经验收的账单页。
  - checkpoint 以私有 `0600` artifact 保存，可能包含中间原始数据，不进入公共日志或紧凑 stdout
    回执；大结果仍沿用显式 `--output-file` 的 artifact/receipt 模式。
  - 时间预算是当前一次运行的总预算，不改变单个 hcloud 请求的既有超时语义；预算耗尽时返回明确的
    部分进度和下一步恢复信息，不把不完整账单声明为完整总额。

### 验证

- 全量离线回归：553 项通过，10 项按条件跳过。
- Ruff、compileall、manifest JSON 和 diff 检查通过。
- 新增回归覆盖盘点恢复、账单分页恢复、scope mismatch、私有权限与紧凑回执；未执行真实云变更。

### 兼容性与运行时边界

- 现有脚本直调继续有效；稳定入口是跨宿主的推荐路径，不是新的平台能力依赖。
- 未提供 checkpoint 参数时保持原执行方式；未提供 `--output-file` 时保持原完整 JSON stdout。
- checkpoint 只负责保存确定的读取进度，不替 Agent 规划任务，也不替宿主管理 LLM session 或审批。

## v0.9.5 / 0.9.5 - 2026-08-18

v0.9.5 是自主 Agent 执行准确性和可移植性增强版本。它明确 `hcloud > SDK > Terraform` 的默认选择，
统一高价值公共脚本的兼容结果回执，并补齐复杂请求预检、批量/异步结果语义、资源依赖证据和
区域 project_id fallback。Skill 继续提供事实、参数、错误和验证语义，不替代 Agent 的业务决策，
也不要求宿主实现专属 Function Calling。

### 主要变化

- **后端选择和运行时边界**
  - 默认优先 hcloud；SDK 用于类型化请求、复杂 body、分页/并发或 hcloud 的实际覆盖障碍；Terraform
    只由 IaC、import、drift 和长期纳管意图触发。
  - 环境 doctor 按当前任务检查 hcloud、指定服务 SDK、Terraform、OBS、网络和 artifact 目录，
    不再因未选择 SDK 服务而扫描全部 package。

- **公共结果和大输出回执**
  - 11 个高价值查询、盘点、验证和验收入口支持兼容的 artifact/receipt 模式；只有显式传入
    `--output-file` 时才把完整结果写入 `0600` 文件并返回紧凑回执。
  - 公共回执使用 `planned`、`succeeded`、`partially_succeeded`、`failed` 和 `outcome_unknown`，
    并把脚本成功、环境 ready 和领域完成状态分开表达。

- **请求构造和 provider 证据**
  - 新增纯本地请求预检，结合精确 operation 版本与官方 SDK 静态请求模型，在 dry-run/submit 前
    发现 JSON 外层、参数位置、required 和类型错误；证据不完整时保持 partial，不猜测嵌套结构。
  - operation resolver 和 safe exec 为复杂 body、SDK schema 证据、请求结果与资源终态提供更明确的
    结构化语义，结果未知时要求 verify-before-retry。

- **批量、异步和依赖证据**
  - 新增 operation-specific 行为 profile 和本地 inspector，覆盖 ECS、EIP、EVS、ELB、RDS、DNS 的
    批量或异步结果；submit receipt 不再被误写成逐项资源完成。
  - 新增高频资源依赖证据和本地查询入口，帮助 Agent 根据实时状态决定删除、创建和回读次序；
    Skill 不引入公共轮询状态机，也不替 Agent 固定调用顺序。

- **区域 project_id 解析修复**
  - IAM fallback 现在以单 token 传递 `--arg=--name=<region>`，避免 argparse 在 hcloud 调用前拒绝参数。
  - 结构化本地输出错误优先于文本关键字分类，不再把帮助信息中的 `--timeout TIMEOUT` 误报为
    `IAM_NETWORK_TIMEOUT`。

### 验证

- 全量离线回归：529 项通过，10 项按条件跳过，1984 个参数化子测试通过。
- Ruff、compileall 和 diff 检查通过。
- 已用真实 IAM 只读 fallback 成功解析 `cn-north-4` 的 project_id；未执行真实云变更。

### 兼容性与运行时边界

- 未指定 `--output-file` 时，已迁移脚本继续输出原有完整 JSON。
- 新增 profile、preflight 和 dependency 工具只提供事实、计划或证据，不调度 Agent、不要求平台专属
  Tool，也不限制 Agent 对长尾任务直接使用有证据的 hcloud、官方 SDK 或 Terraform。

## v0.9.4 / 0.9.4 - 2026-08-17

v0.9.4 是只读执行入口的可移植性和长结果可靠性增强版本。账号盘点与账单读取由 Agent 直接通过
普通命令执行工具调用 Skill CLI，不再要求宿主平台实现专属只读 capability Function Calling；
同时补齐 project 复用、有限并发、结果 artifact 和账单完整分页，减少重复探测、模型大结果等待和
第一页账单被误报为完整总额的问题。

### 主要变化

- **可移植只读 Skill CLI**
  - 账号盘点和账单读取现在由 Agent 通过普通命令执行工具直接调用 Skill CLI；不再要求宿主实现
    `run_read_only_capability`，也不再发布两项只读 `capabilities.json` 声明。
  - Skill 继续负责华为云查询、分页、结果语义和错误分类；凭据、KooCLI 安装与离线缓存仍由宿主
    runtime 准备。

- **盘点性能和大结果收敛**
  - 宽泛查询可用 `--output-file` 保存完整 JSON，并只向 stdout 返回紧凑状态、摘要、文件路径、
    大小和 SHA-256 回执。
  - 账号盘点在每个区域只解析并复用一次 `project_id`，使用有限并发查询独立服务；IAM 解析失败时
    一次性标记该区域的项目级检查，避免每个 hcloud 子进程重复探测。

- **账单分页和完整性语义**
  - Billing live-read 在页数、记录数、payload 和总超时上限内自动分页并合并结果。
  - 跨页校验查询 scope、币种、顶层金额元数据和 `total_count`；只有完整结果返回
    `verified_monetary_totals`。
  - 后续页失败、空页、响应不一致或触及安全上限时返回 `partially_succeeded`，不把第一页小计
    暴露为可声明的完整总额。

### 验证

- 全量离线回归：463 项通过，10 项按条件跳过。
- 本版本未执行真实云变更。

### 兼容性与运行时边界

- 未指定 `--output-file` 时，账号盘点和账单读取继续输出完整 JSON，保持原有 CLI 调用兼容。
- KooCLI 固定版本、中文 BSS 离线元数据种子、临时 profile 与断网验收仍由宿主 runtime 负责；
  Skill 不携带平台路径、镜像元数据或凭据。

## v0.9.3 / 0.9.3 - 2026-08-04

v0.9.3 是大一统 Skill 的执行边界和证据可信度增强版本。它吸收外部执行层评测中可复现、且与
统一大 Skill 路线一致的问题：修复 safe_exec 参数兼容，明确共享执行与秘密边界，并让未来的
只读实测从产生时携带可审计 provenance。Skill 继续统一跨服务原则、事实和安全口径，不限制
Agent 根据现场自主选择服务、工具、参数和调用顺序。

### 主要变化

- **safe_exec 参数兼容与外部回归基线**
  - service/operation 模式下，直接 CLI 的裸 `--arg=server_id=...` 会规范化为 hcloud 所需的
    `--server_id=...`；已经带长/短选项前缀的参数保持不变。
  - generic command-part 继续保留 `obs://` 等位置参数；空值、首尾空白和多行 token 会在启动
    hcloud 前拒绝。
  - 新增分层外部执行回归清单，要求精确 commit、环境、分子/分母、硬失败和责任归因，不沿用
    无法复算的单一总分。

- **共享执行与秘密边界**
  - machine-readable audience manifest 明确：普通业务 API 默认经 safe_exec；版本、帮助和元数据
    预热允许受限代码直调；仍保留有证据的窄范围 Agent fallback。
  - 普通 task/证据 artifact 与 `0600` credential artifact 分开处理，凭据不得先经过普通日志或
    workspace 记录。
  - 修复旧 Qwen MaaS 兼容入口可能把 HTTP 错误正文中的 API Key 带入异常信息的问题。

- **诚实成熟度与可复现 smoke evidence**
  - 成熟度审计区分 curation 设计档案、目标闭环契约和真实 `live-read-smoked` 证据；缺时间、来源
    或环境时继续报告 unknown，不把规划档案描述成最近实测。
  - metadata-backed 只读 smoke 的 record 与 confidence suggestion 共用一个 `observed_at`，并记录
    受限的 Skill revision、工作树状态、region、Python/platform 和 hcloud 版本 token。
  - 没有独立 `.git` 的复制或 vendored Skill 不借用父仓库 commit；profile、project ID、binary path、
    原始 stdout/stderr 和版本诊断不会进入证据记录。
  - 成熟度完整 provenance 要求观测时间、来源、具体 source revision 和非敏感环境同时存在。

- **统一任务语义兼容**
  - Progress 模板恢复统一“当前缺口”标签，同时保留“阻塞、未知或遗留”的细分语义。
  - 本版本不新增固定 TaskContract、状态机、Policy Engine、服务/API 白名单或 Agent 适配层。
  - v0.8.2 延续的大输出保护、变更确认、脱敏、异步收敛和业务验收边界保持不变。

### 验证

- 全量离线回归：432 项通过，10 项按条件跳过，另有 1904 个 subtests 通过。
- smoke/成熟度工具扩大回归：159 项通过，另有 16 个 subtests 通过。
- 统一机制契约：13 项通过，另有 8 个 subtests 通过。
- Ruff、Python `compileall`、234 个 JSON 文档和 `git diff --check` 通过。
- `SKILL.md` 保持 140 行且无差异；本版本没有运行真实云变更或伪造历史 smoke provenance。

### 兼容性与安全说明

- safe_exec 只规范化它收到的 argv，不替 Agent 决定服务、operation、参数值、重试或调用顺序。
- smoke provenance 是维护期证据元数据，不是账号授权、云侧状态库或强制运行时控制器。
- 历史 confidence 条目不会被自动补写时间、commit 或环境；需要后续真实只读验证产生新证据。
- Plugin 内置 Skill 快照不属于本版本发布范围，继续保持原状态。

## v0.9.2 / 0.9.2 - 2026-08-02

v0.9.2 是大一统 Plus 的范围收口版本。它在 v0.9.1 的共享原则和 task workspace 基础上，补充
可移植任务身份、目标组织、用户状态投影和知识渐进加载，并把目标明确限定为一个对话/task 内的
跨服务、跨场景和多轮一致性。Skill 继续只辅助 Agent，不控制服务、工具、参数或执行顺序。

### 主要变化

- **可移植 task 身份**
  - 复杂任务入口必须包含非空 `task_id` 和 `task_id_source`；简单一次性查询继续豁免建档。
  - 运行时 ID 对 Agent 可见时原样复用；不可见时首次建档生成稳定描述符，后续轮次从同一
    workspace 读取并复用。
  - Agent 生成的描述符不冒充平台 ID，不绑定 CloudClaw 环境变量，也不用于平台 task API。

- **Plus 行为证据和目标资料**
  - 新增固定条件、重复运行、分子/分母、失败样例、工具轨迹和正式 workspace 文件清单的评测协议。
  - 历史固定条件中，任务身份候选的描述符采用和跨轮复用均为 3/3，简单查询仍保持零正式任务
    文件；该结论只覆盖当时的 Agent、模型、workspace 和离线场景。
  - 企业网站、跨服务资源盘点和成本治理指南作为可选目标组织参考保留。此前目标指南独立加载为
    0/3、未证明改善 Agent 行为，因此本版本不把它宣称为已验证优势，也不强制 Agent 读取。

- **用户状态投影**
  - 新增 `references/interaction-guidance.md`，让 Agent 从同一份 task 记忆按需生成 Goal、
    Option、Progress、Recovery 和 Completion。
  - task/progress 模板可选记录完成条件、证据来源和时效、未知、阻塞、用户影响与下一步。
  - 五种投影不是五个固定文件、Schema 或运行时状态对象；简单任务只使用必要部分。

- **知识所有权和渐进加载**
  - `references/source-map.md` 区分权威事实、编写知识、派生视图和运行时事实，明确各自维护位置。
  - 形成 Metadata、`SKILL.md`、Shared Core、Goal/Scenario、Service Module、Materials 六层加载路径，
    并定义何时停止扩大上下文、何时继续寻找证据。
  - 大输出继续保存为独立 artifact，不因加载更多知识重新塞入对话；目标视图不复制 registry、
    catalog、价格、配额、参数或实时云状态。

- **单 task 范围和架构表达**
  - 一个对话对应一个 task；同一对话中的追加、修改、撤销和恢复继续更新同一 task。
  - task 内部统一使用 `task -> phase -> step -> operation`；subtask 是 Agent 自主拆解时的可选概念，
    不要求独立 task ID、文件、Schema 或固定状态机。
  - 不建设跨 task workload、长期偏好、跨 Agent 交接、机器交换格式、常见 Agent 适配，也不继续
    扩展现有 P2 能力。CCI、CCE 和 Kubernetes 中的 workload 技术术语及既有 P2 planner 保持不变。
  - 主架构文档新增共享机制因果矩阵，集中解释大 Skill 相对服务分散组织的跨场景一致性优势。

### 验证

- v0.9.2 包含的历史 Plus 基线、任务身份和目标指南候选保留了 36 份逐次运行记录及对应静态契约。
- 恢复目标资料后的历史门禁为：聚焦 13 项通过；全量 431 项通过、10 项按条件跳过；Ruff、
  Python `compileall` 和 `git diff --check` 通过。
- 按用户要求，交互投影、知识管线和本次架构收口没有由 Codex 新运行单元测试或行为评测，当前
  状态明确为“已实现、待用户验证”。发布前只复核版本差异、whitespace、路径和 Git 边界。
- `SKILL.md` 保持 140 行，v0.8.2 延续的大输出 operation 清单和执行前保护未修改。

### 兼容性与安全说明

- v0.9.2 不建设 Policy Engine、Execution Gateway、授权账本、固定 TaskContract、固定状态机或
  Agent 框架适配层。
- 使用本 Skill 的 Agent 假定具备 Skill 使用、代码执行、云工具调用和 workspace 文件读写能力；
  Skill 不为缺少这些能力的 Agent 提供降级运行时。
- task 文件仍不是用户授权、可信审计日志或云侧实时状态库。继续高影响操作前必须实时回读，
  付费、公网、破坏性和秘密相关边界保持不变。
- 现有 hcloud-first、SDK 窄补充、Terraform 辅助面、MaaS API、变更确认、脱敏、异步收敛、
  后置验证和业务验收行为保持兼容。

## v0.9.1 / 0.9.1 - 2026-08-02

v0.9.1 是轻量大一统机制的稳定化版本，也是后续 Plus 架构实施的基线。它根据真实多轮建站任务暴露的问题，补齐任务升级、重要变化更新、逻辑资源身份、异步结果收敛、受控替换和秘密输出边界；不增加任务控制器，也不限制 Agent 根据现场改变服务、工具、参数和执行顺序。

### 主要变化

- **多轮任务记忆生命周期**
  - 同一 task 从简单查询升级为多轮、跨服务、有副作用、异步或可中断任务时，必须立即重新分类，并在下一项实质规划或执行前建立或更新任务记忆入口。
  - 用户修改目标、约束或方案，获得关键结果、出现错误、准备中断或形成完成判断时，只更新重要变化；恢复时先读取任务入口和必要 artifact。
  - 运行时 task 级 workspace 直接使用当前目录和运行时 task ID；只有多个 task 共享 workspace 时才使用 `tasks/<task_id>/`，不生成第二个任务身份。

- **逻辑资源与副作用收敛**
  - 对付费或有副作用的创建、删除、替换、绑定，以及异步结果恢复，按需记录逻辑角色、预期数量、canonical 资源、当前状态、待决操作和最近核验时间。
  - 同一逻辑角色存在 pending 或 outcome unknown 的操作时，先通过 job、资源列表、详情或等效证据回读收敛，不因命令退出码为 0 或请求已受理而再次创建同角色资源。
  - 资源名称变化不会自动产生新的逻辑角色；幂等恢复同时检查名称、用途、候选资源和待决动作。

- **受控替换与诊断**
  - 默认一换一替换要求删除 job 达到终态且旧资源已确认不存在；迁移、高可用或临时并存需要作为显式方案说明。
  - 原方案没有覆盖的连续替换、并行保留、数量或持续费用增加、公网暴露扩大、数据或破坏范围变化，需要重新向用户说明并取得匹配的确认。
  - ECS 登录或应用验收失败不直接等于必须重建；Agent 根据现场核验 job/实例状态、EIP/网络/安全组、凭据、cloud-init、服务和日志，再自主选择等待、原地修复、替换或停止。

- **秘密输出边界**
  - 创建 keypair、重置密码或生成 token 时，秘密必须直接进入受限 artifact、凭据 broker 或 runtime secret 通道，不能先经过普通 stdout/stderr、平台日志、task 文件或最终回复。
  - 当前运行时没有安全输入、输出或保存通道时，Skill 要求 Agent 说明阻塞；真正不可绕过的隔离、脱敏和访问控制仍属于 Agent 运行时。

- **验证与文档**
  - 扩展 `templates/task.md`、workspace 指南、运行安全边界和幂等恢复 playbook。
  - 增加逻辑资源收敛、删除 job 未终结、诊断后一换一替换和敏感输出行为场景。
  - 同步当前轻量机制实施说明和版本口径，为后续 Plus 设计提供明确基线。

### 验证

- 统一机制与架构聚焦测试：43 项通过。
- 全量离线单元测试：427 项通过，10 项按条件跳过。
- Ruff、Python `compileall` 和 `git diff --check` 通过。
- `SKILL.md` 保持 140 行；v0.8.2 延续的大输出策略未删减。

### 兼容性与安全说明

- v0.9.1 不建设 Policy Engine、Execution Gateway、授权账本、固定任务状态机或强制运行时组件。
- 资源生命周期摘要是按风险触发的可选 task 信息，不是固定 JSON Schema、云侧实时数据库或不可修改计划。
- Agent 仍负责选择服务、工具、API、参数、诊断深度和调用顺序；Skill 只统一高影响信息和判断边界。
- 简单一次性只读查询可以不创建 task 记录；现有 hcloud-first、大输出保护、变更确认、脱敏和后置验证行为保持兼容。

## v0.9.0 / 0.9.0 - 2026-08-01

v0.9.0 是基于 v0.8.2 的轻量大一统机制验证版本。它不建设新的任务控制器，而是在保留 Agent 自主规划能力和现有云操作安全边界的前提下，增加少量跨服务共享语义与每 task 的 workspace 任务记忆，验证完整用户目标在跨服务、多轮和可中断场景中的一致性。

### 主要变化

- **跨服务共享原则**
  - 新增 `references/unified-principles.md`，统一目标变化、用户声明、Agent 推断、工具观测、信息时效、作用域、事实冲突和结论依据。
  - 使用共同但非状态机式的完成语义，区分 `planned`、`submitted`、`resource_ready`、`business_verified`、`partially_succeeded` 和 `outcome_unknown`。
  - 安全、授权、错误处理和大输出继续引用既有权威资料，不复制第二套规则。

- **Agent workspace 任务记忆**
  - 新增 `references/task-workspace-guide.md`、`templates/task.md` 和 `templates/progress.md`。
  - 复杂、多轮、跨服务、有副作用、异步或可能中断的任务，必须在首次实质规划或执行前，由 Agent 使用自身文件读写工具把最小任务记忆实际写入 workspace。
  - 运行时已提供 task 级独立 workspace 时直接使用当前目录；多个 task 共用 workspace 时使用 `tasks/<task_id>/` 隔离。
  - 用户追加或修改要求、关键结果或错误、方案变化、中断和完成判断发生时，只更新重要状态，不要求记录每句对话或每次工具调用。
  - 对话 context、运行时待办和平台自动日志不能替代正式任务记录；写入失败必须如实说明。

- **目标—能力组织样例**
  - 新增企业网站上云样例，从用户目标组织计算、网络、域名、HTTPS、数据、监控、日志、备份和成本候选。
  - 样例保留替代路径、动态事实和澄清空间，不定义唯一架构、固定服务组合或调用顺序。

- **验证与开发者资料**
  - 新增统一机制契约测试和多轮行为场景，覆盖目标修改、未知变化、上下文清空恢复、任务切换、任务隔离、结论依据和简单查询负担。
  - 新增 `docs/unified-task-mechanism-implementation.md`，并同步架构、技术概览、实现细节、收益分析和开发者文档索引。
  - CloudClaw 本地验证暴露了“使用运行时待办但未实际落盘”的失败模式，因此 `SKILL.md` 进一步强调文件写入要求。

### 验证

- 统一机制契约测试：8 项通过。
- 全量离线单元测试：426 项通过。
- Ruff 0.16.1、Python `compileall` 和 `git diff --check` 通过。
- materials drift 检查通过；catalog 审计保持 199 个公有云服务、15,702 个 operation，curated registry 保持 19 个服务、311 个 registered operation。

### 兼容性与安全说明

- v0.9.0 不固定 `TaskContract`、`TaskPlan`、JSON Schema、API、参数、工具或调用顺序，也不建设 Policy Engine、Execution Gateway、授权账本或系统级防旁路机制。
- 简单的一次性只读查询可以不创建 task 记录；复杂任务的记录格式和文件数量可由 Agent 按需要调整。
- task 文件不是用户授权、可信审计日志或云侧实时状态库，不能替代实时查询、变更前确认和平台权限控制。
- 现有 hcloud-first 执行链路、大输出收敛、凭据脱敏、付费/公网/真实变更确认、异步终态跟踪和业务验收边界保持不变。
- 本版本面向具备多轮对话和 workspace 文件读写能力的常见 Agent；纯 Skill 指令不能保证所有模型或运行时一定遵守，后续仍需继续收集真实运行证据。

## v0.8.2 / 0.8.2 - 2026-07-31

v0.8.2 是 v0.8 系列的兼容性与安全闭环补丁版本。它继续保持 hcloud-first 的执行链路和既有变更门禁，不增加默认资源创建、修改、删除、Terraform apply 或通用 SDK mutation 能力。

- MaaS 批量图片入口现在接受每项稳定 `id` 并输出逐项进度检查点；图片文件必须非空且完整落盘后才报告成功，失败批次可由宿主平台识别已完成项，避免重复生成。
- `SKILL.md` 直接列出大输出 operation 和命名规则，要求 Agent 在执行前命中策略并禁止先用裸 `hcloud` 试探响应大小；架构契约确保显式清单与机器可读策略保持同步。
- 网站部署路由新增 `architecture_decision` 和 `change_execution_blocked`：明确要求机器、ECS 或公网 IP 时进入 ECS + EIP 路径，纯静态且接受对象存储时才进入 OBS；未明确托管方式、动态能力边界或约束冲突时，先向用户澄清且不得创建资源。
- OBS 默认静态网站域名只作为临时源站验证结果，正式交付需要自定义域名和真实浏览器验收；不得用 OBS 地址代替用户要求的 ECS 公网 IP。
- Billing planner 内置 operation-specific 语言 Header 能力：只对支持的 BSS operation 生成 `X-Language`，月度汇总、账户余额和定价等不支持接口不再被无效参数阻断；live-read 复用同一能力校验。
- Skill 增加可选、运行时中立的账号盘点 capability 契约；支持声明式 capability 的运行时可安全调用，不支持的运行时仍可直接调用同一脚本。

### 验证

- 全量离线单元测试和 Python 编译检查：见本次发布提交中的实际执行结果。

### 兼容性与安全说明

- 仅在用户确认公网网站方案后，ECS 规划才允许精确 TCP `80/443` 公网入口；仍需现有 guarded submit 确认、规则回读和外网协议探测。
- 保留 v0.8 中兼容入口的 deprecated 状态；主路径仍使用统一 closure 和 MaaS 入口。

## v0.8.1 / 0.8.1 - 2026-07-24

v0.8.1 聚焦 Skill 独立分发后的运行一致性，以及 hcloud 查询在 API 版本和大输出场景下的稳定性。版本没有增加新的默认资源变更能力，也不依赖 `huaweicloud-skill` 文件夹之外的源码仓库。

### 主要变化

- **独立安装**
  - 默认运行不再搜索父目录或同级参考项目。
  - Billing 差距检查和问题覆盖使用 Skill 内置的规范化基线与最小回归样例。
  - SDK、Terraform Provider 和完整问题集审计保留为显式维护入口，不影响下载后的普通 Agent 使用。

- **API 版本解析**
  - Catalog 保留 operation 的逐版本参数和请求信息。
  - 新增统一 resolver，根据实际参数生成显式 `Operation/vN`，避免多版本 API 误用最高版本参数。
  - 只读命令只在明确的版本或参数使用错误时允许一次受限纠正；mutation 不自动重放。

- **大输出保护**
  - 新增机器可读的输出策略，覆盖大列表、日志与事件、时序指标、全租户记录和内容下载。
  - safe-exec 支持自动分页、摘要和本地文件输出；成功解析的 JSON 不再和 raw stdout 重复回显。
  - 超阈值响应只向 Agent 返回 schema、数量和少量样本，完整数据仅在明确选择本地文件时保存。

- **统一受控入口**
  - 普通查询和资源发现路径复用统一的版本解析与输出策略。
  - 高风险大输出查询优先生成显式版本的 safe-exec 命令，降低不同 Agent 直接拼接 hcloud 命令时的行为差异。

### 验证

- 全量离线回归：381 项通过，8 项按条件跳过。
- `python -m compileall -q scripts tests`、223 个 reference JSON 解析与 `git diff --check`：通过。
- 独立 Skill 文件夹回归：仅复制 `huaweicloud-skill` 后，全量测试和默认 Billing、问题覆盖、SDK、catalog smoke 路径均通过；Provider 维护审计按预期要求显式源码路径。

### 兼容性与安全说明

- 保持一个大 Skill、hcloud-first 和现有风险门禁理念。
- 没有增加默认资源创建、修改、删除、Terraform apply 或通用 SDK mutation 能力。
- 默认运行只依赖 Skill 内置文件、用户本地运行时状态，以及已安装的 hcloud、SDK 或维护工具。

## v0.8.0 / 0.8.0 - 2026-07-24

v0.8.0 聚焦“少而精”的专家证据增强和统一入口治理：不增加第二套 Skill 架构，不扩大默认执行面，也不移除现有兼容脚本。`hcloud` 继续作为资源查询、执行和回读主路径，新增内容主要帮助 Agent 更准确地判断证据是否充分、任务是否真正完成。

### 主要变化

- **受限运行环境兼容**
  - `hcloud_safe_exec.py` 在继承当前环境的基础上，为缺失的 `USER` 和 `HOME` 提供非敏感默认值。
  - 解决最小 sandbox 环境中 KooCLI 无法解析当前用户目录的问题；已经由运行时注入的 profile、凭据和目录环境不会被覆盖。

- **云原生与多集群证据**
  - CCI 增加版本相关 annotation 的精确写入/回读要求，以及 WebSocket exec 不可用时的日志、事件和只读状态降级路径。
  - CCE 补充指标采集依赖、CoreDNS/apiserver 指标语义、资源绑定一致性和活动告警加历史告警的关联判断。
  - UCS 区分源 CCE ID 与 UCS ID，并补充管理面可达性、`Available` 完成状态和策略从 warn 到 deny 的分阶段证据。

- **计算、运维与数据仓库诊断**
  - Flexus/COC 使用七层完成状态，区分云资源、远程执行、系统、进程、端口、协议和持续运行证据；COC 同时区分服务控制面区域与目标实例区域。
  - DWS 将 CPU 采样语义、CN/DN 内存归属，以及吞吐、IOPS、时延、队列证据分开判断，避免把单一指标直接归因为节点故障。

- **AI 与网站合规证据**
  - ModelArts 训练诊断采用作业详情到训练日志的渐进证据链，缺少关键证据时停止下结论。
  - ICP 相关指导只提供带适用范围和时间边界的规则证据方法，不固化可能过期的备案结论。

- **v0.8 统一入口治理**
  - `hcloud_acceptance_evidence_result.py`、`hcloud_acceptance_probe_plan.py`、`hcloud_acceptance_probe_run.py`、三个分层 closure planner 以及 `qwen_text_to_image.py` 正式标记为 deprecated。
  - 旧文件在 v0.8/v0.9 窗口继续可调用；新工作流使用 `hcloud_acceptance_closure.py`、`hcloud_closure_plan.py`、`maas_image_generation.py` 或 `maas_text_to_image.py`。
  - EIP 验收示例已迁移到统一入口；新增架构契约，阻止活跃文档、路由和示例重新使用旧命名。

### 验证

- 兼容入口、架构契约、safe-exec、专家证据和场景路由聚焦测试：68 项通过。
- 全量离线回归：352 项中 351 项通过；唯一失败仍是既有 Billing 外部参考目录缺少 `guide.md`，此前已经在未包含本版本改动的基线上复现。
- `python3 -m compileall -q scripts tests`、217 个 reference JSON 解析与 `git diff --check`：通过；活跃文档旧入口扫描无命中。

### 兼容性与安全说明

- v0.8.0 只标记旧入口 deprecated，没有删除脚本，也没有改变现有调用结果和安全门禁。
- 本版本没有增加默认资源创建、修改、删除、Terraform apply 或通用 SDK mutation 能力。
- 专家证据链是诊断和验收判断规则，不代表未采集证据的服务已经完成真实账号验证。
- v0.9 计划把主路径测试进一步迁移到统一入口；是否在 v1.0 移除旧入口仍需按连续版本使用情况单独评审。

## v0.7.2 / 0.7.2 - 2026-07-23

v0.7.2 聚焦运行环境可移植性、场景交付约束和无服务器容器部署前的安全证据链。`hcloud` 仍是资源查询与验证主路径；本版本没有新增默认资源创建、删除或 SDK 变更执行能力。

### 主要变化

- **Catalog 与 Billing 安全边界**
  - 刷新 hcloud metadata-backed catalog：默认排除 HCS/ManageOne 私有云控制面，保留 AgentArts 公有云覆盖，共 199 个服务、15,702 个 operation。
  - BSS 写操作（包括计费周期转换）进入 hard manual gate，只读 Billing/BSS 工作流保持不变。

- **Windows 与运行时兼容**
  - 生成的 safe-exec 和 ECS 后续验证命令使用当前 Python 解释器，不再假定只有 POSIX `python3`。
  - `hcloud_environment_doctor.py` 为 Windows 提供 KooCLI PowerShell 下载/解压/Path 校验指引，以及 `python`、Terraform 和 `obsutil.exe` 的平台化检查命令；诊断器仍然只检查，不会自动安装或改写配置。

- **场景契约**
  - 场景路由为 OBS 静态站点、可观测 readiness、审计与成本治理、容器镜像部署返回 machine-readable 契约，明确所需输入、证据、输出结构和风险边界。

- **CCI 工作负载前检**
  - 新增 `hcloud_cci_workload_plan.py`，以非执行方式编排 namespace、Network、quota/events、workload、Pod、Service 和协议探测的证据计划。
  - CCI planner 拦截 delete intent、与 `10.247.0.0/16` 重叠的子网、CPU/内存 request 与 limit 不一致，以及缺少业务理由或受限来源 CIDR 的 ELB/EIP 公网暴露。
  - CCI 作为中等覆盖的候选服务进入 curation profile；尚未声称真实账号只读 smoke 证据。

### 验证

- 与本版本相关的 Windows、场景路由、CCI、curation 和架构契约测试：73 项通过。
- `python3 -m compileall -q scripts tests`、关键 JSON 解析与 `git diff --check`：通过。
- 全量测试当前有 1 项既有 Billing 外部参考目录重命名问题：代码仍指向旧目录，不影响本版本的 catalog、Windows 或 CCI 功能。

### 兼容性与安全说明

- 本版本不自动安装 KooCLI、SDK、Terraform 或 obsutil。
- CCI planner 不调用 hcloud、不接收镜像拉取凭据，也不产生可提交的资源变更或删除命令。
- `ready_to_review` 仅表示前置输入和规划检查齐备，不代表变更授权或应用已可用。

## v0.7.1 / 0.7.1 - 2026-07-05

v0.7.1 是 v0.7 之后的小版本，重点把成本/账单只读查询链路、CES 指标 datapoint 诊断和 acceptance probe 安全边界补实，同时把兼容入口退役节奏写成清晰的版本治理规则。

### 主要变化

- **成本与账单只读链路**
  - 新增 `hcloud_billing_live_read.py`，把 Billing/BSS request planner、safe_exec 和脱敏 summarizer 串成显式确认的只读 live-read wrapper；默认只计划，执行时要求 `READ_BILLING_DATA` 确认并限制分页。
  - 修正 Billing/BSS hcloud 命令计划的语言参数：KooCLI 7.2.2 的 BSS operation 使用 `--X-Language=zh_CN`，不是 `--cli-lang=cn`。
  - 新增 `hcloud_billing_operation_gap.py`，对比官方 billing-scout / business-support-query 与本地 BSS planner 的 operation 覆盖，输出 P1/P2 缺口和 pricing helper 参考。
  - 扩展 Billing/BSS 只读 planner，新增 `usage-summary` / `usage-detail`，覆盖 `ListResourceUsageSummary` 和 `ListResourceUsage` 的 95 计费用量汇总与明细查询计划。
  - 扩展 Billing/BSS 只读 planner，新增 `on-demand-pricing` / `period-pricing`，覆盖官方 BSS 按需与包周期询价 API 的保守 request spec 和 reviewed safe_exec 命令计划。

- **CES datapoint 诊断**
  - 新增 `hcloud_ces_datapoint_plan.py`，生成并可执行受限的 CES `BatchListMetricData` 只读 datapoint 查询计划。
  - 对空数据、Agent、namespace、period、dimension 等常见排障原因做本地判读，避免把无数据直接误判为监控服务异常。

- **安全与版本治理**
  - Acceptance probe 执行增加目标安全策略：元数据/link-local 目标 hard-block，内网、loopback 和 `.local` 目标需要 `--allow-private-targets` 显式确认，HTTP probe 不跟随重定向。
  - `references/versioning-policy.md` 增加兼容入口退役节奏，用 v0.8/v0.9/v1.0 分阶段把 facade 过渡到真正收敛。

- **项目定位表达**
  - 优化 README，突出一个大 Skill、hcloud CLI-first、风险门禁、证据闭环和本地测试契约，降低新用户理解成本。

### 验证

- `.venv/bin/python -m unittest discover -s tests`：328 个测试通过，8 个 skipped。
- `git diff --check`：通过。

## v0.7 / 0.7.0 - 2026-07-03

v0.7 是一次收敛和纵深版本。它继续坚持“一个统一的大 Skill”路线：`hcloud` 仍然是云资源发现、执行和回读主链路，SDK、MaaS API 和 Terraform 只作为边界清晰的辅助能力面。这个版本的重点不是铺更多入口，而是把工具面收敛、把高频服务验证计划做深，并把账单、用量、监控和治理能力做成可测试的项目契约。

### 主要变化

- **统一入口收敛**
  - 新增 `hcloud_acceptance_closure.py`，作为 acceptance closure 的首选统一入口，提供 `plan`、`run`、`evaluate`、`chain` 子命令。
  - 新增 `hcloud_closure_plan.py`，统一 P0 lifecycle、P1 governance、P2 scenario closure planning。
  - 旧的 probe-plan、probe-run、evidence-result 和分层 closure planner 保留为兼容路径，但新流程默认选择统一入口。

- **SKILL.md 减负**
  - `SKILL.md` 精简为运行入口：统一大 Skill 定位、安全红线、默认工作流和 10 个以内首选入口。
  - 详细脚本说明下沉到 `references/scripts.md`，减少双份维护和入口选择负担。

- **真实账号验证规划**
  - 新增 `hcloud_live_validation_plan.py` 和 `references/live-validation-profiles.json`。
  - 面向 ECS、VPC/EIP、OBS、ELB、RDS 生成发现、计划、回读、probe、evidence 和晋级缺口，不自动执行云调用。

- **MaaS 用量治理**
  - `maas_usage_request_plan.py` 增加受控 `--execute`，支持只读 ShowStatistics 查询。
  - 明确 MaaS 用量统计走 AK/SK 签名，不是 `MAAS_API_KEY`；token 返回单位按“千 token”解释。
  - 环境体检、Terraform context 和 MaaS 用量规划支持 `HUAWEI_*` 凭据别名。

- **Billing/BSS 纵深增强**
  - `hcloud_billing_readonly.py` 扩展余额、账单流水、摊销、账户流水、资源包、券、订单、企业/伙伴账务和参考字典只读 planner。
  - 固化 `fact × grain × money_basis × scope/billing_period` 账单语义纪律。
  - 增加企业项目过滤、BSS 固定 CLI 默认值、KooCLI 点号参数和分页边界等防错规则。

- **账单、用量、监控和治理能力**
  - CES/ECS：补充 Agent 指标、`mem_used_percent` namespace、`ces.0014` 误诊风险和告警模板建议。
  - OBS：补充 `SYS.OBS` 指标、traffic vs bandwidth、请求数拆分汇总和容量统计边界。
  - COC：补充 `ServiceAgencyForCOC`、409 幂等、ControlMaster 和 60 秒清理模式。
  - Flexus L：补充 HCSS 控制面观察，并明确标记为 evidence gap，执行前必须复核。
  - CCE/UCS/SWR/DWS：补充云原生评估、fleet/policy 治理、镜像治理和数据库诊断方法论。

- **安全和诚实边界**
  - `hcloud_safe_exec.py` 增加 `CLI_ERROR` 识别和 KooCLI 日志排查建议。
  - `runtime-safety-boundaries.md` 增加凭据本地化和结果叙事真实性要求。
  - Terraform guardrails 明确区分 generated、validated、planned、applied、verified，不把 plan 或模板写成已上线。

### 验证

- `python3 -m unittest discover -s tests`：308 个测试通过。
- `python3 -m py_compile` 覆盖本轮关键脚本：通过。
- `python3 -m json.tool` 覆盖 Billing semantic catalog 和 CES metric guidance：通过。
- `git diff --check`：通过。

### 兼容性与安全说明

- v0.7 没有新增默认 Terraform apply、destroy、import 或 state 迁移自动化。
- v0.7 没有把 SDK 扩展为通用 mutation 执行面。
- live validation 仍然是 plan/evidence 规划，不代表所有服务都已在真实账号完成验证。
- Billing/BSS 仍然是只读 planning + 用户确认后的 safe_exec 路径；默认不读取真实账单。
- COC 和 Flexus L 仍保持高风险边界，未变成默认执行面。

## v0.6.2 / 0.6.2 - 2026-07-03

v0.6.2 在 v0.6.1 的 MaaS/API 基线之上，扩展为更完整的租户场景版本。它补齐上云、用云、管云的本地指导，同时保持单一 Skill 架构：`hcloud` 仍然是云资源执行与回读主链路，SDK/MaaS/Terraform 是边界清晰的辅助能力面，live 或会改变状态的步骤仍然必须经过显式门禁。

### 相比 v0.6.1 的变化

- 新增本地场景 playbook，覆盖：
  - OBS 静态网站托管和 Flexus 风格低成本建站。
  - ECS 监控排障、EIP 成本优化和 IAM 权限诊断。
  - CCI 工作负载就绪、SWR 镜像就绪和 FunctionGraph 就绪。
  - 生产 Web/API 就绪，覆盖计算、ELB、RDS、VPC/安全组、DNS/CDN/SCM/WAF、可观测、备份和成本。
  - MaaS 用量治理和 CCE 云原生评估。
- 新增 MaaS 用量和 CCE 评估 planner，可生成非执行型 evidence/request plan，不读取也不打印凭据。
- 新增 `hcloud_acceptance_probe_run.py`，用于运行现有 acceptance probe planner 生成的 HTTP、TCP、DNS、TLS 探针模板。
- 新增 `hcloud_live_regression_plan.py` 和 `references/live-regression-runbook.md`，让真实账号验证可以按输入、证据和风险边界进行规划。
- 新增 `hcloud_terraform_operations_plan.py` 和 `references/terraform/operations.md`，用于规划 Terraform import、drift review 和 remote state，并绑定 hcloud 回读与显式 state-change 门禁。
- 更新 scenario routing、script audience 边界、Terraform reference 和相关聚焦测试，覆盖这些新增本地资产。

### 验证

- `python3 -m unittest discover tests`：285 个测试通过。
- `python3 -m compileall -q scripts tests`：通过。
- `references/scenario-router.json`、`references/script-audience-manifest.json` 和 `references/terraform/catalog/terraform-reference-catalog.json` 的 JSON 解析通过。
- `git diff --check`：通过。

### 兼容性与安全说明

- v0.6.2 没有新增 Terraform apply 自动化、通用 SDK mutation 执行，也没有新增无门禁的云资源变更路径。
- live probe runner 只执行由探针模板生成的内置 HTTP/TCP/DNS/TLS 检查，不执行任意 shell 命令。
- Terraform import 仍然属于 state-changing 操作，只有在显式 `--execute-import`、`--allow-state-change` 和确认 token 门禁之后才允许执行。
- 真实账号回归仍然依赖用户环境；本地测试验证的是 planner 和架构契约，不代表真实华为云账号行为已经全部验证。

## v0.6.1 / 0.6.1 - 2026-06-22

v0.6.1 在保持 hcloud-first 云资源安全模型的同时，新增华为云 MaaS API 能力面，用于大模型任务。MaaS 按 API-first 能力处理，不作为 KooCLI service registry 入口。

### 相比 v0.6 的变化

- 新增华为云 MaaS API 能力面，支持本地模型目录查询、V2/OpenAI 兼容 chat、图像理解、图片生成/编辑，以及异步视频生成 helper。
- 新增 MaaS routing/reference 资产，让 Agent 可以选择模型、检查 dry-run payload，并处理视频生成的 `task_id` 轮询，同时不把 MaaS 当作 KooCLI service。
- 扩展环境就绪检查，支持通过 `MAAS_API_KEY` 和 `MODELARTS_MAAS_API_KEY` 检查 MaaS API Key，但不暴露密钥值。
- 新增 MaaS 在线文档发布链接和控制台创建 API Key 的指导，入口为 `管理与统计 > API Key 管理`。

### 验证

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests`：265 个测试通过。
- `python3 -m compileall -q scripts tests`：通过。
- `git diff --check`：通过。

## v0.6 / 0.6.0 - 2026-06-18

v0.6 turns the v0.5.1 closure-maturity baseline into a broader practical cloud-assistant release for beginner, small-business, and mid-enterprise users. It expands cost, environment setup, monitoring, Terraform review, low-cost hosting, permission troubleshooting, and inventory governance while keeping the hcloud-first safety model.

### Changes Since v0.5.1

- Adds BSS/Billing semantic routing, fixed `cn-north-1`/`cn` hcloud read-only command plans, pagination warnings, and a protected-identifier result summarizer.
- Adds v0.6 acceptance scenarios for beginner setup, low-cost website hosting, cost governance, CES metric troubleshooting, mid-enterprise governance, Terraform plan-review, and security-group reuse.
- Adds a script audience manifest so runtime, guarded-change, supplement, maintenance, internal-library, and compatibility scripts have explicit review boundaries before any future consolidation.
- Moves long runtime safety rules from `SKILL.md` into `references/runtime-safety-boundaries.md` and adds `references/versioning-policy.md` so release docs remain the version truth source.
- Adds cross-region/EPS inventory planning, scoped idle-audit summaries, and an IAM action hint catalog used by permission-error diagnostics.
- Adds COC readiness and entry-level web-hosting playbooks so low-cost OBS/Flexus/ECS website choices and remote-execution fallback paths are explicit.
- Adds a controlled Terraform generation guardrails reference and routes it as a core Terraform document.
- Expands curated Terraform examples from 55 to 73 with sanitized network, CCE, ELB/NAT reuse, end-to-end ECS/ELB/RDS, OBS/CDN/DNS, and RDS engine-shape stacks.
- Adds Terraform provider validation guidance for fmt/init/validate/schema/mirror/cache checks without adopting the upstream installer as an execution entry.
- Terraform context inspection now reports read-only Terraform CLI config, provider mirror, and provider cache hints without installing Terraform or downloading providers.

### Validation

- `python3 -m unittest discover tests`: 252 tests passed.
- `python3 -m compileall -q scripts tests`: passed.
- `git diff --check`: passed.
- `skill-creator` quick validation: passed.

### Compatibility and Safety Notes

- v0.6 does not add automatic live probes, generic SDK mutation execution, Terraform apply automation, or broad submit surfaces.
- Billing/BSS support is read-only planning plus approved safe_exec command plans and redacted result summarization; it does not default to live billing reads.
- Terraform remains a plan-review and IaC drafting aid in this release; import, drift automation, remote state, and blueprints are left for later v0.6.x work.
- Inventory, idle audit, and teardown review remain evidence and planning surfaces; candidates are not deletion, release, stop, or downsize approvals.
- COC readiness documents remote-execution boundaries and fallback decisions; it does not make COC a new default execution plane.

## v0.5.1 / 0.5.1 - 2026-06-17

v0.5.1 is a small closure-maturity patch after v0.5. It makes the recommended offline acceptance chain easier for agents and users to follow while keeping live execution boundaries unchanged.

### Changes Since v0.5

- P0 lifecycle plans now emit structured `acceptance_evidence_plan` items for cloud readback, runtime checks, protocol probes, observability, governance, and missing inputs.
- New acceptance tools:
  - `hcloud_acceptance_probe_plan.py` generates non-executing probe templates from lifecycle evidence requirements.
  - `hcloud_acceptance_evidence_result.py` evaluates collected local evidence into `passed`, `warning`, `missing`, or `blocked` outcomes.
  - `hcloud_closure_maturity_audit.py` reports closure tiers honestly instead of implying full closed-loop maturity where only planners exist.
- `SKILL.md`, scenario routing, and examples now describe the recommended chain: scenario route -> lifecycle closure plan -> acceptance probe plan -> evidence result.
- `examples/eip-acceptance-closure.md` adds a concrete offline EIP acceptance flow that users can copy into real validation work after supplying their own evidence.
- SDK supplement docs now include the local SDK `3.1.199` reference snapshot, installed-package runtime rules, auth/region/endpoint guidance, and narrow candidate rules for future read-only supplements.
- Terraform provider docs now include the local provider `1.93.0` snapshot, refreshed inventories covering 1689 resources and 2251 data sources, and stronger authentication/context guidance.
- New maintenance script: `hcloud_terraform_provider_inventory.py` rebuilds provider inventories from the local provider reference checkout and detects drift.
- Terraform context inspection now reports more provider environment aliases and warns when shared hcloud config is encrypted and therefore unsuitable for Terraform shared-config auth without an explicit risk decision.

### Validation

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests`: 225 tests passed.
- `python3 -m compileall -q scripts tests`: passed.
- `git diff --check`: passed.

### Compatibility and Safety Notes

- v0.5.1 does not add automatic live probes, Terraform apply automation, generic SDK execution, or Billing/BSS live queries.
- Acceptance probe plans are templates; users or guarded workflows must still collect real evidence explicitly.
- P1/P2 closure remains planner-only unless a service has a dedicated guarded flow.

## v0.5 / 0.5.0 - 2026-06-13

v0.5 makes Terraform a first-class, routed IaC asset plane inside `huaweicloud-skill` while preserving the hcloud-first safety model. It absorbs the prior standalone Terraform skill assets, adds catalog/context/router scripts, and keeps agents from browsing every Terraform example by default.

### Changes Since v0.4

- Terraform assets are now first-class local skill assets: 55 example stacks and supporting Markdown references are available through `examples/terraform/` and `references/terraform/`.
- New Terraform catalog, context inspection, and router scripts let agents choose a small number of relevant IaC assets while keeping hcloud as the discovery and verification path.
- Runtime artifacts remain excluded: `.terraform/`, state files, real tfvars, crash logs, and secrets must not be committed.
- Scenario routing now returns a Terraform next-hop with context inspection, router, workflow, and asset index paths when the user explicitly needs IaC.
- Active Terraform references and examples now use `hcloud` / `huaweicloud-skill` naming; the original source skill is retained only as an archive.
- `SKILL.md` frontmatter now passes `skill-creator` quick validation.

### Validation

- `skill-creator` quick validation: passed.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests`: 215 tests passed.
- `python3 -m compileall -q scripts tests`: passed.
- `git diff --check`: passed.

### Compatibility and Safety Notes

- v0.5 does not make Terraform an automatic apply path.
- Terraform plan/apply still requires local Terraform/provider readiness, exact plan review, and explicit user confirmation.
- hcloud remains the source of live discovery, readback, troubleshooting, and post-apply verification.
- SDK allowlists are unchanged; Terraform support does not expand generic SDK execution.

## v0.4 / 0.4.0 - 2026-06-13

v0.4 focuses on making the skill easier to use for real 上云/用云/管云 workflows without changing the safety model. The release adds a narrow SDK supplement layer, local scenario routing, service guides, Terraform workflow documentation, and keeps large generated catalog assets out of committed runtime files.

### Changes Since v0.3.3

- Removed the committed `references/hcloud-service-catalog.generated.json` full catalog so ClawHub packages do not include a file over 10M.
- Runtime catalog loading continues to use `references/hcloud-service-catalog.index.json` plus per-service files under `references/hcloud-service-catalog/`.
- `build_hcloud_catalog.py` now skips full catalog output by default; pass `--output <temporary-full-catalog-json>` only for local operation-level diff review.
- Adds a narrow SDK supplement layer:
  - Runtime discovery prefers installed `huaweicloudsdk*` Python packages.
  - The SDK source tree is only a maintenance/test fallback.
  - Executable SDK calls are limited to `references/sdk-supplement-registry.json` allowlisted read-only operations and keep hcloud fallback plans.
- Adds scenario routing and service guides:
  - `hcloud_scenario_router.py` maps broad natural-language goals to local playbooks, service guides, planners, SDK supplements, and Terraform candidates.
  - `references/guides/` covers ECS, VPC/network, ELB, RDS, CCE, OBS, observability, and governance boundaries.
- Adds `references/terraform-workflow.md` to keep Terraform as a separate IaC route with hcloud discovery before plan generation and hcloud verification after apply.

### Validation

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests`: 207 tests passed.
- `python3 -m compileall -q scripts tests`: passed.
- `git diff --check`: passed.

### Compatibility and Safety Notes

- v0.4 does not make SDK a generic execution plane.
- SDK execution is limited to allowlisted, low-risk, read-only operations and keeps hcloud fallback plans.
- Terraform remains a documented IaC route; it does not bypass hcloud discovery, explicit apply confirmation, or hcloud post-apply verification.
- The removed full generated catalog remains available only as an explicit local maintenance artifact, not a committed skill asset.

## v0.3.3 / 0.3.3 - 2026-06-06

v0.3.3 is a scenario-closure patch after v0.3.2. It includes the P1 governance completion work and adds P2 scenario closure planning so the skill now has three planner-only closure layers: P0 lifecycle, P1 governance, and P2 scenario services.

### Changes Since v0.3.2

- Completes P1 governance closure planning:
  - `hcloud_governance_closure_plan.py` now outputs read-only evidence command plans, target-scoped missing-parameter gaps, governance summaries, and curated promotion readiness for TMS, CTS, CBR, RMS/Config, Billing/BSS, WAF, DLI, and CodeArtsRepo.
  - Billing/BSS remains request-spec-only. The planner does not sign requests, accept billing credentials, send HTTP traffic, or generate live `hcloud BSS` query commands.
- Adds `hcloud_p2_scenario_closure_plan.py`:
  - Planner-only and non-executing by default.
  - Builds four-stage scenario plans: scenario scope, read-only evidence, risk boundary, and next closure steps.
  - Covers CCE, NAT, DCS, RFS, UCS, IAM/KPS/IMS dependencies, security posture, and database family.
- Clarifies P2 maturity:
  - CCE/NAT/DCS/RFS/UCS/IAM/KPS/IMS reuse existing curation profiles to generate read-only discovery and target-scoped query plans.
  - HSS, SecMaster, CFW, DBSS, KMS, GaussDB, GaussDBforNoSQL, GaussDBforopenGauss, DDS, DDM, and DWS stay metadata-backed evidence-gap plans.
  - Security and database-family coverage is intentionally not described as curated maturity.
- Updates user and developer documentation:
  - README, SKILL, script references, technical overview, implementation details, data/coverage, service coverage, lifecycle scenarios, changelog, and review planning docs now describe P1/P2 planner boundaries.

### Validation

- `python3 -m unittest discover -s huaweicloud-skill/tests`: 196 tests passed.
- `python3 -m compileall -q huaweicloud-skill/scripts`: passed.
- `git diff --check`: passed.

### Compatibility and Safety Notes

- v0.3.3 does not make P1 or P2 writes auto-executable.
- Governance, security, identity, key, cluster, NAT, cache, stack, fleet, and database mutations remain planner-only or hard-gated until dedicated guarded flows, tests, explicit confirmation, and post-change verification exist.
- Billing/Cost support remains request-spec planning only.
- Metadata-backed service presence is used for safe discovery and evidence-gap planning, not as a curated execution claim.

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
  - Runtime catalog loading now uses an index plus per-service JSON files; the full generated catalog was retained for compatibility and complete diffs in this release, and was later removed from committed assets for ClawHub packaging.
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
