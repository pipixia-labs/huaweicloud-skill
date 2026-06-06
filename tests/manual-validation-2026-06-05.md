# huaweicloud-skill Manual Validation 2026-06-05

本文件记录 metadata-backed catalog read-only smoke 的第一批实测结果。所有命令均为只读查询，没有创建、修改、绑定、解绑、扩容、停用或删除云资源。

## 环境前提

- KooCLI version: 7.2.2
- profile: `default`
- region: `cn-north-4`
- 本轮不显式传 `project_id`，由当前 profile 和 hcloud 自身上下文处理。

## 验证 1：metadata-backed plan matrix

```bash
python3 scripts/hcloud_catalog_readonly_smoke.py \
  --service UCS \
  --service RFS \
  --service WAF \
  --service DCS \
  --region=cn-north-4 \
  --project-id=<project-id> \
  --catalog-max-operations=1 \
  --output tests/fixtures/hcloud-catalog-readonly-smoke-plan.json \
  --pretty
```

结果：

- 4 个服务均能生成 metadata-backed read-only discovery command。
- 持久化 fixture 中的 `project_id` 已占位化为 `<project-id>`。
- fixture 不包含 raw stdout、stderr 或 parsed response body。

## 验证 2：metadata-backed live read-only smoke

```bash
python3 scripts/hcloud_catalog_readonly_smoke.py \
  --service UCS \
  --service RFS \
  --service WAF \
  --service DCS \
  --region=cn-north-4 \
  --catalog-max-operations=1 \
  --execute \
  --timeout=60 \
  --output tests/fixtures/hcloud-catalog-readonly-smoke-execute.json \
  --confidence-output /tmp/hcloud-catalog-confidence-suggestions.json \
  --pretty
```

结果分桶：

| Service | Operation | Bucket | 结论 |
| --- | --- | --- | --- |
| UCS | `ListAddonTemplates` | `command_shape_ok` | 命令形态通过，返回 JSON 顶层键为 `apiVersion/items/kind`。 |
| WAF | `ListAntileakagePolicyRules` | `command_shape_ok` | 命令形态通过，返回 JSON 顶层键为 `items/total`。 |
| DCS | `ListAvailableZones` | `command_shape_ok` | 命令形态通过，返回 JSON 顶层键为 `available_zones/region_id`。 |
| RFS | `ListPrivateHooks` | `command_shape_error` | 初始生成命令暴露两个 catalog 适配问题：`limit=5` 低于元数据下限，且缺少 `Client-Request-Id` required header。 |

说明：

- 普通沙箱网络下 UCS 曾被分为 `network`；网络权限下重跑后变为 `command_shape_ok`，说明此前是执行环境网络问题，不是 command shape 问题。
- 成功的 3 个 operation 先登记到 `references/hcloud-service-confidence.json`，均为 operation 级 `live-read-smoked`；对应 service 仍保持 `catalog-derived`，不等于 curated coverage。
- `tests/fixtures/hcloud-catalog-readonly-smoke-execute.json` 只保存矩阵、bucket、命令和响应形态，不保存完整云端响应。

## 验证 3：RFS 参数/header 修复后单服务复测

```bash
python3 scripts/hcloud_catalog_readonly_smoke.py \
  --service RFS \
  --region=cn-north-4 \
  --catalog-max-operations=1 \
  --execute \
  --timeout=60 \
  --output tests/fixtures/hcloud-catalog-readonly-smoke-rfs-fixed.json \
  --confidence-output /tmp/hcloud-catalog-confidence-rfs-fixed.json \
  --pretty
```

结果：

- `RFS ListPrivateHooks` 返回 `command_shape_ok`。
- 生成命令把默认 `limit=5` 按 catalog 元数据下限调整为 `limit=10`。
- 生成命令自动补齐安全的 required header：`Client-Request-Id=00000000-0000-0000-0000-000000000000`。
- 响应只记录 JSON 形态：顶层键为 `hooks/page_info`，fixture 不保存完整响应体。
- `RFS ListPrivateHooks` 已补充到 `references/hcloud-service-confidence.json` 的 operation 级 `live-read-smoked` 条目。

## 验证 4：metadata-backed live read-only smoke 扩容

```bash
python3 scripts/hcloud_catalog_readonly_smoke.py \
  --service AOS \
  --service CBR \
  --service CodeArtsRepo \
  --service DLI \
  --service ModelArts \
  --service CFW \
  --region=cn-north-4 \
  --catalog-max-operations=1 \
  --execute \
  --timeout=60 \
  --output tests/fixtures/hcloud-catalog-readonly-smoke-expanded.json \
  --confidence-output /tmp/hcloud-catalog-confidence-expanded.json \
  --pretty
```

结果分桶：

