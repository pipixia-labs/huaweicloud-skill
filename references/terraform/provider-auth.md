# Provider & Auth

本文件定义华为云 Terraform provider 的推荐写法，以及与 `huaweicloud-skill` / `hcloud` 主链路的环境变量协同规则。

## 推荐 `required_providers`

```hcl
terraform {
  required_providers {
    huaweicloud = {
      source  = "huaweicloud/huaweicloud"
      version = ">= 1.36.0, < 2.0.0"
    }
  }
}
```

说明：
- provider 源应使用 `huaweicloud/huaweicloud`
- 版本约束应明确写出，不要省略
- 版本策略建议使用明确的最小版本和主版本上界，不要完全放开

## 推荐 provider 配置

### 1. 环境变量驱动，优先推荐

```hcl
provider "huaweicloud" {}
```

推荐配套环境变量：

```bash
export HW_ACCESS_KEY="your-ak"
export HW_SECRET_KEY="your-sk"
export HW_REGION_NAME="cn-north-4"
```

### 2. 显式 provider 参数

```hcl
provider "huaweicloud" {
  region     = var.region_name
  access_key = var.access_key
  secret_key = var.secret_key
}
```

适用场景：
- 示例代码
- 多 provider alias
- 需要明确展示认证来源

### 3. 临时凭证

```hcl
provider "huaweicloud" {
  region         = var.region_name
  access_key     = var.access_key
  secret_key     = var.secret_key
  security_token = var.security_token
}
```

## 与项目现有 `HUAWEI_*` 变量的兼容规则

项目中既有 `hcloud` 主链路可能常用：
- `HUAWEI_ACCESS_KEY`
- `HUAWEI_SECRET_KEY`
- `HUAWEI_REGION`
- `HUAWEI_PROJECT_ID`

Terraform provider 官方常用：
- `HW_ACCESS_KEY`
- `HW_SECRET_KEY`
- `HW_REGION_NAME`
- `HW_PROJECT_NAME`

### 兼容建议
- 文档和 Terraform 最佳实践优先写 `HW_*`
- 如果任务上下文只提供了 `HUAWEI_*`，应提醒用户 Terraform 官方默认读取的是 `HW_*`
- 在联动模式下，可以提示做以下映射：

```bash
export HW_ACCESS_KEY="$HUAWEI_ACCESS_KEY"
export HW_SECRET_KEY="$HUAWEI_SECRET_KEY"
export HW_REGION_NAME="$HUAWEI_REGION"
```

注意：
- `HUAWEI_PROJECT_ID` 不是 provider 官方默认环境变量
- 如果任务需要 project 级别约束，应优先通过显式变量或现网发现确认

## 其他认证方式

根据 provider 文档，华为云 provider 还支持：
- `shared_config_file`
- ECS Instance Metadata Service
- `assume_role`
- `assume_role_with_oidc`

第一轮 skill 中应当：
- 知道这些方式存在
- 能在用户提及时引用
- 但默认示例仍以 AK/SK 或环境变量方式为主

## 实践规则
- 不要在示例代码里硬编码真实凭证
- 不要把凭证直接写入 `terraform.tfvars` 并提交版本库
- 如果用户已经在 ECS 上运行 Terraform，优先考虑元数据方式而不是明文 AK/SK
