# Expert Evidence Regression Scenarios

这些场景验证新增内容是否减少误判。全部是只读判断测试，不要求真实账号，也不允许因此执行云资源变更。

## CCI-EXPERT-01：CLI 序列化与 exec 降级

- 正例：dry-run 和创建后回读都保留完整 annotation key，允许进入下一层 workload 计划。
- 易误判反例：dry-run 有值但回读缺少包含点号的 key，应报告版本相关 CLI blocker 并停止，不能切换写入执行器。
- 证据不足：hcloud 版本未知或对象无法回读，只能写 blocker 未确认；Pod exec 失败也不能判容器故障。

## CCE-EXPERT-01：指标与告警证据

- 正例：集群绑定、metrics endpoint、ServiceMonitor/PodMonitor、query 和时间窗均有证据，才解释指标值。
- 易误判反例：指标空序列或 active 告警为空，不能写健康；需区分 NXDOMAIN 与真实 DNS 错误、WATCH/CONNECT 与普通 API 请求。
- 证据不足：只有告警标题、没有 resource ID 时，只能标记弱关联；近期问题还需查询历史/已恢复告警。

## UCS-EXPERT-01：接入与策略合规

- 正例：使用正确 UCS cluster ID 回读 `Available`，access/fleet 可见；策略从有限范围 `warn` 验证后再规划扩大。
- 易误判反例：注册 accepted 或 policy job `Success`，但 cluster 未 Available 或 violation 非空，不能写接入完成/已合规。
- 证据不足：无法区分源 CCE ID 与 UCS ID，或缺少管理面可达性、job 时间、目标范围时，停止重试和 deny 推广。

## FLEXUS-COC-EXPERT-01：分层完成态

- 正例：订单、资源、管理通道、每个 COC target、主机服务、外部入口和最小应用请求全部通过，才写应用可用。
- 易误判反例：实例 `ACTIVE`、任务 `FINISHED`、端口监听，但外部模型请求失败，只能写完成到主机服务层。
- 证据不足：`coc_service_region`、`target_instance_region` 或 target agent 状态未知时，不靠切换 `--region` 重试定因。

## DWS-EXPERT-01：CPU、内存与 I/O 归因

- 正例：节点/磁盘范围、当前规格、同窗口 SQL/session/process/wait/plan 证据相互解释后，才提高根因置信度。
- 易误判反例：per-SQL I/O 为 0 或缺失时，CPU Top 不能写成 I/O Top；单节点偏差不能直接证明数据倾斜。
- 证据不足：缺少采样时间语义、CN/DN 角色、active/idle session 或磁盘分布时，保留多假设，不使用固定阈值归责。

## MODELARTS-EXPERT-01：训练作业渐进诊断

- 正例：job detail、失败 stage/event、目标 task 日志和跨 task 证据一致时，给出带置信度的失败点。
- 易误判反例：job 为 `Running` 但 stage、最近进度和日志都不前进，不能写运行正常；wrapper/collective abort 不一定是首个根因。
- 证据不足：只有 task ID、状态或一个 traceback 时，列出缺口；临时 OBS 日志 URL 不进入输出或提交。

## ICP-EXPERT-01：规则适用范围和时效

- 正例：先确认部署位置、对象、业务、主体、省份、备案类型和查询日期，再按“规则 × 适用范围 × 当前官方证据”回答。
- 易误判反例：本地旧案例、固定数字或单一“备案完成”状态，不能替代 ICP 备案、公安备案和经营性许可的分别判断。
- 证据不足：官方来源冲突、过旧或范围不清时标记 `evidence_gap`，不输出无条件的全国统一结论。
