# Architecture

`huaweicloud-skill` 是一个基于华为云 KooCLI (`hcloud`) 的执行型 skill。它的目标不是让模型记住所有云命令，而是把云资源操作拆成一条可审计、可验证、可扩展的执行链路。

核心链路是：

1. 检查本机 `hcloud` 上下文。
2. 发现 service、operation 和参数线索。
3. 根据机器可读 registry 生成命令或变更计划。
4. 通过统一包装器执行命令。
5. 对返回结果做结构化错误诊断、资源状态验证和后续检查。

当前架构重点是十个平面：

- **路由/指南面**：`hcloud_scenario_router.py`、`references/scenario-router.json` 和 `references/guides/` 把自然语言目标映射到本地 playbook、planner、SDK 补充点和 Terraform 候选。
- **控制面**：`references/service-registry.json` 决定服务、operation、runner、planner、verifier 和 known limits。
- **执行面**：`hcloud_safe_exec.py` 统一执行、脱敏、JSON 解析和错误诊断。
- **SDK 补充面**：`references/sdk-supplement-registry.json` 控制允许的 SDK supplement；`hcloud_sdk_catalog.py` 和 `hcloud_sdk_readonly.py` 使用已安装的 `huaweicloudsdk*` package 或维护期源码 fallback，补充参数类型、region/endpoint、错误结构和少量 registry allowlist 只读查询；不作为通用变更执行面。
- **IaC 资产面**：`hcloud_terraform_context_inspect.py`、`hcloud_terraform_router.py`、`references/terraform/catalog/` 和 `examples/terraform/` 负责 Terraform 环境检查、资产路由和示例渐进加载；`references/terraform-workflow.md` 定义 plan/validate/apply/verify 流程和 hcloud 后置验证边界。
- **MaaS API 面**：`references/maas-model-calls.md`、`references/maas-model-catalog.json` 和 `scripts/maas_*.py` 负责华为云 MaaS 模型 API 的 dry-run、payload 构造、调用和异步任务查询；不进入 KooCLI service registry。
- **验证面**：job waiter、resource query、resource verifier、service readiness 分层确认结果。
- **闭环面**：`hcloud_lifecycle_closure_plan.py` 把 VPC/安全组、EIP、EVS、ELB、RDS、OBS、DNS、SCM、CDN、CES/LTS 的 P0 典型任务组织成六阶段 planner-only 闭环。
- **治理/场景面**：账号盘点、闲置审计、teardown review、可观测、Billing/Cost request spec、P1 governance closure、P2 scenario closure 和 curation profiles 支持生命周期治理和后续场景演进。
- **回归面**：单测、架构契约、materials drift 和 coverage 检查持续约束实现。

## 顶层结构

```text
huaweicloud-skill/
├── SKILL.md
├── README.md
├── references/
├── scripts/
├── examples/
├── materials/
├── tests/
└── docs/
```

各目录职责：

| 路径 | 职责 |
| --- | --- |
| `SKILL.md` | 面向 agent 的入口，定义触发场景、质量规则和默认工作流。 |
| `references/` | 清洗后的操作资料，包括 workflow、playbook、错误手册、服务覆盖矩阵和 service registry。 |
| `scripts/` | 可执行 Python 脚本，负责上下文探查、命令生成、安全执行、规划、验证和 coverage 检查。 |
| `examples/` | 可复用的输入模板和示例，例如 ECS 创建 JSON。 |
| `materials/` | 原始 KooCLI 文档材料，只作为资料源，不直接作为运行时规则。 |
| `tests/` | 单测、架构契约测试和人工验证记录。 |
| `docs/` | 当前目录，面向开发者解释架构和实现。 |

## 架构总览

