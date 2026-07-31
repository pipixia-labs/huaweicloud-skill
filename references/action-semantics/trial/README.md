# M2/M2.5 试点 Action Spec

本目录保存统一 Action Plan 的试点语义覆盖层：ECS 受控建机、DNS 记录变更、MaaS 图像生成，以及 LTS/CTS 的受限只读取证。

- 这里的条目只保存 effect、风险、前置、验证和输出语义；hcloud 的 HTTP 方法、路径、参数等事实仍以 `references/hcloud-service-catalog/` 为唯一来源。
- `catalog_fingerprint` 是对应服务 catalog JSON 的规范化 SHA-256 指纹。catalog 刷新后必须重新核验，不允许静默沿用。
- 所有样例仅用于生成和评审 Action Plan，`v0.8.2` 升级期间不构成真实提交授权，也不接管现有脚本。
- LTS/CTS 在当前成熟度体系中仍是 candidate；这里的 `reviewed` 表示试点语义已人工检查，不能解释为服务已晋级 curated。
- ECS/DNS 的 M2.5 准入准备范围、上下文刷新要求和执行器缺口见 `m2-5-admission-preparation.md`。它们最多生成 `prepared_for_future_adapter`，不会生成 submit token 或调用旧入口。
