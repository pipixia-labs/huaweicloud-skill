# Huawei NAT SNAT Stack Example

这是一个最小可运行的华为云 Terraform 示例，用于创建：
- 一个 VPC
- 一个 Subnet
- 一个 NAT Gateway
- 一个 EIP
- 一条 SNAT 规则

## 设计目标

- 自包含
- 便于评审
- 默认只覆盖出网能力链
- 适合作为私网资源统一出网模板基础

## 文件说明

- `versions.tf`: Terraform 和 provider 版本约束
- `provider.tf`: provider 配置
- `variables.tf`: 输入变量
- `main.tf`: 网络、NAT Gateway、EIP 和 SNAT 资源定义
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
region_name       = "cn-north-4"
vpc_name          = "demo-nat-vpc"
vpc_cidr          = "192.168.0.0/16"
subnet_name       = "demo-nat-subnet"
subnet_cidr       = "192.168.1.0/24"
subnet_gateway_ip = "192.168.1.1"
nat_gateway_name  = "demo-nat-gateway"
```

### 3. 执行

```bash
terraform init
terraform plan
terraform apply
```

## 注意事项

- 默认使用 subnet 级 SNAT，也就是 `snat_source_type = 0`
- 如果你想改成 CIDR 级 SNAT，需要把 `snat_source_type` 设为 `1`，并显式填写 `snat_cidr`
- 这个示例只覆盖出网能力，不包含 DNAT 或私网实例模板