```mermaid
flowchart TD
    UserTask["User cloud task"] --> Skill["SKILL.md"]
    UserTask --> Router["hcloud_scenario_router.py"]
    Router --> ScenarioMap["references/scenario-router.json"]
    ScenarioMap --> Guides["references/guides/*.md"]
    ScenarioMap --> Workflow
    ScenarioMap --> TerraformRouter["hcloud_terraform_router.py"]
    TerraformRouter --> TerraformCatalog["references/terraform/catalog/*.json"]
    TerraformCatalog --> TerraformExamples["examples/terraform/*"]
    TerraformCatalog --> TerraformRefs["references/terraform/*.md"]
    TerraformRouter --> TerraformRef["references/terraform-workflow.md"]
    TerraformInspect["hcloud_terraform_context_inspect.py"] --> TerraformRef
    ScenarioMap --> MaasRef["references/maas-model-calls.md"]
    MaasRef --> MaasScripts["maas_models.py / maas_chat.py / maas_image_generation.py / maas_video_generation.py"]
    MaasCatalog["references/maas-model-catalog.json"] --> MaasScripts
    MaasScripts --> MaasAPI["Huawei Cloud MaaS API\napi.modelarts-maas.com"]
    Skill --> Workflow["references/workflow.md"]
    Skill --> Registry["references/service-registry.json"]
    Workflow --> Context["hcloud_context_inspect.py"]
    Workflow --> Meta["hcloud_meta_lookup.py / hcloud_prewarm_cache.py"]
    Registry --> Discovery["hcloud_resource_discovery.py"]
    Registry --> Query["hcloud_resource_query.py"]
    SDKRegistry["sdk-supplement-registry.json"] --> SDKMeta["hcloud_sdk_catalog.py\nSDK metadata supplement"]
    SDKRegistry --> SDKRead["hcloud_sdk_readonly.py\nallowlisted SDK read-only"]
    SDKMeta --> Query
    Registry --> Closure["hcloud_lifecycle_closure_plan.py"]
    Registry --> Scenario["hcloud_p2_scenario_closure_plan.py"]
    Registry --> ChangePlan["hcloud_service_change_plan.py"]
    Registry --> Guarded["hcloud_guarded_change_flow.py"]
    Registry --> Readiness["hcloud_service_readiness.py / hcloud_readonly_smoke.py"]
    Closure --> ChangePlan
    Closure --> Readiness
    Scenario --> Discovery
    Scenario --> Query
    Discovery --> SafeExec["hcloud_safe_exec.py"]
    Query --> SafeExec
    ChangePlan --> SafeExec
    Guarded --> SafeExec
    Readiness --> SafeExec
    SafeExec --> HCloud["hcloud / hcloud obs"]
    HCloud --> Result["Structured JSON result"]
    Result --> Verify["Show* query / resource verifier / ECS waiters"]
    Verify --> Report["Auditable final state"]
    Materials["materials/ raw docs"] --> References["references/ curated docs"]
    References --> Workflow
    TestsInput["tests fixtures / registry"] --> CoverageGate["check_question_coverage.py"]
    CoverageGate --> Registry
    Tests["tests/ contract and unit tests"] --> Registry
    Tests --> Discovery
    Tests --> Query
    Tests --> ChangePlan
    Tests --> Verify
```

## 设计原则

### 1. 发现优先，不靠记忆

华为云服务和 KooCLI operation 很多，参数形态也会变化。skill 的设计不是硬编码所有命令，而是按顺序使用：

1. `references/service-registry.json`
2. 本地 `~/.hcloud/metaRepo`
3. `hcloud <service> --help`
4. `hcloud <service> <operation> --help`
5. `references/` 和 `materials/`

这样可以减少模型猜参数造成的错误。

### 2. 查询和变更分流

查询类脚本默认生成 JSON 友好的 read-only 命令，例如：

- `hcloud_resource_discovery.py`
- `hcloud_resource_query.py`
- `hcloud_readonly_smoke.py`
- `hcloud_service_readiness.py`

变更类脚本默认只生成计划或 dry-run 命令，例如：

- `hcloud_change_plan.py`
- `hcloud_service_change_plan.py`
- `hcloud_ecs_create_plan.py`
- `hcloud_eip_change_flow.py`
- `hcloud_guarded_change_flow.py`
- `hcloud_obs_change_plan.py`

真实 submit 需要显式确认，尤其是创建、绑定、扩容、删除、停用、证书变更等可能产生费用或影响可用性的操作。通用 guarded flow 会把 planner 输出进一步包成 dry-run、submit 确认门禁、资源级 Show* 后置验证和服务级 read-only smoke。

### 3. 所有执行都尽量经由 safe exec

