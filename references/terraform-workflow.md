# Terraform Workflow

Terraform 是已接入的补充 IaC 变更面，适合可重复创建、环境复制、长期纳管、import 和 drift review。它不替代 hcloud 的上下文发现、只读核验和故障排查，也不由 SDK runner 承担。

## 三个执行面

| 执行面 | 角色 | 默认边界 |
| --- | --- | --- |
| hcloud | 主查询/执行面，负责真实上下文、资源发现、dry-run、提交和后置验证。 | 变更需显式确认。 |
| SDK | hcloud 补充面，负责参数类型、request model、region/endpoint 和少量 allowlist 只读查询。 | 不做通用写操作。 |
| Terraform | IaC 面，负责声明式资源、plan、validate、apply 和 drift 管理。 | 不自动 apply；apply 后仍用 hcloud 验证。 |

## 什么时候用 Terraform

优先考虑 Terraform 的场景：

- 用户要创建一组可重复的基础设施，例如 VPC、ECS、ELB、RDS、CCE。
- 用户希望保存配置、review diff、复制环境或长期纳管。
- 任务需要明确变量、输出、依赖关系和模块边界。
- 需要把现有资源逐步导入 IaC 管理。

不优先考虑 Terraform 的场景：

- 一次性只读查询、排障或资源状态核验。
- 需要快速定位 hcloud 参数、权限、region、project 或 CLI 错误。
- 资源变更很小，且 hcloud guarded flow 已能清楚表达风险和验证。
- 用户没有要求 IaC，且任务只需要临时补齐依赖或做后置验证。

## 推荐流程

1. **确认目标**
   - 明确是新建、纳管现有资源、复制环境、还是 drift review。
   - 记录 region、project、企业项目、资源命名、计费影响和回滚边界。
   - 运行 `python3 scripts/hcloud_terraform_router.py "<user-goal>" --pretty`，只选择命中的少量 `examples/terraform/*` 和 `references/terraform/*`。

2. **hcloud 发现现状**
   - 运行 `hcloud_context_inspect.py`。
   - 运行 `hcloud_terraform_context_inspect.py`，确认 Terraform CLI、provider cache、环境变量和禁止提交的 runtime artifact。
   - 用 `hcloud_resource_discovery.py`、`hcloud_resource_query.py` 和对应 playbook 收集现有 VPC、subnet、安全组、EIP、镜像、规格、RDS/ELB/CCE 等证据。
   - 对 SDK allowlist 中的补充点，可用 SDK metadata 验证参数类型和 request path。

3. **生成 Terraform 草案**
   - 只生成必要资源，不把账号内所有资源一次性塞入 state。
   - 把变量、provider、资源、输出拆清楚。
   - 避免把 AK/SK、密码、token、私钥写进 `.tf`、`tfvars`、state 或日志。
   - 已有资源应优先使用 import 或 data source 方案；不要默认重建。

4. **本地校验**
   - 运行 `terraform fmt`。
   - 运行 `terraform init`。
   - 运行 `terraform validate`。
   - 运行 `terraform plan`，并把新增、修改、删除、替换、费用和停机风险摘要给用户。
   - 没有 Terraform CLI、provider 下载能力或本地 plugin cache 时，只能交付可审查草案和下一步环境缺口，不能宣称 plan 已通过。

5. **显式确认后 apply**
   - 用户必须确认 exact plan、region、project、资源清单和风险。
   - 不要把 `terraform apply -auto-approve` 作为默认建议。
   - apply 输出中涉及敏感字段必须摘要和脱敏。

6. **hcloud 后置验证**
   - apply 后回到 hcloud 查询资源状态。
   - ECS 要继续 job/ACTIVE/SSH/应用验收。
   - ELB 要继续 member health 和协议探测。
   - RDS 要继续实例、备份、配置和连接证据。
   - CCE 要继续集群、节点、网络和监控证据。

## 与 SDK 的关系

- SDK 不负责生成 Terraform。
- SDK 可以补充 Terraform 草案所需的 API 参数类型、region 线索和只读资源详情。
- 若 hcloud 和 SDK 对字段名称或可选性给出不同线索，以实际 hcloud dry-run/查询和官方 Terraform provider schema 为准。
- SDK allowlist 不因为 Terraform 接入而扩大。

## 安全边界

- 不保存真实 AK/SK、token、密码、私钥。
- 不自动 apply。
- 不自动 destroy。
- 不用 Terraform 批量接管未知生产资源。
- 不把 plan 中的替换、删除、停机、计费风险藏在长日志里。
- 不在没有 hcloud 后置验证的情况下宣称 IaC 变更完成。

## 本地资产面

Terraform 资产入口放在 `references/terraform/README.md`。当前已吸收：

- 73 个 `examples/terraform/*` 示例，覆盖 ECS、VPC/安全组、EIP、EVS、ELB、RDS、OBS、CCE、NAT、DNS、DCS、治理、安全、可观测和端到端业务拓扑。
- `references/terraform/catalog/terraform-example-catalog.json`：示例路由 catalog。
- `references/terraform/catalog/terraform-reference-catalog.json`：reference 路由 catalog。
- Provider 认证、生成门禁、provider validation、hcloud interop、discovery workflow、data source 选择、service variant、troubleshooting 和 inventory 文档。

运行时先用 router 选资产，再按需读取。`inventories/` 只在用户问 provider 覆盖面、data source 覆盖面或维护 catalog 时读取。

## 后续增强建议

继续增强 Terraform 时，优先补独立脚本或 reference，而不是改造 SDK runner：

- plan helper：读取 hcloud 发现结果，生成变量草案和检查清单。
- import plan：指导现有资源导入和 state 风险；当前先按 `references/terraform/operations.md` 做手工可审查流程。
- provider schema cache：缓存 provider schema，辅助字段校验。
- hcloud verifier：从 Terraform output 生成 hcloud 后置验证计划。
