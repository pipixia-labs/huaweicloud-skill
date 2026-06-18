# Terraform Assets

本目录完整吸收原独立 Terraform skill 中对 `huaweicloud-skill` 有用的 Markdown 和 Terraform 示例资产，但运行时不要从这里“全量浏览”。Terraform 是 `hcloud` 的补充 IaC 面：用于可重复创建、环境复制、长期纳管、import 和 drift review；不是只读查询、排障和一次性小变更的默认入口。

## 默认入口

优先按下面顺序进入：

1. 先运行 `python3 scripts/hcloud_terraform_context_inspect.py --pretty`，确认 Terraform CLI、hcloud、环境变量、provider cache 和禁止提交的运行时产物状态。
2. 再运行 `python3 scripts/hcloud_terraform_router.py "<user-goal>" --pretty`，按用户意图选择少量示例和核心参考。
3. 只读取 router 返回的 `references` 和 `matches.path`；不要默认打开所有 `examples/terraform/*`。
4. 生成或修改 `.tf` 前，仍要按 `references/terraform-workflow.md` 先做 hcloud 现网发现，再做 Terraform fmt/init/validate/plan。
5. Terraform apply 必须等用户确认 exact plan；apply 后回到 hcloud 做资源状态和业务可用性验证。

## 目录角色

| 路径 | 角色 |
| --- | --- |
| `catalog/terraform-example-catalog.json` | 73 个 Terraform 示例的路由索引。 |
| `catalog/terraform-reference-catalog.json` | Terraform reference 的核心/高级/清单索引。 |
| `provider-auth.md` | Provider 和环境变量协同规则。 |
| `generation-guardrails.md` | Terraform 生成、验证、敏感信息和 apply 边界门禁。 |
| `provider-validation.md` | Provider mirror/cache、schema/fmt/validate、版本漂移和 installer 借鉴边界。 |
| `discovery-workflow.md` | hcloud 发现现网后再生成 IaC 的流程。 |
| `interop-with-hcloud.md` | Terraform 与 hcloud 的协作边界。 |
| `service-variant-guide.md` | 同一服务不同变体的选择规则。 |
| `data-source-selection-guide.md` | data source 与既有资源复用选择规则。 |
| `troubleshooting.md` | 常见 Terraform/provider 错误处理。 |
| `inventories/` | provider 资源、data source、能力面和参考示例总索引；仅在用户问覆盖面或维护 catalog 时读取。 |
| `source-skill.md` | 原独立 Terraform skill 的归档内容，不作为当前技能入口。 |

## Provider inventory 维护

`inventories/provider-resource-inventory.md` 和 `inventories/provider-data-source-inventory.md` 来自本地 `reference-projects/terraform-provider-huaweicloud/docs` 快照。当前快照是 provider changelog `1.93.0`，包含 1689 个 resource 和 2251 个 data source。

维护时运行：

```bash
python3 scripts/hcloud_terraform_provider_inventory.py --write --pretty
python3 scripts/hcloud_terraform_provider_inventory.py --fail-on-drift --pretty
python3 scripts/hcloud_terraform_provider_inventory.py --signal-kind resources --signal-name rds_instance --pretty
```

这些 inventory 只回答“provider 覆盖了什么”。`--signal-kind/--signal-name` 只读 provider Markdown，抽取单个 resource/data source 的 `ForceNew`、`Import` 段和敏感字段线索；生成或修改 `.tf` 前可用它提醒用户“这个字段变更可能重建资源”或“这个资源支持 import 但不能自动导入”。它们不是默认路由清单，更不是执行许可清单。新增 resource/data source 进入示例或 agent 默认路线前，还要看是否符合 `hcloud` 发现、Terraform plan review、风险分级和后置验证要求。

## 资产卫生

- 可以提交 `.terraform.lock.hcl` 和 `terraform.tfvars.example`。
- 不要提交 `.terraform/`、`terraform.tfstate*`、真实 `*.tfvars`、`crash.log`、AK/SK、token、密码或私钥。
- 修改示例后运行 `python3 scripts/hcloud_terraform_catalog.py --write --pretty` 重建 catalog，并跑资产测试。