`hcloud_safe_exec.py` 是统一执行包装器。它负责：

- 构造 `hcloud` 子进程命令。
- 收集并脱敏本地 profile、命令参数和 JSON 输入中的敏感值。
- 解析 JSON 输出。
- 识别 KooCLI 错误类型。
- 生成结构化 `error_details`。
- 控制超时和输出长度。

上层脚本尽量输出 `python3 scripts/hcloud_safe_exec.py ...`，而不是直接输出裸 `hcloud ...`。

### 4. 机器可读 registry 是服务覆盖控制面

`references/service-registry.json` 是多服务能力的中心索引。它说明每个服务：

- 覆盖等级。
- 是否需要 region。
- 哪些 operation 可作为通用 list/query 起点。
- 哪些 operation 必须显式传资源 ID。
- 哪些 change operation 只允许 planner-only。
- 是否有专用 runner。
- 已知限制和 playbook。

通用脚本通过 registry 决定如何构造命令，而不是在脚本里散落大量服务判断。

## 执行链路

### 查询类链路

```mermaid
sequenceDiagram
    participant Dev as Developer or Agent
    participant Registry as service-registry.json
    participant Discovery as hcloud_resource_discovery.py
    participant Query as hcloud_resource_query.py
    participant Safe as hcloud_safe_exec.py
    participant CLI as hcloud
    participant Verify as hcloud_resource_verify.py

    Dev->>Registry: Check service coverage and operation scope
    alt list-only query
        Dev->>Discovery: Build plan for query_operations
        Discovery->>Safe: Generate safe_exec command
    else resource-scoped query
        Dev->>Query: Provide explicit target params
        Query->>Safe: Generate safe_exec command
    end
    Safe->>CLI: Execute hcloud command
    CLI-->>Safe: stdout/stderr/return code
    Safe-->>Dev: Structured JSON result
    Dev->>Verify: Optional service-specific state verification
```

`query_operations` 和 `resource_query_operations` 的边界很重要：

- `query_operations` 是通用发现入口，例如 `ListVpcs`、`ListInstances`、`ListPublicips`。
- `resource_query_operations` 必须有目标上下文，例如 `ShowVpc`、`ShowPublicip`、`ShowLoadBalancer`。

脚本不会替用户猜资源 ID。缺少显式目标参数时，`hcloud_resource_query.py` 会失败并返回 `missing_params`。

### 变更类链路

```mermaid
flowchart LR
    Request["Change request"] --> Plan["hcloud_service_change_plan.py"]
    Plan --> Risk["hcloud_change_plan.assess_risk"]
    Risk --> DryRun["dry-run or plan command"]
    DryRun --> Confirm["Explicit user confirmation"]
    Confirm --> Submit["Submit command"]
    Submit --> Target["Extract or provide target ID"]
    Target --> Show["Resource Show* verification"]
    Show --> Smoke["Service read-only smoke"]
    Smoke --> Ready["Ready or blocked result"]
```

目前具备多类闭环能力：

- ECS：创建 JSON 本地校验、dry-run、submit 命令生成、`ShowJob` 轮询、`ACTIVE` 验证。
- P0 任务闭环：`hcloud_lifecycle_closure_plan.py` 为 VPC/安全组、EIP、EVS、ELB、RDS、OBS、DNS、SCM、CDN、CES/LTS 生成任务级六阶段闭环计划，不执行真实 submit。
- P1 治理闭环：`hcloud_governance_closure_plan.py` 为 TMS、CTS、CBR、RMS/Config、Billing/BSS、WAF、DLI、CodeArtsRepo 生成治理范围、只读证据、风险/隐私门禁和晋级缺口，不执行治理写操作。
- P2 场景闭环：`hcloud_p2_scenario_closure_plan.py` 为 CCE、NAT、DCS、RFS、UCS、IAM/KPS/IMS、安全姿态和数据库族生成场景范围、只读证据、风险边界和下一步闭环动作，不执行场景写操作。
- EIP：Plan -> dry-run -> guarded submit -> `ShowPublicip` verify 的参考 flow。
- VPC / ELB / EVS / NAT / RDS / CDN / DNS / SCM：通用 Plan -> dry-run -> guarded submit -> resource Show* verify -> read-only smoke 的 P0 门禁。
- OBS：obsutil planner-only 变更计划和后置只读验证计划。

