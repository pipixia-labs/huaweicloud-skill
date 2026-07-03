# CCI Workload Readiness Playbook

## 目标

帮助用户用云容器实例 CCI 部署或排查容器应用前，先确认 namespace、Network、镜像、Deployment/Pod、Service、公网入口、日志和监控证据。CCI 类 Kubernetes API 看起来像普通 K8s，但它没有用户自管节点，网络和规格限制必须前置确认。

## 适用场景

- 用户说要“无服务器容器”“云容器实例”“不用买服务器跑容器”。
- 用户要把 SWR 镜像部署到 CCI。
- 用户要查询 CCI Pod/Deployment/Service 状态。
- 用户遇到 CCI 镜像拉取失败、Service 暴露失败、Pod 不 Ready、日志查不到。

## 标准只读检查

1. 查询 CCI namespace：

```bash
python3 scripts/hcloud_resource_discovery.py \
  --service CCI \
  --operation listNamespaces \
  --region=<region> \
  --pretty
```

2. 查询 namespace 下的 Network：

```bash
python3 scripts/hcloud_resource_query.py \
  --service CCI \
  --operation listNamespacedNetworks \
  --region=<region> \
  --param namespace=<namespace> \
  --pretty
```

3. 查询 Deployment、Pod、Service：

```bash
python3 scripts/hcloud_resource_query.py \
  --service CCI \
  --operation listNamespacedDeployments \
  --region=<region> \
  --param namespace=<namespace> \
  --pretty
```

```bash
python3 scripts/hcloud_resource_query.py \
  --service CCI \
  --operation listNamespacedPods \
  --region=<region> \
  --param namespace=<namespace> \
  --pretty
```

```bash
python3 scripts/hcloud_resource_query.py \
  --service CCI \
  --operation listNamespacedServices \
  --region=<region> \
  --param namespace=<namespace> \
  --pretty
```

4. 如需确认镜像，先进入 `swr-image-readiness.md`。

## 创建或更新前检查

CCI 的 namespace、Network、Deployment、Service、Secret、Ingress、EIPPool 创建/更新都是写操作。生成计划前必须确认：

- region / project / enterprise project。
- namespace 名称和资源类型。
- Network 绑定的 VPC、subnet、安全组。
- 镜像地址、tag/digest、拉取凭证。
- CPU、内存、GPU、临时存储、环境变量、Secret/ConfigMap。
- 副本数、健康检查、端口、Service 类型。
- 是否需要 EIP、ELB、DNS、HTTPS、访问源限制。
- 日志是否进入 LTS，指标是否进入 CES。
- 费用和释放策略。

## 风险边界

- 不自动创建 Deployment、Service、Secret、Network 或 EIPPool。
- 不在最终输出里展示镜像拉取密码、token、Secret value。
- 不把 Pod Running 当成业务可用；必须补协议探测或 Service/Ingress 访问证据。
- 不建议直接创建裸 Pod 承载长期服务；优先 Deployment/Job/StatefulSet，按用户目标选择。
- 变更前先用 planner 或 Terraform route，真实执行必须二次确认。

## 常见问题

| 现象 | 常见原因 | 下一步 |
| --- | --- | --- |
| Pod Pending | namespace 网络未就绪、规格不可用、配额不足 | 查 namespace/network/events，再确认资源规格。 |
| ImagePullBackOff | SWR tag 不存在、私有仓库无权限、镜像架构不匹配 | 进入 `swr-image-readiness.md`。 |
| Service 没公网入口 | Service 类型、EIP/ELB、Network 或安全组未配置 | 进入 `eip-public-ip-readiness.md` 和 `vpc-network-readiness.md`。 |
| 无日志 | 应用未输出 stdout/stderr，或 LTS 未配置 | 进入 `lts-log-readiness.md`。 |
| 健康检查失败 | 端口、路径、启动时间或协议不匹配 | 先读 Pod/Service 状态，再生成 probe 计划。 |

## 验收

CCI 应用可用至少需要：

- namespace 和 Network 已存在且绑定到正确 VPC/subnet。
- Deployment/Pod 状态、重启次数、事件清楚。
- 镜像 tag/digest 可追溯。
- Service/Ingress/EIP/ELB/DNS 路径清楚。
- 日志、指标、访问探测至少有一种可验证证据。
- 如果是生产服务，还要有回滚镜像、资源上限、成本和清理策略。
