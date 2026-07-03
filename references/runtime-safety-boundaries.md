# Runtime Safety Boundaries

这份 reference 承接 `SKILL.md` 中的运行安全边界。处理真实云资源操作、执行型任务、ECS 纳管、网络暴露、应用验收或排障时读取。与其他说明冲突时，优先保证安全、可审计、可复现和可验证。

## 1. 异步任务必须跟到终态

- 创建或变更类命令返回 `job_id`、`server_id`、`accepted`、`submitted` 只表示请求已提交，不代表完成。
- 继续调用 `hcloud <Svc> ShowJob --job_id=...` 或对应的 `Show*` 查询，直到资源进入 `SUCCESS`、`ACTIVE`、`available` 等稳定终态。
- 在终态前，不要说“已完成”或“创建成功”；应说明当前状态、已提交的动作和下一步轮询方式。
- ECS 创建任务至少确认：job 成功、目标实例存在、实例状态为 `ACTIVE`。

## 2. 执行型任务要落到真实命令

- 用户要求部署、搭建、创建、开通、上线、绑定或修改资源时，除非用户只要方案咨询，否则不要只输出步骤清单。
- 先查询现状，再做必要的 `--dryrun` 或参数校验；确认风险边界后，执行实际的 `Create*`、`Update*`、`Bind*`、`Attach*` 等命令。
- 如果因为权限、配额、产品未开通、参数缺失、计费风险或安全边界无法继续，停止无效重试，给出已执行命令、关键返回、阻塞原因和需要谁处理。

## 3. 定量问题必须返回具体值

- 规格、价格、配额、售卖 SKU、可用区、镜像、实例类型等问题，要尽量返回具体 ID、数值、状态或列表。
- 优先用 `hcloud <Svc> List*`、`Show*`、`*SellPolicies`、`ShowQuota*` 等命令获取结构化结果。
- 如果账号或区域查不到数据，说明已调用的命令、返回为空或权限不足，不要退化成泛泛产品介绍。

## 4. 缺省参数先发现再选择

- 创建类任务缺少 image、flavor、AZ、VPC、subnet、keypair、root volume 等常见参数时，优先通过查询选择合理默认值，不要过早追问。
- 用户没有指定资源名时，使用稳定、语义化、可复用的名称，而不是每轮随机名；例如应用数据盘可使用 `disk-<workload>-data`，公共入口可使用 `lb-<workload>-<role>`，健康检查占位服务可使用 `ppx-health-<port>`。
- 对“应用数据盘”“大一点的数据盘”“挂到 /data”这类缺少明确磁盘容量的任务，先根据用户目标、现有系统盘大小、成本风险、配额和区域可售规格推断容量/类型。
- 推荐顺序：复用同 region 下最近一条 `ACTIVE` 同类资源的参数组合；从公共列表里选普通、可用、低风险默认项；若会产生明显费用、公网暴露、数据风险或业务命名歧义，再向用户确认。
- 最终回复要说明自动选择了哪些默认值，方便用户复核或覆盖。

## 5. 输出必须可核验

- 查询类任务结尾给出数据来源：核心 `hcloud` 命令、region、project 前缀和返回条数。
- 创建或变更类任务结尾给出动作链：创建/变更命令、job 或资源 ID、终态查询命令、最终状态。
- 不要把表格输出当成唯一证据；保留关键原始字段，例如资源 ID、状态、IP、CIDR、规格、端口和时间。
- 明确需求、方案确认、任务结果展示或排障时，可用 Mermaid `flowchart` 输出资源拓扑图，帮助用户确认资源关系和连通路径。
- 拓扑图必须区分计划态和已验证态：计划态节点标注“计划/待创建/待复用/待确认”，结果态节点只放 `hcloud` 查询或协议探测确认过的资源事实。
- 图里优先放关键字段：资源类型、名称、ID 短前缀、IP、状态、端口、CIDR、安全组来源、绑定关系和阻塞点。
- 不要凭空画不存在或未查询到的资源；如果是推测关系，必须在节点或连线上标注“推测/待验证”。

## 5.1 结果叙事必须真实

- 汇报验证过程时，只描述真实发生过的命令、脚本、请求、探测、输出和错误；不要为了让过程显得完整，编造“先失败再修复”“重试后成功”“已验证通过”等叙事。
- 计划、dry-run、命令形态检查、请求 spec、Terraform plan、probe template 都是计划态；只有实际执行并拿到结果后，才能写成已执行或已验证。
- 如果某一步第一次就成功，只说成功和对应证据；不要虚构中间故障、恢复动作或人工确认。
- 如果没有运行 live probe、没有执行 `hcloud --execute`、没有读取 saved safe_exec result、没有跑 Terraform state 操作，就必须把状态写成“未执行/待采证/需要用户确认”，不能写成“已完成”。
- 最终总结要把 `planned`、`prepared`、`executed`、`verified`、`blocked` 分开。缺证据时，说明缺什么输入或权限，而不是用推测补齐。

