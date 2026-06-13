---
name: huaweicloud-skill
description: 使用 hcloud 命令行工具执行华为云资源查询、分析、规划和变更。适用于用户明确要走 CLI/KooCLI 路线，或任务需要通过 hcloud 直接发现 service/operation、构造命令、执行查询或变更、排查认证、网络、缓存与输出格式问题的场景；当华为云部署静态站、独立站或 Web 应用需要图片素材时，可通过华为云 ModelArts MaaS 图像生成 API 生成本地站点资产。
version: "0.3.3"
---

# Huawei CLI Skill

## 核心定位

- 这是一套基于 `hcloud` 的华为云执行型 skill。
- SDK 是 `hcloud` 的补充，不是第二套大而全执行面。只有当 SDK 能让 `hcloud` 主链路更稳时才使用，例如补充参数类型、region/endpoint、错误结构、凭证来源线索，或执行少量 `references/sdk-supplement-registry.json` allowlist 内的稳定只读查询。
- 用户机器不要求有 SDK 源码仓库；如果需要 SDK 补充能力，优先使用已安装的 `huaweicloudsdk*` Python package。`reference-projects/huaweicloud-sdk-python-v3` 只作为本仓库维护期参考。
- 后续 Terraform 应作为 IaC 变更面接入；SDK 不承担通用创建、修改、删除等云变更职责。
- MaaS 图像生成只作为华为云 Web/独立站部署的辅助资产生成能力，必须使用华为云 ModelArts MaaS API，默认模型为 `qwen-image`，不作为通用生图入口，也不登记为 KooCLI service。
- 目标不是背命令，而是让 agent 能稳定完成一条完整链路：
  - 识别上下文
  - 发现 service 和 operation
  - 构造安全命令
  - 执行查询或变更
  - 校验结果
  - 处理常见错误

## 通用质量规则

这些规则面向真实云资源操作，不绑定任何内部场景。与其他说明冲突时，优先保证安全、可审计、可复现和可验证。

### 1. 异步任务必须跟到终态

- 创建或变更类命令返回 `job_id`、`server_id`、`accepted`、`submitted` 只表示请求已提交，不代表完成。
- 继续调用 `hcloud <Svc> ShowJob --job_id=...` 或对应的 `Show*` 查询，直到资源进入 `SUCCESS`、`ACTIVE`、`available` 等稳定终态。
- 在终态前，不要说"已完成"或"创建成功"；应说明当前状态、已提交的动作和下一步轮询方式。
- ECS 创建任务至少确认：job 成功、目标实例存在、实例状态为 `ACTIVE`。

### 2. 执行型任务要落到真实命令

- 用户要求部署、搭建、创建、开通、上线、绑定或修改资源时，除非用户只要方案咨询，否则不要只输出步骤清单。
- 先查询现状，再做必要的 `--dryrun` 或参数校验；确认风险边界后，执行实际的 `Create*`、`Update*`、`Bind*`、`Attach*` 等命令。
- 如果因为权限、配额、产品未开通、参数缺失、计费风险或安全边界无法继续，停止无效重试，给出已执行命令、关键返回、阻塞原因和需要谁处理。

### 3. 定量问题必须返回具体值

- 规格、价格、配额、售卖 SKU、可用区、镜像、实例类型等问题，要尽量返回具体 ID、数值、状态或列表。
- 优先用 `hcloud <Svc> List*`、`Show*`、`*SellPolicies`、`ShowQuota*` 等命令获取结构化结果。
- 如果账号或区域查不到数据，说明已调用的命令、返回为空或权限不足，不要退化成泛泛产品介绍。

### 4. 缺省参数先发现再选择

