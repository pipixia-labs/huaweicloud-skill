# CES Metric Readiness Playbook

## 目标

确认云监控指标 namespace、dimension、period 和时间范围，避免空结果被误判为资源异常。

## 适用场景

- 查询可用指标
- 为 ECS、ELB、RDS 等服务做监控前置检查
- 排查监控数据为空、维度错误或时间范围错误

## 标准检查

```bash
python3 scripts/hcloud_resource_discovery.py --service CES --operation ListMetrics --region=<region> --limit=50 --pretty
```

查询具体指标前必须先从目标服务确认：

- namespace
- metric name
- dimension name/value
- period
- from/to 时间范围

## 风险边界

- 当前 curated 覆盖只承诺只读 metric discovery。
- 告警规则、通知屏蔽、资源组等 mutation 不纳入当前 registry。
- 监控无数据不直接等于资源故障；先检查 region、namespace、dimension 和采集延迟。

## 验收

成功时输出 namespace、metric、dimension 和可查询时间范围。失败时说明是维度不匹配、时间范围不合理、指标未上报还是权限/region 问题。
