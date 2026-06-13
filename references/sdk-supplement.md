# SDK Supplement

`huaweicloud-skill` 仍然是 hcloud-first skill。SDK 支持只用于让 hcloud 主链路更好用，不以覆盖所有 SDK API 为目标。

## 定位

- **主执行面**：`hcloud` / KooCLI。
- **SDK 补充面**：已安装的 `huaweicloudsdk*` Python package。
- **SDK 源码参考**：`reference-projects/huaweicloud-sdk-python-v3` 只用于本仓库维护、测试和离线比对；用户机器不要求存在该目录。
- **未来 IaC 面**：Terraform 应作为单独的 plan/validate/apply/verify 链路接入，不由 SDK runner 替代。

## 参考快照

当前维护参考来自 `reference-projects/huaweicloud-sdk-python-v3`：

- 本地 `VERSION`：`3.1.199`
- 本地 changelog 日期：`2026-06-11`
- 运行时要求：用户机器不需要 SDK 源码，只需要按需安装 pip package
- Python 要求：SDK 文档声明 Python 3.6+

注意：这只是本仓库维护期快照。真实用户环境应以已安装 package 版本和当前 PyPI/SDK 中心为准；agent 不应假设用户机器存在 reference 源码。

## 运行时认证与 region 线索

SDK 补充层只读取或调用已安装的 `huaweicloudsdk*` package。典型安装方式：

```bash
pip install huaweicloudsdkecs
pip install huaweicloudsdkvpc
```

`huaweicloudsdkall` 会安装集合包，但不建议 agent 默认要求用户安装全量集合；只有当任务确实跨多个服务且用户接受依赖体积时才提示。

SDK 常见环境变量：

| 变量 | 用途 |
| --- | --- |
| `HUAWEICLOUD_SDK_AK` | SDK Access Key |
| `HUAWEICLOUD_SDK_SK` | SDK Secret Key |
| `HUAWEICLOUD_SDK_SECURITY_TOKEN` | 临时凭证 token |
| `HUAWEICLOUD_SDK_PROJECT_ID` | 区域级服务 project ID |
| `HUAWEICLOUD_SDK_DOMAIN_ID` | 全局级服务 domain ID |

认证选择：

- 区域级服务优先使用 `BasicCredentials`，通常需要 project ID；新版 SDK 在使用永久 AK/SK 且 `with_region()` 时可自动查询 project ID。
- 全局级服务使用 `GlobalCredentials`，通常需要 domain ID。
- SDK 支持环境变量、profile、metadata、Pod Identity 等凭证来源；CCE Pod Identity 能减少明文 AK/SK 暴露，但只能在对应集群/身份配置完成后使用。

Region/endpoint 选择：

- 优先用 SDK 内置 region，例如 `{Service}Region.value_of("cn-north-4")`。
- 显式 endpoint 可用于专属云、特殊网络或内置 region 不完整的场景，但通常需要显式 project/domain ID。
- SDK 的 region 查找顺序包括环境变量、配置文件和内置 region；找不到时可能抛出 `KeyError`。
- 自定义 endpoint 可通过形如 `HUAWEICLOUD_SDK_REGION_{SERVICE_NAME}_{REGION_ID}` 的环境变量补充；多 endpoint 需要确认 SDK 版本支持。

异常处理：

- `ClientRequestException` 通常包含 `status_code`、`request_id`、`error_code`、`error_msg`。
- agent 只应把这些字段作为 hcloud 错误归因补充，不应因为 SDK 能返回更详细错误就绕过 hcloud 主链路。

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

## 候选池规则

从 SDK reference 继续吸收新能力时，优先考虑下面这类只读补充：

- CBR vault/policy 等备份姿态查询。
- RFS stack、execution plan 等 IaC 状态元数据。
- DCS instance、session、background task 等缓存可见性查询。
- HSS、SecMaster、CFW 等安全姿态 list/show 查询，但默认 `execute_allowed=false`，先用于参数和证据规划。

不要把这些能力自动变成 SDK 执行入口。只有当 hcloud 主链路有明确痛点、SDK package 可维护、operation 只读且经过 smoke/test 后，才允许进入 `sdk-supplement-registry.json`；数据库操作、密码重置、升级、kill session、删除、启停、扩缩容等 action/mutation 不进入 SDK runner。