- 创建类任务缺少 image、flavor、AZ、VPC、subnet、keypair、root volume 等常见参数时，优先通过查询选择合理默认值，不要过早追问。
- 用户没有指定资源名时，使用稳定、语义化、可复用的名称，而不是每轮随机名；例如应用数据盘可使用 `disk-<workload>-data`，公共入口可使用 `lb-<workload>-<role>`，健康检查占位服务可使用 `ppx-health-<port>`。后续修复必须先按这些名称查询并复用。
- 对“应用数据盘”“大一点的数据盘”“挂到 /data”这类缺少明确磁盘容量的任务，先根据用户目标、现有系统盘大小、成本风险、配额和区域可售规格推断容量/类型。若只是为了一般应用数据落盘，选择普通高性能 SSD/GPSSD 类数据盘通常更稳；最终说明选择依据和可调整项。
- 推荐顺序：
  1. 复用同 region 下最近一条 `ACTIVE` 同类资源的参数组合。
  2. 从公共列表里选普通、可用、低风险的默认项，例如 Linux 公共镜像、通用计算规格、可用 AZ、已有 VPC/子网。
  3. 若会产生明显费用、公网暴露、数据风险或业务命名歧义，再向用户确认。
- 最终回复要说明自动选择了哪些默认值，方便用户复核或覆盖。

### 5. 输出必须可核验

- 查询类任务结尾给出数据来源：核心 `hcloud` 命令、region、project 前缀和返回条数。
- 创建或变更类任务结尾给出动作链：创建/变更命令、job 或资源 ID、终态查询命令、最终状态。
- 不要把表格输出当成唯一证据；保留关键原始字段，例如资源 ID、状态、IP、CIDR、规格、端口和时间。
- 明确需求、方案确认、任务结果展示或排障时，可用 Mermaid `flowchart` 输出资源拓扑图，帮助用户确认资源关系和连通路径。
- 拓扑图必须区分计划态和已验证态：计划态节点标注“计划/待创建/待复用/待确认”，结果态节点只放 `hcloud` 查询或协议探测确认过的资源事实。
- 图里优先放关键字段：资源类型、名称、ID 短前缀、IP、状态、端口、CIDR、安全组来源、绑定关系和阻塞点；复杂场景先画核心链路，不要一次画满所有资源。
- 不要凭空画不存在或未查询到的资源；如果是推测关系，必须在节点或连线上标注“推测/待验证”。

### 6. 可达服务必须闭环验证

- Web、Docker Remote API、数据库、负载均衡后端等任务不能只停在资源 `ACTIVE`；还要验证进程、端口和应用协议。
- 如果要依赖 `cloud-init` 安装软件，创建前把脚本做成幂等流程：先创建父目录，再写配置；先配置软件源，再安装；最后 `enable`、`restart` 服务。
- 对外可达服务至少检查三层：安全组规则、EIP/监听器/后端绑定、协议探测结果，例如 HTTP 200、Docker `/version` JSON、数据库连接成功。
- ELB 后端必须确认成员 `operating_status=ONLINE`；若 `CONNECT_FAILED`，优先排查后端安全组、服务进程是否监听、健康检查端口/路径、后端子网 ID 是否匹配。
- ELB、NAT、VPC 路由等网络编排任务必须先确定 canonical VPC/subnet。后端 ECS 分属不同 VPC、member subnet 与 ECS 网卡不匹配、或 ELB 与后端网络不可达时，不要反复重建 listener/member；VPC peering 不是普通 ELB instance member 的默认修复方式，除非用户明确要求跨 VPC 后端且 API 明确支持 IP target。对新建、演示、测试、无状态服务或可替换部署资源，可以重装/重建不兼容后端并保留用户要求的资源名；对需保留状态的既有业务资源，只输出拓扑阻塞和最小变更建议。
- 如果没有远程命令能力，可用 EIP + 协议探测验证；如果协议探测不通，不要宣布应用部署成功。

### 7. 安全组入口端口必须收敛

- 安全组入方向规则中，SSH 端口 `22` 和常见 Web 入口端口 `80`、`443`、`3000`、`5000`、`8000`、`8080` 不允许使用 `0.0.0.0/0` 作为来源。
- 即使用户目标是公网访问，也不要自动生成或提交上述端口到全网来源的规则；应让用户提供固定客户端 IP、办公网 CIDR、VPN CIDR、跳板机/堡垒机来源、负载均衡来源或私网 CIDR。
- 创建或修改安全组规则前，必须明确 `direction`、`protocol`、端口范围和来源 CIDR；若来源是 `0.0.0.0/0` 且端口命中上述清单，应停止提交并输出安全策略违规原因。
- ECS 创建参数若只引用已有安全组 ID，提交前要查询 `ListSecurityGroupRules` 或 `ShowSecurityGroup` 复核入方向规则；不要假设已有安全组是安全的。

