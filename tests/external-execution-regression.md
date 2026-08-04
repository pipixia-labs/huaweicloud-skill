# 外部执行层回归清单

## 目的

本文把 2026-07-27 的 `全量评测报告+huaweicloud-skill` 和
`深度分析报告+huaweicloud-skill` 中可复现的执行层观察整理为回归清单。它补充
`unified-mechanism-evaluation.md` 的业务 task 行为评测，不替代多轮、跨服务、副作用恢复和完成准确性
评测。

外部报告只标明源码为 `v0.8+`，没有提供 commit，生成时间早于正式 `v0.8.2`。因此不能把报告中的
97.7% 通过率或 85 分当作任一正式版本的可复算基线。本清单只继承能够明确描述输入、执行边界和结果
证据的案例。

## 运行层级

| 层级 | 环境 | 默认自动运行 | 约束 |
| --- | --- | --- | --- |
| L0 | 纯函数、静态契约和本地 fixture | 是 | 不执行 hcloud，不读取凭据 |
| L1 | 临时 fake hcloud subprocess | 是 | 只验证 argv、输出、错误、脱敏和策略，不访问网络 |
| L2 | 真实 hcloud 只读查询 | 否 | 需要隔离 profile、明确 account/project/region 和输出脱敏 |
| L3 | 隔离账号中的真实变更闭环 | 否 | 需要逐次授权、费用/影响说明、唯一资源名、清理计划和清理证据 |
| EXT | MaaS 或其他外部服务兼容性 | 否 | 区分请求构造、Skill、云服务端和模型状态，不把外部 4xx 自动记为 Skill Bug |

L2、L3 和 EXT 不进入普通单元测试。缺少凭据、配额、模型、库存或隔离环境时标记 `not_run`，不能记为
通过或失败。

## 每次运行必须记录

- `run_id`、case ID、重复序号和开始/结束时间；
- Skill tag 和精确 commit；
- Python、hcloud 和相关 SDK/工具版本；
- Agent、模型、工具权限和 sandbox 边界；
- account/project/region 的脱敏标识，是否使用真实云和真实 mutation；
- 输入、退出码、结构化结果和脱敏 artifact；
- `pass`、`fail`、`not_run` 或 `not_observable`；
- 责任层：Skill、Agent、hcloud/SDK、云服务、模型服务或评测环境。

不得保存 AK/SK、API Key、密码、私钥、完整 token 或未脱敏原始响应。

## 自动回归

| Case ID | 层级 | 输入或故障 | 必须结果 | 当前自动证据 |
| --- | --- | --- | --- | --- |
| `ER-ARG-001` | L0/L1 | `--arg=server_id=server-1` | 规范化为 `--server_id=server-1`，并被版本解析、策略和最终命令共同使用 | `test_hcloud_safe_exec.py` |
| `ER-ARG-002` | L0/L1 | 已有 `--arg=--limit=5` 或短选项 | 不重复添加前缀，不改写已有 token | `test_hcloud_safe_exec.py` |
| `ER-ARG-003` | L0/L1 | 空值、首尾空白、换行或 NUL | 在启动 hcloud 前拒绝 | `test_hcloud_safe_exec.py` |
| `ER-ARG-004` | L1 | `--command-part=obs --command-part=ls` 加位置参数和已有前缀 option | command parts、`obs://` 等位置参数和已有 option 均保持原样 | `test_hcloud_safe_exec.py` |
| `ER-SEC-001` | L0/L1 | 输入和 JSON 输出含密码、token、user data 或私钥字段 | stdout、结构化结果和 artifact 均按契约脱敏 | `test_hcloud_safe_exec.py` |
| `ER-ERR-001` | L0/L1 | credential、permission、region、CLI 和 OpenAPI 错误 | 返回结构化分类、云错误码和可执行建议，不泄露秘密 | `test_hcloud_safe_exec.py` |
| `ER-OUT-001` | L1 | 高容量列表或超阈值 JSON | 应用默认范围、摘要和样本，不把完整 payload 放入 Agent 输出 | `test_hcloud_safe_exec.py` |
| `ER-OUT-002` | L1 | 文件内容或 file-only operation | 完整脱敏内容进入 artifact，普通 stdout 只保留摘要和路径 | `test_hcloud_safe_exec.py` |
| `ER-VERSION-001` | L0/L1 | 多版本 operation 和参数冲突 | mutation 不重放；只读仅在受限条件下纠正一次 | `test_hcloud_safe_exec.py` |
| `ER-GATE-001` | L0 | 创建、修改或删除计划 | 风险、dry-run、确认和回读边界保持，初始请求不等于 submit 授权 | guarded change 和架构契约测试 |

新增执行脚本或公共策略时，应先判断它是否改变以上契约，再增加差异化案例。不要为了追求用例数量复制
同一条断言。

## 受控 live 回归

### `ER-LIVE-READ-001`：跨服务只读查询

在固定 account/project/region 中选择 ECS、VPC、EIP、IAM 和 EVS 等代表性只读 operation。验证：

- 实际 operation、版本和参数有可追溯证据；
- 空列表是成功结果，不被写成 API 失败；
- 权限不足、region 错误和分页未完成分别表达；
- 大输出只返回摘要和 artifact；
- 不因一个服务查询成功声称账号盘点完成。

服务数量和非空资源数只描述本次 fixture，不作为固定通过阈值。

### `ER-LIVE-CHANGE-001`：OBS 最小生命周期

只有在隔离账号、明确授权和清理能力齐备时，执行唯一 bucket 的 plan、create、readback、delete 和
不存在确认。必须记录每个阶段的云侧证据；删除受理不等于清理完成。中途失败时先收敛已有资源，不得
用新 bucket 掩盖未知结果。

### `ER-EXT-MAAS-001`：MaaS 模型兼容性

固定模型、region、请求 schema 和调用时间，分别判断：

- 本地请求构造或响应解析是否错误；
- 认证、配额或 endpoint 是否错误；
- 模型 processor 或服务端是否拒绝有效请求；
- 异步 `task_id` 是否最终收敛。

外部服务端 4xx/5xx 只有在相同请求按官方契约应成功、且可排除本地构造问题时，才能归为外部兼容性
问题；证据不足时标记 `not_observable`。

## 性能观察

`ER-PERF-001` 只记录数据，不设置未经验证的硬阈值。至少分别测量：

- Python 进程启动；
- catalog 和 output policy 加载；
- 版本解析与脱敏；
- hcloud 本身和网络请求；
- 单次与批量任务总耗时。

需要同时报告 safe_exec 和直调的中位数、最小值、最大值、样本数和环境。只有在真实查询密集任务中
确认累计成本显著，才评审轻量索引、批处理或缓存；不能为了减少本地毫秒级开销绕开统一安全层。

## 汇总口径

- 每个 Case 单独报告运行数、通过、失败、未运行和不可观察数；
- 比例必须保留分子和分母，分母为零时写 `N/A`；
- secret 泄露、未授权 mutation、未知副作用重放和虚假完成属于硬失败；
- 不把 L0/L1 数量和 L2/L3 真实云结果混成一个总通过率；
- 不使用单一加权总分决定架构拆分或功能成熟度；
- 对外比较统一 Skill 与分散 Skills 时，另按 `unified-mechanism-evaluation.md` 固定 Agent、模型、
  workspace、权限和业务输入，再联合报告执行层与业务 task 层结果。
