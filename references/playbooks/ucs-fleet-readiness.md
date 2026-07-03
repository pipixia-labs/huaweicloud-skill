# UCS Fleet Readiness Playbook

## 目标

为 UCS curated registry 覆盖提供 fleet、cluster、policy 和 addon 的只读检查边界。

## 当前状态

- 已 live-smoked：`ListAddonTemplates`、`ListPolicyDefinitions`
- 已知 CLI shape 例外：`ListManagedClusters` 在 KooCLI 7.2.2 中拒绝 `--limit`，skill 会省略该可选参数。
- 当前 registry 覆盖只读 fleet/cluster/policy/addon discovery 和 target-scoped readback，不开放通用 mutation submit。

## Readiness 检查

```bash
python3 scripts/hcloud_resource_discovery.py --service UCS --operation ListAddonTemplates --region=<region> --pretty
python3 scripts/hcloud_resource_discovery.py --service UCS --operation ListClusterGroup --region=<region> --pretty
python3 scripts/hcloud_resource_discovery.py --service UCS --operation ListManagedClusters --region=<region> --pretty
python3 scripts/hcloud_resource_discovery.py --service UCS --operation ListPolicyDefinitions --region=<region> --pretty
```

有 cluster 或 fleet ID 后：

```bash
python3 scripts/hcloud_resource_query.py --service UCS --operation ShowCluster --region=<region> --param clusterid=<cluster-id> --pretty
python3 scripts/hcloud_resource_query.py --service UCS --operation ShowClusterGroup --region=<region> --param clustergroupid=<fleet-id> --pretty
python3 scripts/hcloud_resource_query.py --service UCS --operation ShowPolicyDefinition --region=<region> --param policydefinitionid=<policy-definition-id> --pretty
```

## 治理操作清单

UCS 场景重点不是只查到 fleet，而是确认“多集群治理是否可闭环”：

- Fleet / cluster group：有哪些 fleet、包含哪些集群、集群状态和地域分布。
- Policy definition：可用策略定义、策略版本、参数要求和适用范围。
- Policy instance：策略是否已实例化、绑定目标、当前合规状态、最近更新时间。
- Compliance：哪些集群、namespace 或 resource 不合规，是否有豁免或待处理项。
- Addon：addon template、已装 addon、版本、升级风险和依赖。
- 凭据边界：kubeconfig、cluster access token、接入脚本都属于高敏材料，不输出原值。

如果要从只读治理进入写类操作，必须先生成单独 guarded plan：创建、更新、删除 policy instance，接入或移除集群，安装或升级 addon 都不能由 readiness 流程自动提交。

## 风险边界

UCS federation、policy、addon、kubeconfig 和 cluster 接入变更不在当前 curated registry 的 change operations 中。后续如果要加入写类能力，必须先补专用 guarded flow、凭据脱敏、集群状态回读和显式确认门禁。不得保存 kubeconfig token 或把集群凭据写入最终输出。