### 8. ECS 初始化和远程排障

- 复杂 ECS 创建优先使用 `--cli-jsonInput` 或临时 JSON 文件，避免超长单行命令、base64、嵌套数组参数被 shell 转义破坏。
- 创建 Linux ECS 前必须先选定 SSH 登录凭证模式：`key_name` 加本地可用私钥，或 `adminPass` 加已保存的密码 artifact；两者不要同时设置，两者都不可用时不要提交创建。
- 若创建 keypair 用于后续 SSH，必须把返回的 private key 保存到受限权限文件，例如 `chmod 600`，并记录 keypair 名称；否则不要把 SSH 当成可用降级路径。优先使用 `KPS CreateKeypair` 新建任务专用 keypair 并保存返回的 `private_key`，不要只引用无法导出私钥的旧 keypair。
- 若使用 `adminPass`，密码必须在创建前生成并保存到受限权限 artifact；不要依赖日志或 `ShowServerPassword` 事后找回 Linux root 密码。
- ECS 创建完成不能只停在 `ACTIVE`；需要继续用选定凭证执行 SSH 验收，至少跑通 `echo SSH_OK && id && hostname`，否则不要宣称服务器可登录。
- 如果 ECS 创建后还需要安装软件、启动服务、挂载磁盘或做应用验收，创建时必须预埋可纳管通道：可用 keypair private key、cloud-init 完成目标脚本、或明确可用的密码登录配置。不要把“创建 ECS 成功”当作后续机内动作可执行的保证；没有 COC 时，保存私钥和 cloud-init 是默认必选项。
- 创建公网可访问 ECS 时，如果目标安全组不存在或缺少 22/80/443 入方向，先按 VPC/企业项目查询现有安全组和规则；若 `CreateSecurityGroupRule` / `vpc:securityGroupRules:create` 被 SCP 或 IAM 显式拒绝，不要反复补规则，可复用已有同时满足目标端口、VPC/企业项目和风险边界的安全组，并在最终输出说明安全组名称与用户原命名要求的偏差。
- `cloud-init` 脚本中写 `/etc/docker/daemon.json`、systemd drop-in、Nginx 站点配置等文件前，先 `mkdir -p` 父目录。
- 对 Ubuntu 安装 Docker，优先选择当前区域可达的官方/云镜像源；安装失败时可降级为发行版仓库中的 `docker.io`，并说明降级影响。
- 远程暴露 Docker TCP 2375 属于高风险配置；只有用户明确要求时才开放，并在最终输出中提示这是未加密管理端口。

### 9. 幂等修复与保守收敛

- 创建前按资源名做幂等查询；发现同名资源时先读 `references/playbooks/resource-idempotency-reconcile.md`，选择 canonical resource 修复，不要继续创建同名资源。
- ECS 内服务、Docker Remote API、ELB HTTP 后端这类可达性任务，应优先读取对应 readiness playbook，使用可重复执行的初始化和验收流程。
- 收敛规则必须保守：只在明确硬阻塞、同一失败已基于新证据修复至少两轮仍无进展、或后续只剩外部等待且继续执行不会改变状态时，才停止并输出部分完成结果。
- 只要还有明确、低风险、与用户目标直接相关的下一步，不要提前交卷；也不要把未通过协议探测或健康检查的组件写成已完成。

### 10. 机内执行和 SSH fallback

