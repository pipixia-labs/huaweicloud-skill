# Huawei SWR Stack Example

这是一个最小可运行的华为云 Terraform 示例，用于创建：
- 一个 SWR Organization
- 一个 SWR Repository

## 设计目标

- 自包含
- 便于评审
- 适合作为镜像仓库最小模板

## 文件说明

- `versions.tf`: Terraform 和 provider 版本约束
- `provider.tf`: provider 配置
- `variables.tf`: 输入变量
- `main.tf`: 主资源定义
- `outputs.tf`: 输出结果

## 推荐使用方式

### 1. 配置环境变量

```bash
export HW_ACCESS_KEY="your-ak"
export HW_SECRET_KEY="your-sk"
export HW_REGION_NAME="cn-north-4"
```

### 2. 准备变量文件

复制 `terraform.tfvars.example` 为 `terraform.tfvars`，再按实际环境填写。

### 3. 执行

```bash
terraform init
terraform plan
terraform apply
```

## 注意事项

- 这是基础仓库模板，不覆盖企业版高级策略、同步或保留策略
- 如果要对接 CCE 或镜像同步，建议在此基础上继续扩展
