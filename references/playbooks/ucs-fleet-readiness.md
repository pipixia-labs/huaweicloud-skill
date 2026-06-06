# UCS Fleet Readiness Candidate Playbook

## 目标

为 UCS 从 metadata-backed 晋级 curated 前建立 fleet、cluster、policy 和 addon 的只读检查边界。

## 当前状态

- 已 live-smoked：`ListAddonTemplates`
- 已知 CLI shape 例外：`ListManagedClusters` 在 KooCLI 7.2.2 中拒绝 `--limit`，skill 会省略该可选参数。
- 晋级前还需要至少 1 条额外 read-only `command_shape_ok` evidence。

## 候选检查

```bash
python3 scripts/hcloud_resource_discovery.py --service UCS --operation ListAddonTemplates --region=<region> --pretty
python3 scripts/hcloud_resource_discovery.py --service UCS --operation ListClusterGroup --region=<region> --pretty
python3 scripts/hcloud_resource_discovery.py --service UCS --operation ListManagedClusters --region=<region> --pretty
```

有 cluster 或 fleet ID 后：

```bash
python3 scripts/hcloud_resource_query.py --service UCS --operation ShowCluster --region=<region> --param clusterid=<cluster-id> --pretty
python3 scripts/hcloud_resource_query.py --service UCS --operation ShowClusterGroup --region=<region> --param clustergroupid=<fleet-id> --pretty
```

## 风险边界

UCS federation、policy、addon、kubeconfig 和 cluster 接入操作默认高风险 planner-only。不得保存 kubeconfig token 或把集群凭据写入最终输出。
