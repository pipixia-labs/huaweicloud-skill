# Cloud Lifecycle Scenarios

本文用 ECS 和典型华为云服务举例，说明在执行“上云、用云、管云”任务时，使用 `huaweicloud-skill` 和不使用它的差别，以及这个 skill 在不同服务上具体承担哪些工作。

这里讨论的是 Agent 任务执行方式，不是用户手动学习 KooCLI 的教程。用户仍然用自然语言提出目标；`huaweicloud-skill` 负责把目标拆成可发现、可规划、可执行、可验证、可审计的步骤。

## 总体差异

| 维度 | 不使用 huaweicloud-skill | 使用 huaweicloud-skill |
| --- | --- | --- |
| 服务和 API 选择 | Agent 依赖模型记忆或临时猜测 service/operation 名。 | 先查 `service-registry.json`、generated catalog、本地 meta cache 和 `hcloud --help`，再选择 operation。 |
| 上下文确认 | 容易忽略 profile、region、project、domain、OBS endpoint 等前提。 | 先用 `hcloud_context_inspect.py` 检查本机 KooCLI、profile、region、project、认证和 cache。 |
| 命令构造 | 容易漏 `--cli-output=json`、漏必填参数、误把资源级查询当通用 list。 | 通过 discovery/query/planner 脚本生成 JSON-friendly 命令；目标型查询必须显式提供资源参数。 |
| 变更风险 | 创建、删除、绑定、扩容、开放端口等操作可能直接提交。 | 默认 plan-first；高风险操作需要 dry-run、显式确认、plan-bound token 和后置验证。 |
| 结果判断 | API 返回成功容易被当成任务完成。 | 区分 job 终态、资源终态、机内状态、应用可达性、日志/指标证据和治理证据。 |
| 错误处理 | 失败后靠自然语言猜是权限、region、参数还是网络问题。 | `hcloud_safe_exec.py` 输出结构化 `error_details`，便于分桶处理。 |
| 审计和恢复 | 多步任务中断后难以知道执行到哪一步。 | 多步 flow 可写脱敏 run journal，记录计划、dry-run、submit、verify 等事件。 |
| 治理视角 | 多数任务停留在“资源能创建/能查询”。 | 同时覆盖账号盘点、闲置审计、回收前检查、标签、备份、审计、合规、监控、日志和成本请求规划。 |

## 三类任务的执行方式

### 上云

上云任务通常包括创建 ECS、绑定 EIP、配置 VPC/安全组、挂载 EVS、接入 ELB、准备镜像和密钥。

不用 skill 时，Agent 往往会直接拼接创建命令，风险是上下文没确认、依赖资源不匹配、入方向端口过宽、登录方式不可用、job 成功后没有继续验证。

使用 skill 时，默认会做这些事情：

1. 检查 `hcloud`、profile、region、project 和认证上下文。
2. 发现或复核 VPC、Subnet、安全组、镜像、规格、KPS keypair 等依赖。
3. 用 planner 检查 JSON、必填字段、占位符、数量、登录方式和安全组风险。
4. 对可 dry-run 的变更先生成或执行 dry-run。
5. 真正提交前要求用户确认具体资源、region、project、费用影响、风险和回滚预期。
6. 提交后继续验证 job、资源状态、SSH/应用可用性和必要的网络可达性。

### 用云

用云任务通常包括确认资源健康、排查连接失败、验证 ELB 后端、检查 EVS 文件系统、确认 CES 指标、查询 LTS 日志、复核 RDS/OBS/CCE/CDN/DNS 等服务状态。

不用 skill 时，Agent 容易只看云资源状态字段，例如 ECS `ACTIVE`、EVS `in-use`、ELB listener 已创建，然后过早宣称业务可用。

使用 skill 时，默认会把“云侧状态”和“业务可用”分开：

1. 先做资源级 Show/List 查询，确认云资源存在和状态稳定。
2. 对 ECS 继续做 SSH 或 cloud-init/应用验收。
3. 对 EVS 区分“云盘已挂载”和“系统内已格式化、挂载、可读写”。
4. 对 ELB 区分 listener/pool/member 创建成功和后端服务真正 `ONLINE`。
5. 对 CES 先发现 namespace、metric、dimension，再选择时间范围和 period。
6. 对 LTS 只生成有限时间窗口和明确 group/stream 的只读日志查询。

### 管云

管云任务通常包括资源盘点、闲置治理、回收前检查、标签治理、备份姿态、审计追踪、合规检查、账单和成本分析。

不用 skill 时，Agent 可能把资源列表直接等同于治理结论，例如看到某个 EIP 未绑定就建议释放，看到 ECS stopped 就建议删除，或者从资源规格粗略推断费用。

使用 skill 时，默认会保持保守：