- 涉及 ECS 内部状态的任务，例如格式化/挂载数据盘、写 `/etc/fstab`、安装软件、启动后端服务、执行 `docker info`，必须先区分“云侧资源已挂载/已配置”和“机内系统已生效”。
- 首选通道：创建 ECS 时的 cloud-init/user_data、已经可用的远程命令/COC、用户已提供或本地已验证可用的 SSH 凭据。
- 新建、演示、测试、部署类资源默认可重建/重装，除非用户明确说要保留系统盘状态。对于这类资源，不能因为缺 COC 就把任务停在云侧配置；应通过保存私钥、cloud-init、或重装/重建纳管继续打通流程。
- 如果任务是创建、部署、配置或验收类，且 COC/远程命令不可用，可以把受控 SSH fallback 视为通用纳管步骤，而不是硬阻塞：
  1. 对新建 ECS：先用 `KPS CreateKeypair` 创建任务专用 keypair，把响应里的 `private_key` 保存到 `~/.cloud-ppx/keys/huawei/<region>/<keypair>.pem` 或 `$CLOUD_PPX_KEY_DIR` 下并 `chmod 600`，ECS 创建 body 使用该 `key_name`。创建后立即用 `ssh -i` 验证。
  2. 对已有 ECS：先找本地已保存的 private key；若 ECS 有 keypair name，再尝试 `KPS ExportPrivateKey`，只有拿到私钥并验证成功才把 key 登录视为可用。
  3. key 不可用时，用 `ShowResetPasswordFlag` 确认目标 ECS 支持在线重置密码。
  4. 生成一次性强密码，调用 `ECS ResetServerPassword`；密码只保存在受限临时 artifact 或当前会话中，不在最终回复展示。
  5. 只为受限来源 CIDR 创建临时 TCP 22 入站规则；来源应是用户给定管理员 IP、当前执行环境 `/32`、VPN/办公网或跳板机来源，不要为了省事开放全网。
  6. 用 `sshpass`/SSH 依次验证 root 和镜像默认用户；若 `Permission denied` 且 `user_data` 或 sshd 配置显示禁用密码登录，不要重复 reset password。
  7. 对本轮新建、演示、测试或可替换部署资源，若 key/password 都不可用且 COC 不可用，直接重装或同名重建为可纳管实例：保存 private key，并在 cloud-init 中完成目标服务、挂载脚本和 SSH 配置。重建前确认该资源不是用户明确要求保留数据的生产资源。
  8. 登录成功后执行幂等机内脚本，完成格式化挂载、服务启动、日志采集和验收。
  9. 验收通过后删除临时 SSH 入站规则；若因后续维护需要保留，最终输出规则 ID 和原因。
- SSH/recreate fallback 不应用于删除、读取用户隐私数据、扩大业务端口暴露面，或用户明确要求只读的场景。
- 如果 COC 不可用、无可用 key/托管私钥、密码登录被系统策略拒绝、且不能在当前任务边界内重建/重装，再停止无效重试并说明最小缺口。
- ELB member `OFFLINE` 且后端端口 `connection refused` 时，结论应是“负载均衡云侧配置已完成，后端服务未启动”；只有实际启动服务并看到 member `ONLINE` 与入口 HTTP 200 后，才能说任务完成。
- EVS volume `in-use` 只表示云侧已挂载；只有 `df -h <mountpoint>` 和写入测试成功，才能说目录可用。

## 什么时候使用

优先在以下场景使用本 skill：

- 用户明确提到 `hcloud`、`KooCLI`、CLI、命令行方式管理华为云。
- 任务需要直接通过 `hcloud` 查询或变更华为云资源。
- 任务需要查看 `service` / `operation` 列表、构造 `--cli-jsonInput`、使用 `--cli-query`、`--dryrun`、`--cli-waiter` 等 CLI 能力。
- 任务需要排查 `hcloud` 的认证、区域、项目、缓存、网络、输出格式问题。
- 任务是在华为云 ECS/OBS/CDN 等 Web 载体上部署站点，并明确要求用华为云 MaaS 图像生成能力生成站点图片资产。


## 资料入口

先看整理后的资料，再回到原始材料：

1. `references/workflow.md`
2. `references/auth-and-context.md`
3. `references/cache-prewarm.md`
4. `references/local-meta-discovery.md`
5. `references/service-coverage.md`
6. `references/sdk-supplement.md`
7. `references/scenario-router.json`
8. `references/guides/`
9. `references/terraform-workflow.md`
10. `references/command-construction.md`
11. `references/error-playbook.md`
12. `references/output-and-query.md`
13. `references/scripts.md`
14. `references/service-registry.json`
15. `references/service-curation-profiles.json`
16. `scripts/hcloud_catalog_audit.py`
17. `references/playbooks/`
18. `references/source-map.md`
19. `examples/README.md`
20. `references/maas-image-generation.md`（MaaS 图像生成主参考；`references/qwen-image-generation.md` 为兼容旧文件名）

