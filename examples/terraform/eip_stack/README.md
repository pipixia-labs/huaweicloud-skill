# Huawei EIP Stack Example

这是一个最小可运行的华为云 Terraform 示例，用于创建一个独立 EIP。

## 设计目标

- 自包含
- 便于评审
- 默认采用专用带宽
- 适合作为 ELB、NAT、ECS 公网入口的基础模板

## 文件说明

- `versions.tf`: Terraform 和 provider 版本约束
- `provider.tf`: provider 配置
- `variables.tf`: 输入变量
- `main.tf`: EIP 资源定义
- `outputs.tf`: 输出结果

## 推荐使用方式

### 1. 配置环境变量

```bash
export HW_ACCESS_KEY="your-ak"
export HW_SECRET_KEY="your-sk"
export HW_REGION_NAME="cn-north-4"
```

### 2. 准备变量文件

复制 `terraform.tfvars.example` 为 `terraform.tfvars`，再按实际环境填写：

```hcl
region_name = "cn-north-4"
eip_name    = "demo-eip"
```

### 3. 执行

```bash
terraform init
terraform plan
terraform apply
```

## 注意事项

- 默认使用 `5_bgp` 和专用带宽
- EIP 常作为 ELB、NAT 或 ECS 的公网入口组件
