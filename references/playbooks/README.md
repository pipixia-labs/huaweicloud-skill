# Huawei CLI Playbooks

这里收纳的是面向具体任务的执行手册。优先按用户当前目标选一个最贴近的 playbook，再回到 `references/workflow.md` 补通用规则。

## 索引

- `ecs-create-readiness.md`
  - 创建 ECS 前的依赖确认、规格和售卖策略检查。
- `ecs-ssh-access-readiness.md`
  - 创建 Linux ECS 前后的 SSH 登录凭证闭环和登录验收。
- `ecs-inventory.md`
  - 查询当前 scope 下的 ECS 实例并整理成可读摘要。
- `ecs-user-data-service-readiness.md`
  - 用 cloud-init/user_data 安装并启动 ECS 内服务，生成可验收 readiness。
- `elb-http-backend-readiness.md`
  - 创建和排查 HTTP ELB 后端，处理 member `CONNECT_FAILED` / `OFFLINE`。
- `eip-public-ip-readiness.md`
  - 创建、绑定、解绑或查询 EIP 后验证公网 IP 状态和绑定关系。
- `evs-volume-readiness.md`
  - 创建、挂载或扩容 EVS 云硬盘后区分云侧状态和 ECS 内文件系统状态。
- `rds-instance-readiness.md`
  - 创建或修改 RDS 后验证实例状态、规格、备份和连接探测。
- `nat-gateway-readiness.md`
  - 查询或调整 NAT 网关、DNAT/SNAT 规则前确认网关、规则和连通性边界。
- `cce-cluster-readiness.md`
  - 查询 CCE 集群和节点状态，并区分云侧状态、kubeconfig 和 Kubernetes 层验收。
- `cdn-domain-readiness.md`
  - 查询 CDN 域名、源站、证书和缓存配置，并记录 CDN CLI region 限制。
- `dns-zone-record-readiness.md`
  - 查询 DNS zone/record，修改前确认记录、TTL 和解析影响。
- `scm-certificate-readiness.md`
  - 查询证书、证书详情和部署目标，保护证书材料和私钥边界。
- `ces-metric-readiness.md`
  - 查询云监控指标前确认 namespace、dimension、period 和时间范围。
- `dcs-readiness.md`
  - DCS 晋级 curated 前的只读 smoke、实例配置和风险边界候选手册。
- `rfs-stack-readiness.md`
  - RFS 晋级 curated 前的 stack、template、execution plan 候选手册。
- `ucs-fleet-readiness.md`
  - UCS 晋级 curated 前的 fleet、cluster、policy 和 addon 候选手册。
- `waf-policy-readiness.md`
  - WAF 晋级 curated 前的 host、policy、rule 和 event 候选手册。
- `codeartsrepo-readiness.md`
  - CodeArtsRepo 晋级 curated 前的仓库、分支、成员和合并请求候选手册。
- `dli-readiness.md`
  - DLI 晋级 curated 前的权限、catalog、database、queue 和 SQL 检查候选手册。
- `docker-remote-api-readiness.md`
  - 安装 Docker、开放 Remote API 并用协议探测验证 daemon。
- `obs-boundary.md`
  - 记录 OBS 的 `hcloud obs`/obsutil 专用路线，避免生成不可验证的 `hcloud OBS Operation` 命令。
- `resource-idempotency-reconcile.md`
  - 按资源名做幂等选择和修复，避免重复创建同名资源。
- `iam-context-bootstrap.md`
  - 在执行云侧业务前先确认当前 profile、region、project 和认证上下文。
- `ims-image-discovery.md`
  - 创建 ECS 前的镜像发现路径和当前环境约束。
- `kps-keypair-discovery.md`
  - 创建 ECS 或 SSH 登录前的密钥对发现与风险检查。
- `vpc-network-readiness.md`
  - 面向网络前置条件的 readiness 检查方法。
- `vpc-resource-discovery.md`
  - 面向 VPC、子网、安全组等资源的 discovery 路径。

## 选择建议

- 目标是查现网 ECS：先看 `ecs-inventory.md`
- 目标是创建 ECS：先看 `ecs-create-readiness.md`，需要登录机器时同时看 `ecs-ssh-access-readiness.md`
- 目标是修复或续跑已有命名资源：先看 `resource-idempotency-reconcile.md`
- 目标是 ECS 上部署 Web/Docker 服务：同时看 `ecs-user-data-service-readiness.md`
- 目标是 ELB 后端健康：先看 `elb-http-backend-readiness.md`
- 目标是 EIP 绑定和公网入口：先看 `eip-public-ip-readiness.md`
- 目标是云硬盘挂载或扩容：先看 `evs-volume-readiness.md`
- 目标是 RDS 实例可用性：先看 `rds-instance-readiness.md`
- 目标是 NAT 出入口映射：先看 `nat-gateway-readiness.md`
- 目标是 CCE 集群和节点状态：先看 `cce-cluster-readiness.md`
- 目标是 CDN 域名或源站：先看 `cdn-domain-readiness.md`
- 目标是 DNS 解析：先看 `dns-zone-record-readiness.md`
- 目标是证书：先看 `scm-certificate-readiness.md`
- 目标是监控指标：先看 `ces-metric-readiness.md`
- 卡在上下文或认证：先看 `iam-context-bootstrap.md`
- 卡在镜像、密钥对或网络依赖：按 `ims`、`kps`、`vpc` 对应 playbook 进入
- 目标涉及 OBS：先看 `obs-boundary.md`，只读查询走 `hcloud_obs_readonly.py`，写类操作先走 `hcloud_obs_change_plan.py`