原始 KooCLI 材料在 `materials/` 下，仅作为资料源，不应直接当作最终指令集使用。
华为云官方文档优先从 `https://support.huaweicloud.com/intl/zh-cn/` 查证；涉及 API 字段语义时，以官方文档和实际 `hcloud --dryrun`/查询结果为准。

## 默认工作流

1. 先确认上下文
   - 优先运行 `python3 scripts/hcloud_context_inspect.py --pretty`
   - 明确 `hcloud` 是否可用、当前 profile、默认 region、project、offline mode、meta cache 是否存在
   - 如果 `hcloud.found=false`，停止真实云查询和变更；提示用户先按华为云官方快速安装文档安装 KooCLI：`https://support.huaweicloud.com/qs-hcli/hcli_02_003.html`
   - 在 `hcloud` 可执行前，只能基于本 skill 的本地资料输出命令方案草稿，不要宣称已查询或修改华为云资源
2. 先发现，再执行
   - 先看 `hcloud --help`
   - 再看 `hcloud <service> --help`
   - 能拿到 operation 帮助时，再看 `hcloud <service> <operation> --help`
3. 查询类默认稳定化
   - 默认使用 `--cli-output=json`
   - 需要提炼时再加 `--cli-query`
   - 大结果默认先限制 `limit` 或筛选字段
   - `ListImages`、`ListFlavors`、`ListFlavorSellPolicies` 等大列表 API 默认视为高风险大输出；如果需要全量或大范围核验，优先考虑 `--result-file` / `--parsed-json-file` 落盘，只把条数、关键字段样本、摘要和文件位置带回对话
4. 复杂参数不要硬拼长命令
   - 优先 `--skeleton`
   - 或使用 `--cli-jsonInput`
5. 变更类先做预执行
   - 默认先用 `python3 scripts/hcloud_change_plan.py ...` 生成风险摘要和 dry-run/submit 命令
   - 支持 dry-run 的操作默认先加 `--dryrun`
   - 复杂创建类优先先补齐依赖项，再进入真实执行
6. 返回为空时显式校验
   - 为空不代表失败
   - 必要时加 `--debug` 查看状态码
7. 失败时按错误类型处理
   - 先看 `references/error-playbook.md`
   - 不要在未知错误上反复重试同一个命令

## 推荐脚本入口

详细命令模板和参数边界放在 `references/scripts.md`。这里仅保留任务到脚本的选择索引；需要具体命令时再读取该 reference。