| Service | Operation | Bucket | 结论 |
| --- | --- | --- | --- |
| CodeArtsRepo | `ListCurrentUserRepositories` | `command_shape_ok` | 命令形态通过，响应只记录 list 形态和 item count。 |
| DLI | `ListAuthInfo` | `command_shape_ok` | 命令形态通过，返回 JSON 顶层键为 `auth_infos/count`。 |
| AOS | `ListPrivateHooks` | `network` | 已生成带 `limit=10` 和 `Client-Request-Id` 的只读命令，但本次网络传输失败，不升级 confidence。 |
| ModelArts | `ListAlgorithms` | `network` | 本次网络传输失败，不升级 confidence。 |
| CBR | `ListAgent` | `region_or_endpoint` | hcloud 返回 project/region/endpoint 类错误，不升级 confidence。 |
| CFW | `ListDnsServers` | `unknown_cloud_error` | hcloud 返回 not_found 类云侧错误；已到达云侧但本轮无法证明命令形态成功，不升级 confidence。 |

说明：

- 成功的 `CodeArtsRepo ListCurrentUserRepositories` 和 `DLI ListAuthInfo` 已补充到 `references/hcloud-service-confidence.json`。
- 失败项保留在 fixture 中作为分桶证据，但不等同于 skill bug，也不升级为 `live-read-smoked`。
- `tests/fixtures/hcloud-catalog-readonly-smoke-expanded.json` 不保存 raw stdout、stderr 或完整 parsed response body。

## 验证 5：A1 follow-up 和 UCS 参数形态例外

2026-06-06 尝试对 `DCS`、`RFS`、`UCS`、`WAF` 执行后续只读 live smoke，每个服务取 3 个 discovery operation：

```bash
python3 scripts/hcloud_catalog_readonly_smoke.py \
  --service DCS \
  --service RFS \
  --service UCS \
  --service WAF \
  --region=cn-north-4 \
  --catalog-max-operations=3 \
  --execute \
  --timeout=60 \
  --output /tmp/hcloud-catalog-smoke-a1-followup-core.json \
  --confidence-output /tmp/hcloud-catalog-confidence-a1-followup-core.json \
  --pretty
```

结果：

- 普通沙箱网络下无法证明新的 `command_shape_ok`，网络提权审批两次超时，因此本轮不新增 live-smoked confidence。
- `DCS`、`RFS`、`WAF` 返回权限类分桶，不能作为晋级 curated 的证据。
- `UCS ListManagedClusters --limit=5` 被 KooCLI 7.2.2 拒绝为不正确参数；`hcloud UCS ListManagedClusters --help` 只列出 `--unimported`，未列出 `--limit`。

处理：

- `references/hcloud-service-confidence.json` 对 `UCS ListManagedClusters` 增加 `unsupported_optional_args=["limit"]`，但不提升 confidence。
- `hcloud_resource_discovery.py` 现在会在该 operation 上省略 `--limit`，避免 catalog metadata 与 KooCLI 实际 CLI flag 不一致导致命令形态失败。
- 验证 5 执行时，A6 curated promotion audit 显示 DCS/RFS/UCS/WAF/CodeArtsRepo/DLI 尚未达到 medium coverage 验收线，暂不写入 curated registry；验证 6 已补齐第二条 evidence。

## 验证 6：A6 候选服务第二条只读 live smoke

2026-06-06 对 6 个 curated promotion 候选服务各补 1 条明确 operation 的只读 live smoke：

```bash
python3 scripts/hcloud_catalog_readonly_smoke.py \
  --service DCS --operation ListMaintenanceWindows \
  --service RFS --operation ListPrivateModules \
  --service UCS --operation ListPolicyDefinitions \
  --service WAF --operation ListInstance \
  --service CodeArtsRepo --operation ListGroups \
  --service DLI --operation ListCatalogs \
  --region=cn-north-4 \
  --execute \
  --timeout=90 \
  --output tests/fixtures/hcloud-catalog-readonly-smoke-second-live.json \
  --confidence-output <temporary-confidence-json> \
  --pretty
```

结果分桶：

| Service | Operation | Bucket | 响应形态 |
| --- | --- | --- | --- |
| DCS | `ListMaintenanceWindows` | `command_shape_ok` | dict 顶层键 `maintain_windows` |
| RFS | `ListPrivateModules` | `command_shape_ok` | dict 顶层键 `modules/page_info`；`limit` 按元数据下限调整为 `10`，自动补 `Client-Request-Id` |
| UCS | `ListPolicyDefinitions` | `command_shape_ok` | dict 顶层键 `items` |
| WAF | `ListInstance` | `command_shape_ok` | dict 顶层键 `items/purchased/total` |
| CodeArtsRepo | `ListGroups` | `command_shape_ok` | list，当前 item count 为 `0` |
| DLI | `ListCatalogs` | `command_shape_ok` | dict 顶层键 `catalogs/is_success/total_count` |

说明：

- 普通沙箱下首次执行混有 `auth_or_permission` 和 `network` 分桶；网络权限下只读重跑后 6 个 operation 全部为 `command_shape_ok`。
- 本轮只升级成功的 operation confidence；不把网络、权限或 region 类失败写成 `live-read-smoked`。
- `tests/fixtures/hcloud-catalog-readonly-smoke-second-live.json` 只保存脱敏命令、bucket、响应形态和 evidence summary，不保存 raw stdout、stderr 或完整 parsed response body。
- `references/hcloud-service-confidence.json` 已补充这 6 条 operation 级 `live-read-smoked` 证据。
- A6 promotion audit 在 evidence 层面已经达到默认 `min_live_ops=2`；是否真正写入 curated registry 仍是服务名单和维护面决策。