1. 账号盘点只做只读 inventory plan，真实查询需要显式 `--execute`。
2. 闲置审计只从保存的 JSON 查询结果识别候选，不生成删除、释放、退订、停机或缩容命令。
3. teardown plan 只输出依赖顺序和回收前检查项。
4. 标签、备份、审计、合规、日志等治理服务先进入 candidate profile 和 playbook，不把 catalog-derived 能力冒充 curated coverage。
5. Billing/Cost 当前只生成官方 API request spec，不签名、不发请求、不从资源清单推断费用。

## ECS 示例：创建并验收一台可登录服务器

### 不使用 skill 的常见问题

- 直接让模型记忆 `CreateServers` 参数，容易漏 `project_id`、`vpcid`、`subnet_id`、`security_groups`、`root_volume` 等字段。
- `key_name` 和 `adminPass` 处理不清，创建后没有可用登录凭据。
- 只检查 ECS API 返回或 job 成功，没有继续确认实例 `ACTIVE`。
- 没有验证 SSH、应用进程、端口监听和安全组入方向。
- 安全组可能开放 `0.0.0.0/0:22` 或常见 Web 端口。

### 使用 skill 的执行链

| 阶段 | huaweicloud-skill 做什么 |
| --- | --- |
| 上下文 | `hcloud_context_inspect.py` 检查 KooCLI、profile、region、project、认证和 cache。 |
| 依赖发现 | 用 IMS/KPS/VPC/EIP 等 discovery/query 路径复核镜像、密钥、VPC、子网、安全组和 EIP。 |
| 创建前计划 | `hcloud_ecs_create_plan.py` 校验 ECS JSON、必填字段、占位符、数量上限、登录方式和安全组风险。 |
| 风险控制 | 对 SSH 和常见 Web 端口阻断 `0.0.0.0/0`；复杂 body 推荐 `--cli-jsonInput`。 |
| dry-run/submit | 生成 safe-exec dry-run 和 submit 命令；真实 submit 需要显式确认。 |
| job 验证 | `hcloud_ecs_wait_job.py` 轮询 `ShowJob`，并标注 job 终态不等于 ECS 可用。 |
| 资源验证 | `hcloud_ecs_verify_active.py` 或等价查询确认目标实例存在且 `ACTIVE`。 |
| 机内验收 | 按 `ecs-ssh-access-readiness.md` 验证 SSH；如有应用，再进入 Web/Docker/ELB/EVS 等对应 playbook。 |
| 审计记录 | 多步任务可写 redacted run journal，便于中断恢复和复盘。 |

核心差异是：不用 skill 时，任务容易停在“创建请求成功”；使用 skill 时，任务会推进到“资源存在、状态稳定、可登录、应用或网络验收可解释”。

## 典型服务覆盖

### VPC 和安全组

| 任务 | huaweicloud-skill 做什么 |
| --- | --- |
| 上云 | 先确认 canonical VPC/subnet/security group；安全组规则创建前检查 CIDR、端口和协议风险。 |
| 用云 | 通过 `ShowVpc`、`ShowSubnet`、`ShowSecurityGroup`、`ShowSecurityGroupRule` 做目标型只读验证。 |
| 管云 | idle audit 可识别敏感端口公开、无引用或需要复核的安全组候选，但不生成删除命令。 |

不用 skill 时，Agent 容易直接补安全组规则，或者在 ELB/ECS 不通时反复重建 listener/member，而没有先确认 VPC/subnet 拓扑是否匹配。

### EIP

| 任务 | huaweicloud-skill 做什么 |
| --- | --- |
| 上云 | EIP 绑定/解绑走 `hcloud_eip_change_flow.py`，包含 plan、dry-run、plan-bound submit token 和 `ShowPublicip` 验证。 |
| 用云 | 查询公网 IP、绑定关系、带宽和状态，避免只看 ECS 内网状态。 |
| 管云 | idle audit 标记未绑定 EIP 为候选；释放前仍要求 owner、tag、依赖、监控和费用确认。 |

不用 skill 时，未绑定 EIP 容易被直接建议释放；使用 skill 时，它只是治理候选，不是释放授权。

### ELB

| 任务 | huaweicloud-skill 做什么 |
| --- | --- |
| 上云 | 创建 listener/pool/member 前确认 VPC、子网、后端 ECS 和协议端口。 |
| 用云 | 区分 listener/pool/member 创建成功和后端健康；通过 `ShowListener`、`ShowPool`、`ShowMember` 或 `ListMembers` 做验证。 |
| 管云 | idle audit 可标记无 listener、无 member 或后端异常的 ELB 候选。 |

不用 skill 时，Agent 可能只看到 listener 已创建就宣称服务可访问；使用 skill 时，会继续检查 backend member、健康状态和协议探测。

### EVS

