# Terraform Generation Guardrails

本文件把上游 Terraform generator 中可复用的生成规则吸收到 `huaweicloud-skill`，但统一到当前项目的 hcloud-first 边界：先发现现网，再生成 IaC 草案；先 plan review，再由用户明确确认 apply；apply 后必须回到 hcloud 做状态和业务验收。

## 生成前必须确认的事实

不要编造这些信息：

- region、project、企业项目
- AZ、镜像、规格、磁盘类型
- VPC、subnet、安全组、EIP、ELB、RDS、CCE 等现有资源 ID
- 价格、库存、售罄状态
- apply、验证或修复过程

事实来源只能是：

- 用户明确输入
- hcloud 只读查询和现网发现
- Terraform data source 在 plan 阶段解析出的结果
- 本地 provider schema / inventory 提供的字段结构线索

如果事实没有确认，只能标成 pending 或 recommendation，不能写成已验证结论。

## hcloud-first 流程

1. 用 `hcloud_context_inspect.py` 和服务发现脚本确认账号、region、project 和现网资源。
2. 用 `hcloud_terraform_context_inspect.py` 检查 Terraform CLI、provider cache、环境变量、mirror 配置和禁止提交产物。
3. 用 `hcloud_terraform_router.py` 只选择少量相关 example/reference。
4. 生成或改造 Terraform 草案。
5. 运行 `terraform fmt`、`terraform init`、`terraform validate`、`terraform plan`。
6. 摘要 plan 里的新增、修改、删除、替换、停机和计费风险。
7. 用户明确确认 exact plan 后才能 apply。
8. apply 后回到 hcloud 做资源 readback、健康检查、协议探测和业务验收。

## 文件结构规则

推荐示例结构：

- `versions.tf`
- `provider.tf`
- `variables.tf`
- `main.tf`
- `outputs.tf`，只在有明确验收价值时添加
- `terraform.tfvars.example`
- `README.md`

禁止提交：

- 真实 `terraform.tfvars`
- `.terraform/`
- `terraform.tfstate*`
- `crash.log`
- AK/SK、token、密码、私钥、证书私钥

## Provider 和凭据规则

- Provider 源必须是 `huaweicloud/huaweicloud`。
- 新示例优先使用 `HW_*` 变量语义，并兼容 `OS_*` / `HUAWEICLOUD_*` 诊断。
- 不要在 `.tf` 或 `tfvars` 中写真实 AK/SK。
- 不要在对话中要求用户粘贴 AK/SK、token、密码或私钥。
- shared hcloud config 只有在未加密且用户理解风险时才适合 Terraform provider 复用。

## Data Source 优先规则

这些值优先通过 data source 或 hcloud 发现，不要硬编码：

- ECS image、flavor、AZ
- CCE cluster flavor、node flavor、addon template
- RDS flavor、引擎版本、AZ 组合
- ELB flavor、可用区
- 现网 VPC、subnet、安全组、EIP、port

Data source 查询必须使用精确过滤条件。不要用模糊名称猜资源，也不要在结果为空时静默 fallback 到硬编码值。

## 安全组规则

- 端口必须是 `1-65535`，不能使用 `0`。
- SSH、数据库、管理端口、常见 Web 端口不应默认开放给 `0.0.0.0/0`。
- 示例里的公网来源 CIDR 应使用文档占位，例如 `203.0.113.10/32`，并提醒用户替换为真实授权来源。
- 内网服务优先限制在 VPC CIDR、subnet CIDR 或明确的后端安全组。

## 敏感字段规则

示例中如果需要密码：

- 优先使用 `random_password` 或要求用户在本地 `terraform.tfvars` 中填写。
- 不要把生成出的真实密码写进 README、日志或提交文件。
- 不要把密码输出成 Terraform output，除非有明确的安全处理策略。

## 验证门禁

每个吸收进 `examples/terraform` 的示例至少满足：

- `terraform.tfvars` 已改成 `terraform.tfvars.example`
- `README.md` 不要求用户在对话中暴露敏感信息
- catalog 能被 `hcloud_terraform_router.py` 命中
- `hcloud_terraform_context_inspect.py` 不报告 forbidden artifact
- `terraform fmt -check -recursive` 通过
- 在 provider 可用时，`terraform init -backend=false` 和 `terraform validate` 通过

## 不吸收的上游行为

- 不把上游 generator 作为 `huaweicloud-skill` 的默认入口。
- 不自动安装 Terraform 或 provider。
- 不自动 apply。
- 不自动 destroy。
- 不把 provider mirror 网络下载当成默认执行动作。
