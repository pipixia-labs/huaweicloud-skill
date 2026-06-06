# RFS Stack Readiness Candidate Playbook

## 目标

为 RFS 从 metadata-backed 晋级 curated 前建立 stack、template、execution plan 的只读检查边界。

## 当前状态

- 已 live-smoked：`ListPrivateHooks`
- 晋级前还需要至少 1 条额外 read-only `command_shape_ok` evidence。

## 候选检查

```bash
python3 scripts/hcloud_resource_discovery.py --service RFS --operation ListPrivateHooks --region=<region> --limit=10 --pretty
python3 scripts/hcloud_resource_discovery.py --service RFS --operation ListStacks --region=<region> --limit=10 --pretty
```

有 stack name 后：

```bash
python3 scripts/hcloud_resource_query.py --service RFS --operation GetStackMetadata --region=<region> --param stack_name=<stack-name> --pretty
python3 scripts/hcloud_resource_query.py --service RFS --operation ListStackResources --region=<region> --param stack_name=<stack-name> --pretty
```

## 风险边界

RFS apply、continue、rollback、create execution plan 和 stack set 变更默认高风险 planner-only。晋级前不允许 submit；晋级后也必须审查 template diff、execution plan 和回滚路径。
