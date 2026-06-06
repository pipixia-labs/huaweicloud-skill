# Implementation Details

本文解释 `huaweicloud-skill` 的关键实现。重点是脚本之间如何协作、每个脚本负责什么，以及扩展时需要注意哪些边界。

## 共享数据结构

`scripts/hcloud_core.py` 定义了少量轻量 dataclass：

| 类型 | 用途 |
| --- | --- |
| `CommandPlan` | 描述一个计划中的 hcloud 命令，包括 service、operation、命令数组、模式、是否需要 dry-run、警告等。 |
| `RiskAssessment` | 描述风险等级、原因、是否需要确认、是否需要 dry-run 和验证。 |
| `ExecutionResult` | 规范化命令执行结果。当前更多作为共享语义，而不是所有脚本都强制使用。 |
| `VerificationResult` | 规范化验证结果。 |
| `TaskState` | 多步任务的审计和恢复状态模型。 |

这些结构保持简单，便于 JSON 序列化，也便于脚本通过 stdout 传递结构化结果。

## 安全执行包装器

`scripts/hcloud_safe_exec.py` 是最重要的执行入口。它支持两种命令形态：

普通 OpenAPI-style 命令：

```bash
python3 scripts/hcloud_safe_exec.py \
  --service ECS \
  --operation ListServersDetails \
  --arg=--cli-region=cn-north-4 \
  --arg=--cli-output=json \
  --expect-json
```

通用命令片段，例如 `hcloud configure show` 或 `hcloud obs ls`：

```bash
python3 scripts/hcloud_safe_exec.py \
  --command-part=configure \
  --command-part=show
```

### 输出契约

成功或失败都会输出 JSON。核心字段包括：

| 字段 | 含义 |
| --- | --- |
| `success` | 逻辑成功。要求 return code 为 0 且没有识别到 KooCLI 错误类型。 |
| `return_code` | 子进程返回码。 |
| `duration_seconds` | 执行耗时。 |
| `service` / `operation` | 普通命令模式下的 service 和 operation。 |
| `command` | 脱敏后的实际命令数组。 |
| `stdout` / `stderr` | 脱敏和裁剪后的输出。 |
| `error_type` | KooCLI 错误类型，例如 `USE_ERROR`、`NETWORK_ERROR`、`OPENAPI_ERROR`、`APIE_ERROR`。 |
| `error_details` | 进一步结构化诊断，例如 `credential`、`permission`、`quota`、`network`。 |
| `advice` | 下一步建议。 |
| `parsed_json` | 当 `--expect-json` 开启且解析成功时的 JSON 结果。 |
| `parsed_json_error` | JSON 解析失败原因。 |

### 脱敏策略

脚本会从多个来源收集敏感值：

- `~/.hcloud/config.json` 中的 AK/SK/security token。
- 命令行参数中的 token、password、private key、user data 等。
- `--json-input-file` 或 `--json-input-text` 中可解析出的敏感字段。
- OBS obsutil 的 `-i`、`-k`、`-t`、`-token` 参数。

脱敏发生在命令、stdout、stderr 和 parsed JSON 中。

### 错误诊断

`hcloud_safe_exec.py` 先提取 KooCLI 粗粒度错误类型，再从文本和 JSON 中提取云侧错误码、错误消息，并匹配常见模式。

当前常见分类包括：

- `credential`
- `permission`
- `quota`
- `region_or_endpoint`
- `project`
- `parameter`
- `not_found`
- `network`
- `metadata`
- `cloud_api`
- `timeout`
- `local_environment`

上层脚本应该使用 `error_details.category` 判断下一步是让用户修凭证、换 region、补参数，还是停止重试。

## 上下文和元数据发现

### `hcloud_context_inspect.py`

这个脚本只读检查本地环境：

- `hcloud` 是否在 `PATH` 中。
- `hcloud version` 是否可运行。
- `~/.hcloud/config.json` 是否存在。
- 当前 profile、region、project、domain、offline mode 等。
- `~/.hcloud/metaRepo` 和 `~/.hcloud/metaOrigin` 的缓存状态。

它不暴露 AK/SK，只输出 `has_access_key`、`has_secret_key` 之类布尔值。

### `hcloud_meta_lookup.py`

这个脚本读取本地 KooCLI meta cache：

- `services_en.json`
- `template/<service>/apis_en.json`
- `template/<service>/*_en.yaml`
- `template/<service>/endpoints_en.json`

它支持：

- 列服务。
- 查某个 service 的 operation index。
- 查 operation detail，包括 HTTP method、path、参数、是否 required。
- 根据 region 过滤 endpoint。
- 在本地缓存不足时可选调用 `hcloud <service> --help` 作为 fallback。