| 任务 | 首选脚本 | 说明 |
| --- | --- | --- |
| 上下文/认证/region/project 检查 | `hcloud_context_inspect.py` | 真实云任务第一步。 |
| 自然语言场景路由 | `hcloud_scenario_router.py` | 把目标映射到本地 playbook、指南、planner、SDK 补充点和 Terraform 候选；不执行云操作。 |
| 多轮任务前缓存预热 | `hcloud_prewarm_cache.py` | 预热 service/operation help。 |
| 真实 hcloud 查询或系统命令 | `hcloud_safe_exec.py` | 默认 JSON、脱敏、错误分桶。 |
| 本地 KooCLI metadata 探查 | `hcloud_meta_lookup.py` | 查 service/operation detail cache。 |
| SDK 参数/region 补充 | `hcloud_sdk_catalog.py` | 读取已安装 SDK package 或维护期源码 fallback；只补证据，不执行云调用。 |
| SDK allowlist 只读桥 | `hcloud_sdk_readonly.py` | 仅执行 `sdk-supplement-registry.json` 登记的稳定只读补充；保留 hcloud fallback。 |
| generated catalog 审计/重建 | `hcloud_catalog_audit.py`、`build_hcloud_catalog.py` | 运行时走 index/per-service 懒加载；full catalog 只作为可选本地临时产物，不提交、不直接 Read 大 JSON。 |
| ECS 创建前校验 | `hcloud_ecs_create_plan.py` | 检查 JSON、凭证、安全组和 dry-run/submit 命令。 |
| ECS job 终态 | `hcloud_ecs_wait_job.py` | job 终态不等同于 ECS 可用。 |
| ECS ACTIVE 验证 | `hcloud_ecs_verify_active.py` | 之后还要做 SSH/应用验收。 |
| list/count 资源发现 | `hcloud_resource_discovery.py` | registry 或 metadata-backed discovery；默认不执行。 |
| 账号资源盘点 | `hcloud_account_inventory.py` | 核心服务跨服务只读盘点 planner；`--execute` 才真实查询。 |
| 闲置资源审计 | `hcloud_idle_audit.py` | 从已保存 JSON 查询结果识别 EIP/EVS/ECS/ELB/RDS/NAT 闲置候选，不生成删除命令。 |
| 拆除/回收评审计划 | `hcloud_teardown_plan.py` | 从 idle audit 候选生成 planner-only 回收检查顺序；不生成 submit 命令。 |
| 可观测前置计划 | `hcloud_observability_plan.py` | 为资源生成状态复核 + CES 指标发现的只读闭环计划。 |
| CES 告警计划 | `hcloud_ces_alarm_plan.py` | CES metric/alarm 只读发现 + 告警规则 planner-only 草案，不 submit。 |
| LTS 日志只读查询 | `hcloud_lts_readonly.py` | LTS log group/stream/logs 只读 planner；日志内容要窄范围处理。 |
| 成本/账单能力探测 | `hcloud_billing_cost_probe.py` | 本地 catalog feasibility probe；不访问真实账单，不承诺已有 Billing API。 |
| 成本/账单请求规划 | `hcloud_billing_readonly.py` | 基于华为云官方 Billing/Cost API 生成只读请求 spec；不签名、不发请求。 |
| 显式参数只读查询 | `hcloud_resource_query.py` | 目标型 `Show*`/`Get*` 必须显式传参。 |
| OBS 只读查询 | `hcloud_obs_readonly.py` | 走 `hcloud obs`/obsutil，不走普通 OpenAPI 形态。 |
| 服务 readiness | `hcloud_service_readiness.py` | 多服务只读验收，缺目标 ID 则 skipped。 |
| 生命周期闭环计划 | `hcloud_lifecycle_closure_plan.py` | P0 核心服务的六阶段 planner-only 闭环计划，覆盖 VPC/安全组、EIP、EVS、ELB、RDS、OBS、DNS、SCM、CDN、CES/LTS。 |
| 治理闭环计划 | `hcloud_governance_closure_plan.py` | P1 治理服务的 planner-only 闭环计划，覆盖 TMS、CTS、CBR、RMS/Config、Billing/BSS、WAF、DLI、CodeArtsRepo，并输出 evidence command plan 和治理汇总。 |
| P2 场景闭环计划 | `hcloud_p2_scenario_closure_plan.py` | P2 场景服务的 planner-only 闭环计划，覆盖 CCE、NAT、DCS、RFS、UCS、IAM/KPS/IMS、安全姿态和数据库族，并诚实标注 metadata evidence gap。 |
| Terraform/IaC 工作流 | `references/terraform-workflow.md` | 当用户明确需要可重复 IaC、环境复制或长期纳管时读取；Terraform 不替代 hcloud 发现和后置验证。 |
| registry 多服务 smoke | `hcloud_readonly_smoke.py` | 只读 smoke；`--execute` 才真实查询。 |
| metadata-backed smoke | `hcloud_catalog_readonly_smoke.py` | 小批只读矩阵和失败分桶。 |
| curated 晋级审计 | `hcloud_curated_promotion_audit.py` | 校验 profile、playbook、risk profile 和 live-smoke 门槛。 |
| 通用变更风险计划 | `hcloud_change_plan.py` | 非执行 planner，含安全组入口策略检查。 |
| 服务级变更计划 | `hcloud_service_change_plan.py` | curated + metadata-backed planner-only。 |
| 通用 guarded change flow | `hcloud_guarded_change_flow.py` | 普通服务 Plan -> dry-run -> guarded submit -> verify。 |
| EIP guarded flow | `hcloud_eip_change_flow.py` | EIP 专用闭环。 |
| OBS 变更计划 | `hcloud_obs_change_plan.py` | OBS bucket/lifecycle/policy planner-only。 |
| 离线资源验收 | `hcloud_resource_verify.py` | 从 JSON 结果验证资源字段，不访问云端。 |
| 问题集/覆盖回归 | `check_question_coverage.py` | 离线 schema、风险和执行路径门禁。 |
| MaaS 站点图片资产 | `maas_text_to_image.py` | 仅用于华为云站点部署图片资产；`qwen_text_to_image.py` 为兼容旧入口。 |

