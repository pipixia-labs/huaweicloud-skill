# MaaS Usage Governance Playbook

## 目标

帮助用户理解 MaaS 大模型调用的 token 用量、请求数、错误数和错误率，先生成安全的查询计划，再决定是否进行真实 API 查询。这个手册面向“用云”和“管云”场景，不负责直接发起模型推理。

## 适用场景

- 用户想看 MaaS token 用量、词元用量、请求次数或错误率
- 用户要按最近 7/14/30 天或指定时间段查看 MaaS 使用情况
- 用户要区分预置服务、我的服务、自定义 Endpoint 的用量
- 用户担心大模型调用成本、异常错误率或 API Key 滥用

## 边界

- MaaS 模型调用走 `references/playbooks/maas-api-readiness.md` 和 `references/maas-model-calls.md`。
- MaaS 用量统计走 ModelArts MaaS ShowStatistics API，鉴权是 AK/SK 签名，不是 MaaS API Key bearer token。
- 默认只生成 request spec，不签名、不触网、不读取 AK/SK 值；显式 `--execute` 时只执行 MaaS ShowStatistics 只读查询，并且不输出 AK/SK、签名头或 project_id 原值。
- 真实查询前必须确认凭证、project_id、区域、权限和时间范围。

## 标准流程

### 1. 明确查询问题

先把用户问题转成明确指标：

- token：总 token、prompt token、completion token
- 请求：total request count
- 错误：total error count 和错误率
- 范围：最近 7 天、14 天、30 天、本月或明确日期
- 服务类型：预置服务、我的服务、自定义 Endpoint
- 推理类型：在线推理或批量推理

### 2. 生成 request spec

默认查询最近 7 天预置服务在线推理：

```bash
python3 scripts/maas_usage_request_plan.py --pretty
```

指定时间范围：

```bash
python3 scripts/maas_usage_request_plan.py \
  --from 2026-06-01 \
  --to 2026-06-08 \
  --service-type preset-service \
  --infer-type real_time \
  --pretty
```

自定义 Endpoint：

```bash
python3 scripts/maas_usage_request_plan.py \
  --preset last-30-days \
  --service-type custom-endpoint \
  --pretty
```

显式执行只读用量查询：

```bash
python3 scripts/maas_usage_request_plan.py \
  --preset last-7-days \
  --service-type preset-service \
  --infer-type real_time \
  --execute \
  --pretty
```

`start_time` 和 `end_time` 使用 UTC 毫秒时间戳；不要改成字符串日期。

### 3. 安全检查

真实查询前必须确认：

- 不要求用户在对话里粘贴 AK/SK 或 MaaS API Key。
- 凭证只从本地环境变量、hcloud profile 派生流程或受控凭证文件读取。
- 可识别 `HW_*`、`HUAWEICLOUD_*`、`HUAWEI_*`、`OS_*` 中的 AK/SK/project_id 别名；输出只显示变量来源和 presence。
- 需要的最小权限包括 `modelarts:monitoring:get`、`modelarts:service:get`、`iam:projects:get`。
- ShowStatistics 默认区域按 `cn-southwest-2` 处理；其他区域先验证支持情况。
- 时间窗口不要超过约 30 天；超过时拆分查询并聚合。

### 4. 结果解释

响应里的 token 字段通常以“千 token”为单位，汇报时要乘以 1000：

- `total_token`
- `total_prompt_token`
- `total_completion_token`

错误率按下面方式计算：

```text
error_rate = total_error_count / total_request_count
```

如果请求数为 0，不计算错误率，不要输出 0% 误导用户。

## 输出建议

成功拿到统计结果后，面向用户输出：

- 时间范围和服务类型
- 总请求数、总错误数、错误率
- 总 token、prompt token、completion token
- 和上一个可比周期的变化趋势，如果用户提供了对比要求
- 明显异常：错误率升高、token 暴涨、使用集中在某类服务
- 下一步建议：限流、Key 轮换、服务拆分、提示词压缩、预算告警或调用侧日志核对

## 不要做的事

- 不要把 MaaS API Key 当作 ShowStatistics 鉴权凭证。
- 不要把 token 统计等同于账单金额；如需金额，转到账单/成本治理流程。
- 不要在没有用户确认的情况下做真实用量查询。
- 不要输出完整 API Key、AK/SK、签名头或包含密钥的请求。