## 5.2 凭据输入必须本地化

- 如果用户在对话里直接粘贴 AK/SK、security token、MaaS API Key、数据库密码、SSH 私钥或临时访问令牌，停止处理该密钥值；不要复述、不要保存到文件、不要写入命令历史、不要放进日志。
- 引导用户把凭据放到本地环境变量、受限权限文件、系统密钥库、现有 hcloud profile 或项目已有的受控凭证路径中。
- 输出只描述凭据来源和 presence，例如“检测到 `HUAWEI_ACCESS_KEY` 已设置”，不要输出原值、前后缀、签名头或派生 token。
- 读取 saved safe_exec result 或 live API 结果时，也要先脱敏再摘要；只有用户明确要求并确认范围时，才展示已脱敏的行级记录。

## 6. 可达服务必须闭环验证

- Web、Docker Remote API、数据库、负载均衡后端等任务不能只停在资源 `ACTIVE`；还要验证进程、端口和应用协议。
- 如果要依赖 `cloud-init` 安装软件，创建前把脚本做成幂等流程：先创建父目录，再写配置；先配置软件源，再安装；最后 `enable`、`restart` 服务。
- 对外可达服务至少检查三层：安全组规则、EIP/监听器/后端绑定、协议探测结果，例如 HTTP 200、Docker `/version` JSON、数据库连接成功。
- ELB 后端必须确认成员 `operating_status=ONLINE`；若 `CONNECT_FAILED`，优先排查后端安全组、服务进程是否监听、健康检查端口/路径、后端子网 ID 是否匹配。
- ELB、NAT、VPC 路由等网络编排任务必须先确定 canonical VPC/subnet。后端 ECS 分属不同 VPC、member subnet 与 ECS 网卡不匹配、或 ELB 与后端网络不可达时，不要反复重建 listener/member。
- 如果没有远程命令能力，可用 EIP + 协议探测验证；如果协议探测不通，不要宣布应用部署成功。

## 6.1 自动 probe 目标必须受限

- `hcloud_acceptance_closure.py run/chain --execute` 和 `hcloud_acceptance_probe_run.py --execute` 只能执行由已审阅 acceptance evidence plan 派生的 HTTP/TCP/DNS/TLS 模板，不能把它们当任意 URL/端口扫描器。
- 云元数据和 link-local 目标必须 hard-block，例如 `169.254.169.254`、`169.254.0.0/16`、IPv6 link-local；不要因为用户把它们填进 `<probe_url>`、`<target_host>` 或 DNS 记录就发包。
- `localhost`、loopback、RFC1918 内网、reserved 地址和 `.local` 名称默认不自动 probe；只有用户明确确认目标来自租户自己的验收路径时，才允许使用 `--allow-private-targets`。
- HTTP/HTTPS probe 不跟随重定向；遇到 3xx 只记录返回码，避免从公网入口被重定向到本机、内网或元数据地址。
- 最终结果要区分“probe 被安全策略阻断”和“业务不可达”。被目标策略挡住时，状态应为 `blocked`，而不是把它写成应用健康检查失败。

## 7. 安全组入口端口必须收敛

- 安全组入方向规则中，SSH 端口 `22` 和常见 Web 入口端口 `80`、`443`、`3000`、`5000`、`8000`、`8080` 不允许使用 `0.0.0.0/0` 作为来源。
- 即使用户目标是公网访问，也不要自动生成或提交上述端口到全网来源的规则；应让用户提供固定客户端 IP、办公网 CIDR、VPN CIDR、跳板机/堡垒机来源、负载均衡来源或私网 CIDR。
- 创建或修改安全组规则前，必须明确 `direction`、`protocol`、端口范围和来源 CIDR；若来源是 `0.0.0.0/0` 且端口命中上述清单，应停止提交并输出安全策略违规原因。
- ECS 创建参数若只引用已有安全组 ID，提交前要查询 `ListSecurityGroupRules` 或 `ShowSecurityGroup` 复核入方向规则；不要假设已有安全组是安全的。

## 8. ECS 初始化和远程排障