变更类脚本的共同边界：默认只生成计划；真实 submit 必须有用户对本次操作的明确确认。metadata-backed mutation 的 dry-run 默认为 `unknown`，安全合规、身份、密钥和治理类服务会进入 `hard_guard`，通用 guarded flow 不得自动执行 submit。

## 默认执行规则

- 不要为了默认上下文就先追问 AK/SK。
- 当前配置可用时，优先复用已有 profile。
- 系统参数统一优先使用 `cli-*` 新参数名。
- 查询类默认走 JSON 输出，不默认走 table。
- 复杂 body 优先 `--cli-jsonInput`，不要手工拼几百字符命令。
- ECS 创建类 JSON 先用 `hcloud_ecs_create_plan.py` 检查占位符和关键字段。
- ECS 创建类 JSON 必须通过登录凭证门禁：`key_name` 和 `adminPass` 二选一；选择 `key_name` 时说明本地私钥验证方式，选择 `adminPass` 时说明密码 artifact 保存位置。
- ECS 创建类 JSON 写入安全组前，先确认该安全组已有任务要求的入方向端口；当补规则被 `vpc:securityGroupRules:create` SCP/IAM 拒绝时，允许复用同 VPC/企业项目内已开放所需端口的现有安全组，但必须记录原目标安全组、复用安全组 ID/规则和拒绝错误。
- 变更类默认先查证据，再用 `hcloud_change_plan.py` 生成风险计划，再 `--dryrun`，再执行。
- ECS 创建类真实提交后，必须先用 `hcloud_ecs_wait_job.py` 或等价 `ShowJob` 查询 job 终态，再用 `hcloud_ecs_verify_active.py` 或等价查询确认目标实例 `ACTIVE`。
- ECS `ACTIVE` 后必须按 `references/playbooks/ecs-ssh-access-readiness.md` 做 SSH 验收；如果目标任务还包含 Web/Docker/WordPress 等应用，再进入对应服务 readiness。
- `--cli-waiter` 有重复调用风险，默认只建议用于查询或状态轮询。
- 华为云站点部署中如需生成图片资产，先读取 `references/maas-image-generation.md`，通过华为云 ModelArts MaaS 生成本地资产并完成图片质量检查后再部署。
- 如果 live help 因网络或元数据问题失败，改走本地 meta cache 和 `references/`，不要瞎猜参数。

## 当前版本覆盖

当前版本重点覆盖以下内容：