这些闭环不表示可以无确认自动 submit。任务级 closure plan 只负责把上下文、参数、风险、执行链、验证链和治理跟进结构化；真实 dry-run、submit 和 verify 仍由现有 guarded flow、专用 flow 或人工确认流程控制。

## 模块分层

```mermaid
flowchart TB
    subgraph RuntimeRules["Runtime rules"]
        Skill["SKILL.md"]
        Workflow["references/workflow.md"]
        Playbooks["references/playbooks/*.md"]
    end

    subgraph ControlPlane["Control plane"]
        Registry["references/service-registry.json"]
        Coverage["references/service-coverage.md"]
        Sources["references/materials-sources.json"]
    end

    subgraph ExecutionScripts["Execution scripts"]
        Context["hcloud_context_inspect.py"]
        Meta["hcloud_meta_lookup.py"]
        Safe["hcloud_safe_exec.py"]
        Discovery["hcloud_resource_discovery.py"]
        Query["hcloud_resource_query.py"]
        Planner["hcloud_change_plan.py / hcloud_service_change_plan.py"]
        Guarded["hcloud_guarded_change_flow.py"]
        Verifier["hcloud_resource_verify.py"]
    end

    subgraph SpecializedFlows["Specialized flows"]
        ECS["hcloud_ecs_create_plan.py / wait_job / verify_active"]
        EIP["hcloud_eip_change_flow.py"]
        OBS["hcloud_obs_readonly.py / hcloud_obs_change_plan.py"]
    end

    subgraph Quality["Quality gates"]
        UnitTests["tests/*.py"]
        Drift["check_materials_drift.py"]
        CoverageCheck["check_question_coverage.py"]
    end

    RuntimeRules --> ControlPlane
    ControlPlane --> ExecutionScripts
    ExecutionScripts --> SpecializedFlows
    Quality --> ControlPlane
    Quality --> ExecutionScripts
    Quality --> SpecializedFlows
```

## 服务覆盖等级

覆盖等级不是华为云服务成熟度，而是本 skill 内部自动化能力的成熟度。

| 等级 | 含义 |
| --- | --- |
| `high` | 有较完整的 planner、playbook、验证器和实际验证路径。当前主要是 ECS。 |
| `medium` | 有稳定查询、readiness 或专项 guarded flow，但复杂业务语义验证仍不完整。 |
| `low` | 有最小查询入口、资源级查询或通用 guarded change 线索，仍依赖显式参数、账号权限和后续人工确认。 |

维护者扩展服务时，应先补 read-only 查询和验证，再补 planner-only 变更，最后再考虑 guarded submit。

当前 registry 的服务数和 operation 计数以 `python3 scripts/hcloud_catalog_audit.py --pretty` 的 `registry` 字段为准。这些数字不是服务成熟度承诺，而是当前自动化控制面的机器可读范围。

## OBS 的特殊性

OBS 不是普通的 `hcloud <Service> <Operation>` 形态。它走 KooCLI 集成的 obsutil：

```text
hcloud obs <command> ...
```

所以 OBS 在 registry 中配置了专用 runner：

- `scripts/hcloud_obs_readonly.py`
- `scripts/hcloud_obs_change_plan.py`

通用 `hcloud_resource_discovery.py` 和 `hcloud_resource_query.py` 会拒绝普通 OBS 查询，避免生成错误的 `hcloud OBS Operation` 命令。

## 关键不变量

开发时需要保持以下不变量：

- 查询类默认 JSON 输出：`--cli-output=json` 和 `--expect-json`。
- 变更类默认 plan/dry-run，不默认 submit。
- 资源级查询必须显式传目标参数。
- 通用 guarded flow 缺少目标 ID 时必须返回 `missing_params`，不得猜测资源。
- 异步 job 成功不等于资源可用，必须继续做资源状态验证。
- 敏感读取默认阻断，例如密码、私钥、token。
- registry 中配置的 runner、planner、playbook 路径必须存在或有明确 known limit。
- docs、references、tests 和 registry 要保持同步。