- 复杂 ECS 创建优先使用 `--cli-jsonInput` 或临时 JSON 文件，避免超长单行命令、base64、嵌套数组参数被 shell 转义破坏。
- 创建 Linux ECS 前必须先选定 SSH 登录凭证模式：`key_name` 加本地可用私钥，或 `adminPass` 加已保存的密码 artifact；两者不要同时设置，两者都不可用时不要提交创建。
- 若创建 keypair 用于后续 SSH，必须把返回的 private key 保存到受限权限文件并记录 keypair 名称；否则不要把 SSH 当成可用降级路径。
- 若使用 `adminPass`，密码必须在创建前生成并保存到受限权限 artifact；不要依赖日志或 `ShowServerPassword` 事后找回 Linux root 密码。
- ECS 创建完成不能只停在 `ACTIVE`；需要继续用选定凭证执行 SSH 验收，至少跑通 `echo SSH_OK && id && hostname`，否则不要宣称服务器可登录。
- 如果 ECS 创建后还需要安装软件、启动服务、挂载磁盘或做应用验收，创建时必须预埋可纳管通道：可用 keypair private key、cloud-init 完成目标脚本、或明确可用的密码登录配置。
- 创建公网可访问 ECS 时，如果目标安全组不存在或缺少 22/80/443 入方向，先按 VPC/企业项目查询现有安全组和规则；若 `CreateSecurityGroupRule` / `vpc:securityGroupRules:create` 被 SCP 或 IAM 显式拒绝，不要反复补规则。
- `cloud-init` 脚本中写 `/etc/docker/daemon.json`、systemd drop-in、Nginx 站点配置等文件前，先 `mkdir -p` 父目录。
- 对 Ubuntu 安装 Docker，优先选择当前区域可达的官方/云镜像源；安装失败时可降级为发行版仓库中的 `docker.io`，并说明降级影响。
- 远程暴露 Docker TCP 2375 属于高风险配置；只有用户明确要求时才开放，并在最终输出中提示这是未加密管理端口。

## 9. 幂等修复与保守收敛

- 创建前按资源名做幂等查询；发现同名资源时先读 `references/playbooks/resource-idempotency-reconcile.md`，选择 canonical resource 修复，不要继续创建同名资源。
- ECS 内服务、Docker Remote API、ELB HTTP 后端这类可达性任务，应优先读取对应 readiness playbook，使用可重复执行的初始化和验收流程。
- 收敛规则必须保守：只在明确硬阻塞、同一失败已基于新证据修复至少两轮仍无进展、或后续只剩外部等待且继续执行不会改变状态时，才停止并输出部分完成结果。
- 只要还有明确、低风险、与用户目标直接相关的下一步，不要提前交卷；也不要把未通过协议探测或健康检查的组件写成已完成。

## 10. 机内执行和 SSH fallback

- 涉及 ECS 内部状态的任务，例如格式化/挂载数据盘、写 `/etc/fstab`、安装软件、启动后端服务、执行 `docker info`，必须先区分“云侧资源已挂载/已配置”和“机内系统已生效”。
- 首选通道：创建 ECS 时的 cloud-init/user_data、已经可用的远程命令/COC、用户已提供或本地已验证可用的 SSH 凭据。
- 新建、演示、测试、部署类资源默认可重建/重装，除非用户明确说要保留系统盘状态。对于这类资源，不能因为缺 COC 就把任务停在云侧配置。
- 对新建 ECS，优先用任务专用 keypair 保存 private key 并在创建后立即 SSH 验证。
- 对已有 ECS，先找本地已保存 private key；若 ECS 有 keypair name，再尝试可用的私钥导出路径；只有拿到私钥并验证成功才把 key 登录视为可用。
- key 不可用时，用 `ShowResetPasswordFlag` 确认目标 ECS 支持在线重置密码，并只把一次性密码保存在受限临时 artifact 或当前会话中。
- 只为受限来源 CIDR 创建临时 TCP 22 入站规则；不要为了省事开放全网。
- 登录成功后执行幂等机内脚本，完成格式化挂载、服务启动、日志采集和验收。验收通过后删除临时 SSH 入站规则。
- SSH/recreate fallback 不应用于删除、读取用户隐私数据、扩大业务端口暴露面，或用户明确要求只读的场景。
- 如果 COC 不可用、无可用 key/托管私钥、密码登录被系统策略拒绝、且不能在当前任务边界内重建/重装，再停止无效重试并说明最小缺口。
- ELB member `OFFLINE` 且后端端口 `connection refused` 时，结论应是“负载均衡云侧配置已完成，后端服务未启动”；只有实际启动服务并看到 member `ONLINE` 与入口 HTTP 200 后，才能说任务完成。
- EVS volume `in-use` 只表示云侧已挂载；只有 `df -h <mountpoint>` 和写入测试成功，才能说目录可用。
