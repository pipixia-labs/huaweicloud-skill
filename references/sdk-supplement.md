# SDK Supplement

`huaweicloud-skill` 仍然是 hcloud-first skill。SDK 支持只用于让 hcloud 主链路更好用，不以覆盖所有 SDK API 为目标。

## 定位

- **主执行面**：`hcloud` / KooCLI。
- **SDK 补充面**：已安装的 `huaweicloudsdk*` Python package。
- **SDK 源码参考**：`reference-projects/huaweicloud-sdk-python-v3` 只用于本仓库维护、测试和离线比对；用户机器不要求存在该目录。
- **未来 IaC 面**：Terraform 应作为单独的 plan/validate/apply/verify 链路接入，不由 SDK runner 替代。

## 什么时候用 SDK

优先使用 SDK 的场景：

1. hcloud metadata/help 缺少参数类型、query/path/body 位置或 region/endpoint 线索。
2. 需要把 SDK 的 `openapi_types`、`attribute_map`、`sensitive_list` 作为 hcloud 命令规划证据。
3. 需要识别 SDK 的异常结构、request id、error code，以改进 `hcloud_safe_exec.py` 的错误归因。
4. 少量稳定、可维护、明确 allowlist 的只读查询，且 SDK 比 hcloud 更适合程序化处理。

不要使用 SDK 的场景：

1. 为了“支持 SDK”而支持 SDK。
2. 通用创建、修改、删除、启停、扩缩容等变更操作。
3. 需要跨大量服务自动生成 SDK 写操作 runner。
4. hcloud 已能稳定完成，且 SDK 不能提供额外可靠性或可维护性收益。

## 运行时规则

- 默认探测已安装 package，例如 `huaweicloudsdkecs`。
- 如果用户机器没有安装对应 SDK package，SDK 补充能力应降级，不影响 hcloud 主流程。
- `scripts/hcloud_sdk_catalog.py` 可以从已安装 package 或维护期源码 fallback 读取 SDK metadata。
- `references/sdk-supplement-registry.json` 是 SDK 补充控制面。每个条目必须说明 hcloud fallback、SDK 价值、风险、证据和是否允许 execute。
- `scripts/hcloud_sdk_supplement_audit.py` 校验 registry 结构、边界、fallback 和 SDK metadata。
- `scripts/hcloud_sdk_readonly.py` 默认只生成计划；只有显式 `--execute` 才会调用 SDK。
- `scripts/hcloud_sdk_readonly.py` 只执行 registry allowlist 内 read-only operation。非 allowlist 操作应回到 hcloud 查询计划或先补 curated coverage。

## 推荐使用顺序

1. 先用 `hcloud_context_inspect.py` 确认 hcloud 上下文。
2. 查询或变更仍先走 registry、hcloud catalog、playbook 和 safe exec。
3. 如果需要 SDK 证据，再调用：

```bash
python3 scripts/hcloud_sdk_catalog.py --service ECS --operation ListFlavors --pretty
```

4. 如果明确需要 SDK 只读 runner，并且 operation 已 allowlist：

```bash
python3 scripts/hcloud_sdk_readonly.py \
  --service ECS \
  --operation ListFlavors \
  --region cn-north-4 \
  --pretty
```

5. 真实 SDK 执行前确认用户已经安装对应 package，并配置 SDK 凭证来源，例如环境变量或 SDK credentials file。

## 准入流程

新增 SDK supplement 时按顺序执行：

1. 在 `references/sdk-supplement-registry.json` 增加条目，说明为什么 SDK 能改善 hcloud 工作流。
2. 确认 `fallback.runner` 指向 hcloud 主路径，例如 `scripts/hcloud_resource_query.py`。
3. 默认 `execute_allowed=false`；只有低风险、只读、稳定、已有测试和人工 smoke 计划的操作才允许打开。
4. 运行：

```bash
python3 scripts/hcloud_sdk_supplement_audit.py --pretty
```

5. 若维护者机器有 SDK package 或源码 fallback，可加：

```bash
python3 scripts/hcloud_sdk_supplement_audit.py --require-metadata --pretty
```

6. 为 runner 行为补单测。真实 `--execute` 前补人工 smoke 记录。