脚本使用宽松 normalize 规则，把大小写、下划线、连字符差异统一成小写字母数字 token。

### `hcloud_prewarm_cache.py`

这个脚本用于预热 KooCLI 元数据和 help cache：

- 可执行 `hcloud meta download`。
- 可调用 `hcloud <service> --help`。
- 可调用 `hcloud <service> <operation> --help`。
- 支持 checkpoint，长任务中断后可以恢复。
- 输出前会脱敏。

它适合在连续处理大量华为云任务前运行。

## Registry 驱动的查询

`references/service-registry.json` 是查询构造的主控制面。通用查询脚本不直接假设某个 service 有哪些 operation，而是读取 registry。

### `hcloud_resource_discovery.py`

用途：为 `query_operations` 生成或执行 list-only 发现命令。

关键行为：

- 服务名统一转大写。
- operation 支持大小写宽松匹配，例如 `listcloudservers` -> `ListCloudServers`。
- 默认生成 `--cli-output=json` 和 `--expect-json`。
- 如果本地 operation detail 没有声明 `limit` 参数，则保守省略 `--limit`，并在输出中记录 `omitted_args`。
- 对 CDN 这类有 CLI region 限制的服务，使用 registry 中的 `supported_cli_regions` 和 `preferred_cli_region` 做 region resolution。
- 遇到 OBS 这类专用 runner，会拒绝走通用路径。

### `hcloud_resource_query.py`

用途：为 `resource_query_operations` 或需要显式参数的查询生成或执行命令。

关键行为：

- 从本地 metadata 和 `CURATED_REQUIRED_PARAMS` 合并 required params。
- 支持 operation alias，例如 `RDS ShowConfigurationDetail` -> `ShowConfiguration`。
- 缺参数时返回 `missing_params`，不会猜测资源 ID。
- 对敏感读取做风险检查。默认阻断 `ShowServerPassword`、私钥、token 等读取，除非显式 `--allow-sensitive-read`。
- 支持传入额外 raw `--arg`，但要求以 `--` 开头。

### `hcloud_readonly_smoke.py`

用途：多服务 read-only smoke。它按服务选一个优先 operation，例如：

- ECS: `ListServersDetails`
- VPC: `ListVpcs`
- EIP: `ListPublicips`
- OBS: `ListBuckets`

它可以只生成 plan，也可以 `--execute`。OBS 会路由到 `hcloud_obs_readonly.py`。

### `hcloud_service_readiness.py`

用途：服务级 readiness 检查。它不是只跑一个 smoke operation，而是为每个服务定义一组只读检查。

例如 VPC readiness 包括：

- `ListVpcs`
- `ListSubnets`
- `ListSecurityGroups`
- `ListSecurityGroupRules`
- `ShowVpc`，需要 `vpc_id`
- `ShowSubnet`，需要 `subnet_id`
- `ShowSecurityGroup`，需要 `security_group_id`

缺少目标参数的 detail 检查会标记为 skipped。默认情况下 skipped 不算失败；开启 `--require-all` 后会失败。

执行模式下：

- `--strict` 会让任何执行失败导致整体失败。
- 非 strict 模式下，云侧执行失败作为诊断保留，但 plan 失败仍然阻塞成功。

## 变更规划和风险门禁

### `hcloud_change_plan.py`

这个脚本只根据 operation 名称做通用风险判断和命令规划。

风险判断逻辑包括：

- `List`、`Show`、`Count`、`Get`、`Search` 等通常是 read-only。
- `Delete`、`Remove`、`Detach`、`Stop`、`Reset` 等是高风险。
- `Create`、`Attach`、`Bind`、`Resize`、`Update` 等是中风险。
- 涉及 password、private key、credential、secret、token 的读取是高风险敏感读取。
- 未识别的非 read-only 操作走保守中风险门禁。

输出包括：

- `risk`
- `commands.dryrun_or_plan`
- `commands.submit`
- `next_steps`

这个脚本不执行命令。

### `hcloud_service_change_plan.py`

这个脚本在通用风险判断外，叠加 service registry 的服务边界：

- 检查 service 是否注册。
- 检查 change operation 是否在 registry 中。
- 对未注册变更默认失败，除非显式 `--allow-unregistered`。
- 为服务提供上下文提示和验证提示。
- 生成 read-only smoke plan 作为变更前现状确认。
- 遇到专用 planner 时进行 delegation，例如 OBS -> `hcloud_obs_change_plan.py`。

它也不执行 submit。

