# Huawei NAT DNAT Stack Example

这是一个最小可运行的华为云 Terraform 示例，用于创建：
- 一个 VPC
- 一个 Subnet
- 一个 NAT Gateway
- 一个 EIP
- 一台 ECS
- 一条 DNAT 规则

## 设计目标

- 自包含
- 便于评审
- 默认覆盖公网入站映射链路
- 适合作为简单单机入口转发模板

## 文件说明

- `versions.tf`: Terraform 和 provider 版本约束
- `provider.tf`: provider 配置
- `variables.tf`: 输入变量
- `main.tf`: 网络、NAT、EIP、ECS 和 DNAT 资源定义
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
vpc_name          = "demo-dnat-vpc"
vpc_cidr          = "192.168.0.0/16"
subnet_name       = "demo-dnat-subnet"
subnet_cidr       = "192.168.1.0/24"
subnet_gateway_ip = "192.168.1.1"
nat_gateway_name  = "demo-dnat-gateway"
instance_name     = "demo-dnat-ecs"
admin_password    = "ChangeMe123!"
ingress_cidr      = "203.0.113.10/32"
```

### 3. 执行

```bash
terraform init
terraform plan
terraform apply
```

## 注意事项

- `ingress_cidr` 必须显式填写，示例不默认对全网开放后端端口
- 这个示例默认做单端口 DNAT 映射，不覆盖端口段映射
- 如果你要映射到已有 ECS 或 RDS，可以改成直接引用已有 port / private_ip
