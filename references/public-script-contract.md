# 公共脚本契约

本 Skill 的公共脚本是 Agent 可直接运行的高频捷径。脚本文件可以各自保持清晰职责，不需要合并成
一个大 dispatcher；调用方通过统一分类、输出和退出语义判断如何使用它们。

机器可读声明位于 `script-audience-manifest.json`。当前采用渐进迁移：先覆盖云访问或可能产生大结果
的公共查询入口，小型本地 planner 保持轻量，后续在真正需要时加入契约。

## 脚本分类

| kind | 作用 | 是否访问云 |
| --- | --- | --- |
| `planner` | 校验输入并生成可审查计划 | 默认不访问 |
| `inspector_router` | 观察本地环境或选择少量资料/入口 | 通常不访问业务 API |
| `query_executor` | 计划或执行只读查询 | 只有显式 execute 时访问 |
| `mutation_helper` | 规划、校验、执行或回读特定变更 | 由脚本参数和授权边界决定 |
| `artifact_media_producer` | 生成文件、图片、视频或其他外部产物 | 由具体后端决定 |

`backend` 说明脚本包装的是 hcloud、SDK、Terraform、MaaS API 还是本地逻辑。脚本本身不是第四种
执行后端，registry 也不是 Agent 可使用 API 的总白名单。

## 默认兼容行为

- 不传 `--output-file`：继续把原有完整 JSON 写到 stdout；已有调用方无需修改。
- 传 `--output-file <path>`：完整 JSON 原样写入该文件，权限为 `0600`；stdout 只返回紧凑回执。
- `--pretty` 同时控制落盘 JSON 和 stdout 回执的可读格式，不改变字段语义。
- 脚本不因为落盘而重新汇总、删字段或改写 provider 响应；调用方按需从结果文件提取字段。

## 紧凑回执

`huaweicloud_skill_public_result_v1` 至少包含：

```json
{
  "result_contract": "huaweicloud_skill_public_result_v1",
  "success": true,
  "mode": "plan",
  "outcome_status": "planned",
  "result_file": "/workspace/result.json",
  "artifact": {
    "path": "/workspace/result.json",
    "bytes": 1234,
    "sha256": "...",
    "permissions": "0600"
  }
}
```

结果存在时还可带 `service` 和 `operation`。`outcome_status` 优先保留脚本自己声明的值，否则按以下
规则归一化：plan 成功为 `planned`，execute/其他成功为 `succeeded`，失败为 `failed`。

## 退出语义

- `success=true` 返回退出码 `0`；
- `success=false` 返回非零；
- 非零退出不表示没有结果文件，调用方仍应检查 stdout 回执或已知 `--output-file`；
- provider/API 的业务错误不能仅凭子进程退出码判断，脚本需要解析其结构化返回；
- `partially_succeeded`、`outcome_unknown` 等更细状态由具体脚本声明，公共 emitter 原样保留。

## 第一批稳定入口

- `hcloud_resource_discovery.py`
- `hcloud_resource_query.py`
- `hcloud_obs_readonly.py`
- `hcloud_sdk_readonly.py`

`hcloud_account_inventory.py` 和 `hcloud_billing_live_read.py` 已有更丰富的领域回执，其完整性、分页和
部分成功语义继续由各自脚本负责，不为了表面统一而降级。
