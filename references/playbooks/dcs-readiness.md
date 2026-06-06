# DCS Readiness Candidate Playbook

## 目标

为 DCS 从 metadata-backed 晋级 curated 前建立只读检查和风险边界。

## 当前状态

- 已 live-smoked：`ListAvailableZones`
- 晋级前还需要至少 1 条额外 read-only `command_shape_ok` evidence。

## 候选检查

```bash
python3 scripts/hcloud_resource_discovery.py --service DCS --operation ListAvailableZones --region=<region> --pretty
python3 scripts/hcloud_resource_discovery.py --service DCS --operation ListInstances --region=<region> --limit=20 --pretty
```

有实例 ID 后：

```bash
python3 scripts/hcloud_resource_query.py --service DCS --operation ListConfigurations --region=<region> --param instance_id=<instance-id> --pretty
```

## 风险边界

DCS 创建、删除、主备切换、参数修改和账号修改默认 planner-only。晋级 curated 前不得自动 submit；晋级后也需要显式确认、备份/维护窗口检查和实例状态回读。