| 任务 | huaweicloud-skill 做什么 |
| --- | --- |
| 上云 | 创建或挂载云盘前确认规格、AZ、目标 ECS 和挂载关系。 |
| 用云 | 区分 EVS `in-use` 和 ECS 内部文件系统已格式化、已挂载、可读写。 |
| 管云 | idle audit 标记 unattached volume 或 snapshot review candidate；删除前必须确认备份、文件系统、owner 和依赖。 |

不用 skill 时，容易把云侧挂载状态当成业务可用；使用 skill 时，会继续要求机内挂载和写入验收。

### RDS

| 任务 | huaweicloud-skill 做什么 |
| --- | --- |
| 上云 | 变更类任务进入 planner-only 或 guarded flow，要求备份、重启影响、规格和连接边界确认。 |
| 用云 | 通过实例、备份、参数模板和连接相关查询确认状态。 |
| 管云 | idle audit 标记 stopped/error、备份策略弱或需要生命周期复核的实例候选。 |

不用 skill 时，Agent 可能直接建议修改参数或规格；使用 skill 时，先把备份、维护窗口、重启和连接影响列为确认项。

### OBS

| 任务 | huaweicloud-skill 做什么 |
| --- | --- |
| 上云 | OBS 不走普通 OpenAPI-style `hcloud OBS Operation`，而是走 `hcloud obs`/obsutil 专用路线。 |
| 用云 | `hcloud_obs_readonly.py` 支持 bucket list/stat/lifecycle/policy 等只读检查。 |
| 管云 | `hcloud_obs_change_plan.py` 对 bucket、lifecycle、policy 做 planner-only，并识别 public ACL/policy 风险。 |

不用 skill 时，Agent 容易生成错误的普通 OpenAPI 命令；使用 skill 时，会走 OBS 专用适配器。

### CES 和 LTS

| 任务 | huaweicloud-skill 做什么 |
| --- | --- |
| 用云 | `hcloud_observability_plan.py` 先做资源状态复核，再用 CES `ListMetrics` 发现 metric namespace/dimension。 |
| 用云 | `hcloud_lts_readonly.py` 只生成有限时间窗口的 log group/stream/logs 只读查询。 |
| 管云 | `hcloud_ces_alarm_plan.py` 只做 alarm intent 草案，不创建或修改告警规则。 |

不用 skill 时，Agent 容易硬编码 metric 名或直接建议创建告警；使用 skill 时，先发现指标和日志范围，告警仍保持 planner-only。

### CTS、TMS、CBR、RMS、Config

这些服务主要服务“管云”。

| 服务 | 当前 skill 作用 |
| --- | --- |
| CTS | 提供审计 trail、trace、关键事件通知和 OBS 投递 readiness playbook。 |
| TMS | 提供标签 taxonomy、资源标签覆盖、成本分摊治理候选 playbook。 |
| CBR | 提供 vault、backup、policy、protectable resource 备份姿态候选 playbook。 |
| RMS / Config | 提供资源清单、policy state、aggregator、conformance pack 等合规治理候选 playbook。 |

这些服务当前是 candidate profile，不是 curated registry 覆盖。skill 会把它们用于治理候选和晋级审计，但不会把未补 live smoke 的能力说成稳定可执行能力。

### Billing 和 Cost

| 任务 | huaweicloud-skill 做什么 |
| --- | --- |
| 管云 | `hcloud_billing_cost_probe.py` 检查当前 KooCLI catalog 是否有 Billing/Cost 直接能力。 |
| 管云 | `hcloud_billing_readonly.py` 基于官方 API 路径生成 monthly bill summary、cost analysis、resource records 的 request spec。 |
| 边界 | 不接受 AK/SK，不签名，不发送 HTTP 请求，不从 ECS/EIP/RDS 等资源清单推断费用。 |

不用 skill 时，Agent 可能根据资源规格粗略估算费用并误导用户；使用 skill 时，费用和账单必须来自明确的账单/成本 API 路径或用户提供的数据。

## 如何判断 skill 是否真正帮上忙

一个任务使用 `huaweicloud-skill` 后，交付结果应该至少多出以下几类证据之一：

- 上下文证据：当前 profile、region、project、domain、OBS endpoint 是否匹配任务范围。
- API 证据：service/operation 是从 registry、catalog、metadata 或 live help 发现的，不是凭空猜的。
- 风险证据：费用、网络暴露、数据状态、删除/释放、权限和回滚边界被列出。
- 执行证据：dry-run、submit、job、resource verify 或 read-only query 的结构化结果。
- 业务证据：SSH、HTTP、ELB backend、EVS filesystem、CES metric、LTS log 等能证明“可用”的证据。
- 治理证据：owner、tag、backup、trace、compliance、billing request spec 或 teardown precheck。

如果一个回答只是给出一条 `hcloud` 命令，没有说明来源、上下文、风险、验证和边界，那它并没有真正发挥 `huaweicloud-skill` 的价值。