### `hcloud_guarded_change_flow.py`

这个脚本是多服务变更门禁。它把 `hcloud_service_change_plan.py` 的 planner-only 输出包装成可审计的变更链：

```mermaid
flowchart LR
    Plan["service change plan"] --> DryRun["optional dry-run execution"]
    DryRun --> Guard["submit confirmation guard"]
    Guard --> Submit["optional submit execution"]
    Submit --> Target["target ID from submit or --verify-param"]
    Target --> Verify["resource Show* verification plan"]
    Verify --> Smoke["service read-only smoke"]
```

当前通用 guarded flow 覆盖：

- VPC
- ELB
- EVS
- NAT
- RDS
- CDN
- DNS
- SCM

EIP 使用 `hcloud_eip_change_flow.py`，ECS 使用 ECS 专用闭环，OBS 使用 `hcloud_obs_change_plan.py`。

关键行为：

- 默认只输出计划，不执行 dry-run、submit 或 verify。
- `--execute-dryrun` 才会执行 dry-run 命令。
- `--execute-submit` 必须同时带 `--confirm-submit` 和匹配当前计划的 submit token。
- medium/high 风险操作提交前必须已经 dry-run，或显式 `--skip-dryrun`。
- `--verify-param KEY=VALUE` 用于显式提供后置 Show* 查询所需目标 ID。
- `--verify-operation <ShowOperation>` 可覆盖内置推断，用于还没有登记 profile 的变更。
- `--execute-verify` 会执行资源级后置验证。

资源级验证 profile 会把变更 operation 映射到对应 Show* operation，例如：

| 服务 | 变更示例 | 后置验证 |
| --- | --- | --- |
| VPC | `CreateSecurityGroupRule` | `ShowSecurityGroupRule` |
| ELB | `CreateListener` | `ShowListener` |
| EVS | `CreateVolume` | `ShowVolume` |
| NAT | `CreateNatGatewayDnatRule` | `ShowNatGatewayDnatRule` |
| RDS | `CreateInstance` | `ShowInstanceConfiguration` |
| CDN | `CreateDomain` | `ShowDomain` |
| DNS | `CreateRecordSet` | `ShowRecordSet` |
| SCM | `ApplyCertificate` | `ShowCertificate` |

目标 ID 的来源有两个：

1. 显式参数：用户传入 `--verify-param security_group_rule_id=<id>`。
2. submit 结果：脚本从 `parsed_json` 中提取类似 `security_group_rule.id`、`listener.id`、`volume.id` 的字段。

如果缺少 required params，验证计划会返回 `missing_params`。这是有意设计：脚本不从列表结果里猜目标资源，避免把无关资源误报成变更成功。

删除类 operation 会在 `verification_profile` 中标记 `verification_intent=expect_absent_or_deleted_state`。这提醒调用方：delete 后 `not_found` 可能是预期结果，但仍需要结合具体服务语义判断。

## ECS 专用闭环

ECS 是当前覆盖最完整的服务。

```mermaid
flowchart LR
    Json["cli-jsonInput file"] --> Plan["hcloud_ecs_create_plan.py"]
    Plan --> DryRun["safe_exec dry-run command"]
    DryRun --> Submit["submit command with --confirm-submit"]
    Submit --> Job["hcloud_ecs_wait_job.py"]
    Job --> Active["hcloud_ecs_verify_active.py"]
    Active --> Done["ECS ACTIVE verified"]
```

### `hcloud_ecs_create_plan.py`

职责：

- 读取 ECS 创建 JSON。
- 校验必填路径，例如 project_id、name、AZ、flavorRef、imageRef、vpcid、subnet_id、root volume、count。
- 检查 unresolved placeholder，例如 `<project_id>`。
- 对 `count` 做保守数量限制，默认最多 10，API 上限 100。
- 检查登录方式和安全组风险。
- 生成 safe_exec 命令和裸 hcloud 命令。
- submit 模式必须显式 `--confirm-submit`。

### `hcloud_ecs_wait_job.py`

职责：

- 调用 ECS `ShowJob` 轮询异步 job。
- 识别 success、failure、running、unknown 状态。
- 连续命令失败达到阈值时停止。
- job 成功后仍提示必须做 ECS 资源 `ACTIVE` 验证。

### `hcloud_ecs_verify_active.py`

职责：

- 通过 `ListServersDetails` 轮询 ECS 实例。
- 支持按 server ID 或 name 匹配。
- 直到所有目标实例都达到 `ACTIVE`，或超时、连续失败。

这里的核心设计是：job 成功只说明异步任务结束，不说明服务器可用。

