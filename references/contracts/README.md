# 统一操作契约

本目录保存与 Agent 宿主无关的 JSON Schema：Cloud Context、Action Spec、Action Plan、Execution Intent、Submission Authorization、Metadata Read Plan 与 Operation Result。它们只描述跨服务、跨工具复用的语义和安全边界；KooCLI/OpenAPI 的方法、路径、参数和版本事实继续保留在既有 `hcloud-service-catalog/` 中。

可用以下命令进行纯离线校验：

```bash
python3 scripts/hcloud_unified_contracts.py \
  --contract action-spec \
  --input <action-spec.json> \
  --pretty
```

校验会拒绝秘密字段、无精确 catalog 引用的 hcloud Action Spec，以及把 HTTP/参数事实复制进 Action Spec 的做法。校验成功只说明结构和局部语义正确，**不**构成提交授权；真实提交仍需后续策略、Action Plan、确认与受控入口共同满足。

## M2 Action Plan 生成

```bash
python3 scripts/hcloud_action_plan.py \
  --action-spec references/action-semantics/trial/ecs-create-server.json \
  --cloud-context tests/fixtures/unified-action-plan/ecs-context.json \
  --pretty
```

生成器只读取本地 JSON 和本地 catalog；hcloud Action Spec 还会重新核对服务 catalog 的规范化指纹、operation 与版本。输出中的 `allowed_stage` 表示在列出的前置完成后，策略允许**规划到**的最高下一阶段，不是立即执行指令；`execution_authority.submission_authority=not_implemented` 明确表示当前实现没有统一提交授权或执行器。

可将已经脱敏的本地脚本结果归一化为 Operation Result：

```bash
python3 scripts/hcloud_operation_result.py \
  --input <redacted-local-result.json> \
  --stage submit \
  --pretty
```

该工具不会重放源操作，也不会保留原始命令、请求体或输出。超时等错误会进入统一错误策略；提交阶段超时的固定下一步是先读回 job 或资源状态，而不是自动重试。

## 受控提交准入准备

```bash
python3 scripts/hcloud_controlled_admission.py \
  --action-spec <curated-action-spec.json> \
  --cloud-context <cloud-context.json> \
  --execution-intent <execution-intent.json> \
  --confirmation <confirmation.json> \
  --pretty
```

该工具把 Action Plan、任务级 Execution Intent 与显式确认组合成
`submission-authorization/v1`。它会重新核对 Action Spec 与 catalog、区域和项目范围、
计划指纹、执行输入指纹、预检证据指纹、语义 required input，以及每一个 Action Plan 预检项的 `passed` 证据；目标、输入或
确认任一变化都会使准备失败。

成功结果中的 `prepared_for_future_adapter` 仅表示这组材料可以交给**未来**的受控执行器
再次校验。`submission_authority=not_implemented` 和 `mode=plan_only` 表示此命令没有、也
不能生成提交许可、命令片段或云端请求。审批记录的身份认证、一次性使用和审计持久化由
未来宿主/执行器实现，不能由本地 `approval_id` 代替。

## 受限 Metadata Read 计划

```bash
python3 scripts/hcloud_metadata_read_plan.py \
  --action-spec references/action-semantics/trial/cts-list-traces.json \
  --cloud-context tests/fixtures/unified-action-plan/cts-ready-context.json \
  --pretty
```

该工具只接受 reviewed/curated 的 hcloud `effect=read` Action Spec，并同时核对 catalog 指纹、operation、版本、`read_only` 元数据、区域/项目范围和受限输出策略。它不会接受裸命令片段、跳过版本解析或无限输出选项。

输出中的 `eligible_for_future_adapter` 只表示**计划条件齐全**；`metadata_read_authority=not_implemented` 表示当前不存在读取执行器。缺少 LTS 日志时间范围、日志组或日志流等输入时，计划会以 `blocked` 返回而不是猜测或调用 API。

## 旧入口影子比较

```bash
python3 scripts/hcloud_entrypoint_shadow_audit.py \
  --source-path scripts/hcloud_safe_exec.py \
  --action-spec references/action-semantics/trial/ecs-create-server.json \
  --cloud-context tests/fixtures/unified-action-plan/ecs-context.json \
  --pretty
```

影子比较从已审查的执行入口清单读取旧路径的实际准入模型，并与同一输入生成的统一计划并排输出。它会直接暴露“旧 mutation/read 路径尚未桥接”等差异，且只接受清单中登记的精确 source path；它不会 import、调用或修改旧入口。
