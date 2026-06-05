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