- Huawei CLI 基本上下文探查
- Huawei CLI 本地 meta cache 发现
- `hcloud` 命令发现与构造
- CLI 认证、区域、项目和缓存问题排查
- ECS 查询与创建前准备
- ECS 创建 JSON 本地校验、dry-run 命令生成、job 终态轮询和 ACTIVE 资源验证
- service registry、只读资源发现、通用变更风险计划、run journal、材料漂移检查和问题集回归检查
- 账号资源盘点 planner 和离线闲置资源候选审计，面向“管好云”的只读摸底与治理前置分析
- planner-only teardown review，用于按依赖顺序评审闲置候选的回收前检查，不直接执行删除/释放/退订
- 基于 CES `ListMetrics` 的可观测前置计划，用于先发现 namespace/metric/dimension，再结合资源状态和协议验收判断健康
- CES alarm planner-only 和 LTS read-only 日志查询 planner，配套 `references/playbooks/observability-readiness.md`
- Billing/Cost 目前先生成官方 API request spec，不从资源清单推断费用，也不默认执行真实账单查询
- Billing/Cost 本地 feasibility probe，用于确认当前 bundled catalog 是否具备账单/成本直接候选；v0.3.1 可发现 metadata-backed `BSS`，但当前不等同于真实账单查询能力
- curated promotion audit 输出 `value_ranked_candidates`，用于按“上好云、用好云、管好云”价值维度选择下一批治理候选
- `hcloud_lifecycle_closure_plan.py` 提供 P0 核心服务的 planner-only 闭环计划入口，覆盖 VPC/安全组、EIP、EVS、ELB、RDS、OBS、DNS、SCM、CDN、CES/LTS，并把上下文/依赖发现、参数检查、风险门禁、受控执行、后置验证和治理审计统一成六阶段输出
- `hcloud_governance_closure_plan.py` 提供 P1 治理闭环计划入口，覆盖 TMS、CTS、CBR、RMS/Config、Billing/BSS、WAF、DLI、CodeArtsRepo，把治理范围、只读 evidence command plan、风险/隐私门禁、review plan、治理汇总和 curated 晋级缺口统一输出；Billing/BSS 只生成 request spec，不生成 live query 命令
- `hcloud_p2_scenario_closure_plan.py` 提供 P2 场景闭环计划入口，覆盖 CCE、NAT、DCS、RFS、UCS、IAM/KPS/IMS、安全姿态和数据库族，把容器、网络、缓存、IaC、多集群、依赖、安全、数据库场景先收敛成只读 evidence plan、风险边界和下一步晋级缺口；安全和数据库族当前保持 metadata evidence gap，不宣称 curated 完整闭环
- VPC / IMS / KPS / IAM / EIP 创建前只读发现方法
- VPC / IMS / KPS / ELB / EVS / NAT / DNS / SCM 等服务的第一层资源级只读查询登记
- ELB / EVS / NAT / RDS / CCE / CDN / DNS / SCM / CES 的低覆盖查询登记，用于离线数据集回归和前置发现
- 多服务只读 smoke、planner-only 变更计划和 JSON 结果验收脚本
- MaaS 图像生成辅助脚本，用于华为云站点部署时通过华为云 ModelArts MaaS 生成本地 Web 图片资产；主入口为 `maas_text_to_image.py`，旧 `qwen_text_to_image.py` 保留兼容
- OBS `hcloud obs`/obsutil 只读适配器和 planner-only bucket/lifecycle/policy 变更计划
- `hcloud_resource_detail_probe.py` 可对 EVS/NAT 等服务做 list-then-detail 抽样，有资源时执行 detail，无资源时结构化 skipped

当前对 ECS 的 guidance 最完整。P0/P1/P2 已分别形成 lifecycle、governance、scenario 三类 planner-only 闭环计划。对 IAM、VPC、IMS、KPS、EIP、DCS、RFS、UCS 主要提供工作流、发现方法和部分目标查询；对 ELB、EVS、NAT、RDS、CCE、CDN、DNS、SCM、OBS、CES 提供低覆盖查询登记、第一层目标查询和 planner-only 计划。安全姿态和数据库族长尾服务仍以 metadata-backed evidence gap 为主，不等同于 curated registry 覆盖；Billing/Cost 当前只生成 request spec，不执行真实账单请求。

当前版本已经补了本地 meta cache 发现脚本和创建类示例模板；非 ECS 服务的 operation detail 缓存可能不完整，脚本会在缺少参数元数据时保守省略可选参数。

## 示例模板

示例文件放在 `examples/` 下。

当前重点提供：

- ECS `CreateServers` 的 `cli-jsonInput` 模板
- ECS `CreatePostPaidServers` 的 `cli-jsonInput` 模板
- 对应的 dry-run 命令说明

这些示例主要用于：

- 构造可审查的请求骨架
- 指导用户替换真实 ID 和参数
- 避免把几十个字段硬编码进一行命令

## 禁止事项

- 不要把 raw `materials/` 当成唯一事实来源直接复述。
- 不要在未确认上下文前直接执行高风险删除或不可逆变更。
- 不要把真实 AK/SK、token、密码写进文档、日志或最终回复。
- 不要把表格输出当成机器可稳定解析的默认格式。
- 本 skill 负责 CLI/KooCLI 路线；Terraform、MCP、IaC 等路线只在用户明确要求或项目路由规则指定时接管。
