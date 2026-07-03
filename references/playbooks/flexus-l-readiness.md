# Flexus L Readiness

## 目标

Flexus L / 轻量服务器是面向小白用户、小企业和低成本试运行的产品候选。它适合简单后端、博客、小型管理后台、低并发 API、临时演示环境等场景。

当前本 skill 不把 Flexus L 伪装成已完整自动化的执行面。默认先做产品选型、费用和风险确认、hcloud metadata/help 发现、planner-only 方案，再决定是否进入受控执行。

## 适用场景

- 用户说“轻量服务器”“Flexus L”“云耀云”“低成本服务器”。
- 用户要部署一个简单应用，但还不需要 ELB/RDS/CCE。
- 用户关注购买、续费、退订、到期、费用和可维护性。
- 用户不清楚 OBS 静态站、Flexus L、ECS 的区别。

## 选型判断

| 用户目标 | 优先建议 |
| --- | --- |
| 纯静态官网、落地页、文档站 | OBS 静态网站托管 |
| 简单后端、博客、轻量应用、小团队试运行 | Flexus L |
| 需要自定义规格、复杂网络、ELB、RDS、长期 IaC | ECS 或 Terraform 路径 |
| 需要容器编排、弹性和多节点 | CCE / SWR / UCS 路径 |

## 必须确认

- region
- 镜像或应用类型
- CPU / memory / disk / 带宽
- 计费模式、购买时长、续费预期
- 是否需要公网 IP
- 管理来源 IP 或 VPN CIDR
- 登录方式：密码、密钥、COC/SSH fallback
- 是否需要备份、监控、域名、HTTPS
- 退订/释放是否影响数据

## hcloud-first 发现路径

1. 先做环境体检：

```bash
python3 scripts/hcloud_environment_doctor.py \
  --need hcloud \
  --pretty
```

2. 通过 hcloud help / metadata 查证服务和 operation，不凭经验硬写命令：

```bash
hcloud --help
hcloud <service> --help
```

3. 如果本地 metadata 能发现 Flexus / HCSS 相关 service，先做 read-only operation 识别；如果不能发现，输出 planner-only 方案和需要用户在控制台确认的字段。

4. 涉及购买、续费、退订时，同时进入 Billing/Cost 边界：
   - 费用和订单信息属于敏感数据。
   - 读取账单需要用户确认。
   - 退订不是普通删除，必须明确资源、订单、数据和退款影响。

## HCSS 控制面观察

当前材料显示 Flexus L 生命周期可能不完全落在普通 `hcloud <SERVICE> <Operation>` 形态中，部分创建/续费/退订路径会串联 HCSS、BSS 和 IAM：

- HCSS 负责轻量实例生命周期。
- BSS 负责订单、续费、退订和退款相关证据。
- IAM 负责 project/account scope、权限和临时凭证。

已观察到的 HCSS endpoint 形态是 `https://hcss.cn-north-4.myhuaweicloud.com/v1/light-instances`，region 参数更像实例售卖区域选择，而不是普通区域 endpoint 切换。这个结论在本项目中先标记为 `evidence_gap`：可以用于排障和方案解释，但在真正产品化执行前必须用当前账号、当前 region、当前文档或 live dry-run 复核，不把它写成长期稳定契约。

如果用户问“为什么 hcloud service 找不到 Flexus L”，可以解释为：它可能走轻量实例专用 HCSS 控制面，而不是普通 OpenAPI metadata service。不要因此改用裸 API 直接购买；仍然先输出 planner-only 方案、费用边界和需要用户确认的字段。

## 创建类边界

Flexus L 创建必须满足：

- 用户确认 exact region、规格、镜像、购买时长、带宽和费用。
- 安全组或公网入口不默认开放到 `0.0.0.0/0`。
- 登录凭证不出现在对话、日志或提交文件。
- 创建后必须做资源状态、登录和应用协议验收。
- 如需部署应用，优先使用幂等脚本或 cloud-init 风格方案。

如果缺少 operation detail 或费用证据，只能输出待确认计划，不能宣称可以提交。

## 续费和退订边界

续费：

- 先确认资源 ID、订单/实例归属、当前到期时间、续费周期和费用。
- 续费前输出费用风险和自动续费影响。

退订：

- 退订必须视为高风险操作。
- 先确认备份、数据导出、域名/DNS、EIP、快照、依赖服务。
- 默认只生成 `teardown_plan` / review checklist。
- 用户必须明确确认 exact resource 和影响后，才允许进入 guarded flow。

## 验收

创建或变更后至少验证：

- 资源存在且状态稳定。
- 公网 IP / DNS / 安全组符合预期。
- SSH 或 COC/机内命令可用。
- 应用服务进程、端口和 HTTP/HTTPS 协议探测通过。
- 监控和账单边界已说明。

## 输出给用户时

对小白用户不要只说产品名。输出应包含：

- 推荐 Flexus L、OBS 或 ECS 的原因。
- 本轮最小可运行方案。
- 费用和持续成本提醒。
- 需要确认的参数。
- 不能自动完成的边界。
- 后续验收证据。