## EIP Plan -> Apply -> Verify

`hcloud_eip_change_flow.py` 是 EIP 的专用 guarded change flow。它把 EIP 变更串成：

1. service-aware plan。
2. 可选执行 dry-run。
3. guarded submit。
4. `ShowPublicip` 后置验证。

submit 有硬门禁：

- 必须传 `--execute-submit`。
- 必须传 `--confirm-submit`。
- 如果风险门禁要求 dry-run，则必须先 `--execute-dryrun`，或者显式 `--skip-dryrun`。

脚本会尝试从 submit 返回中提取 `publicip.id`，也支持用户显式传 `--publicip-id`。

## OBS obsutil 适配

OBS 使用 `hcloud obs`，不是普通 `hcloud OBS Operation`。

### `hcloud_obs_readonly.py`

支持只读 operation：

- `ListBuckets` -> `hcloud obs ls`
- `StatBucket` -> `hcloud obs stat obs://<bucket>`
- `GetBucketLifecycle` -> `hcloud obs lifecycle obs://<bucket> -method=get`
- `GetBucketPolicy` -> `hcloud obs bucketpolicy obs://<bucket> -method=get`

特点：

- 输出是 obsutil 文本，不是标准 OpenAPI JSON。
- 仍通过 `hcloud_safe_exec.py --command-part=obs ...` 执行。
- 会从文本中提取 bucket count 和 OBS 错误码。
- 对 `InvalidAccessKeyId`、`SignatureDoesNotMatch` 给出 OBS 凭证配置建议。

### `hcloud_obs_change_plan.py`

支持 planner-only change operation：

- `CreateBucket`
- `DeleteBucket`
- `PutBucketLifecycle`
- `DeleteBucketLifecycle`
- `PutBucketPolicy`
- `DeleteBucketPolicy`

它不执行 submit，也不假设 OBS 有通用 dry-run。输出包括 submit 命令和 read-only verification plan。

## 资源验证器

`hcloud_resource_verify.py` 对多服务 JSON 结果做统一资源状态验证。它和 `hcloud_guarded_change_flow.py` 的 Show* 后置验证互补：

- guarded flow 负责发起或生成目标资源的 Show* 查询计划。
- resource verifier 负责对已有 JSON payload 中的目标 ID、name、status、CIDR 或绑定关系做判断。

它解决的问题是：不同服务返回字段不完全一致。例如：

- EIP: `publicips`、`publicip`
- VPC: `vpcs`、`subnets`、`security_groups`
- ELB: `loadbalancers`、`listeners`、`pools`、`members`
- EVS: `volumes`、`snapshots`
- RDS: `instances`、`configurations`
- CDN: `domains`
- DNS: `recordsets`、`zones`

验证能力包括：

- 按 ID 或 name 匹配目标。
- 检查 status。
- 检查 CIDR。
- 检查绑定关系，例如 EIP 绑定到 port 或实例。
- 检查 top-level field 精确值。
- 支持直接读取 `hcloud_safe_exec.py` 输出中的 `parsed_json`。

验证器只验证 JSON 中已经存在的信息，不主动发起云查询。

## Run journal

`hcloud_run_journal.py` 是轻量 JSONL 事件记录器。它支持：

- append 一个 JSON event。
- 读取 events。
- 汇总 command、verification、failure 数量。

它适合多步真实操作的审计和断点恢复。不要把 AK/SK、token、密码、私钥写入 journal。

## 扩展一个新服务的建议流程

建议按小步迭代：

1. 用 `hcloud_meta_lookup.py --service=<SERVICE>` 检查本地 metadata。
2. 在 `references/service-registry.json` 增加服务条目。
3. 先增加少量 `query_operations`，优先 list/count/readiness 起点。
4. 如果有资源详情查询，增加 `resource_query_operations`，并在 `hcloud_resource_query.py` 中补 required params。
5. 在 `hcloud_service_readiness.py` 中增加 readiness profile。
6. 如需验证资源状态，在 `hcloud_resource_verify.py` 中补 collection keys、ID/name/status 字段处理。
7. 对 change operation 先纳入 planner-only，不直接开放 submit。
8. 如果变更可以映射到安全的 Show* 后置查询，在 `hcloud_guarded_change_flow.py` 增加 verify profile。
9. 增加 tests，至少覆盖 plan 生成、参数缺失、大小写 operation resolve、风险门禁和后置验证推断。
10. 再根据真实只读验证结果决定是否补 playbook 或专用 flow。

不要一开始就写真实 submit 自动化。先证明 read-only 和 verifier 稳定。
