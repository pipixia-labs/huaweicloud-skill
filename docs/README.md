# huaweicloud-skill Developer Documentation

本目录是 `huaweicloud-skill` 的开发者文档，解释这个 skill 的架构、设计取舍、关键实现和数据资产。这里的文档面向维护者和二次开发者，不作为 agent 的运行时指令入口。

运行时入口仍然是：

- `SKILL.md`
- `references/workflow.md`
- `references/service-registry.json`
- `scripts/`

## 阅读顺序

建议按下面顺序阅读：

1. [technical-overview.md](technical-overview.md)
   - 快速了解这个 skill 的技术定位、架构平面、核心优势和当前能力边界。
   - 适合第一次接手实现、评审架构或规划扩展路线时阅读。
2. [architecture.md](architecture.md)
   - 了解整体分层、执行链路、模块边界。
   - 适合第一次接手本项目时阅读。
3. [cloud-lifecycle-scenarios.md](cloud-lifecycle-scenarios.md)
   - 了解执行“上云、用云、管云”任务时，用 `huaweicloud-skill` 和不用的差别。
   - 适合评审产品价值、设计演示案例或扩展典型服务能力时阅读。
4. [implementation-details.md](implementation-details.md)
   - 了解关键脚本如何工作。
   - 重点包括安全执行、元数据发现、registry 驱动、ECS/EIP/OBS 特殊流程、通用 guarded flow 和验证器。
5. [data-and-coverage.md](data-and-coverage.md)
   - 了解 `references/`、`materials/`、`service-registry.json`、coverage 脚本和测试之间的关系。
   - 适合扩展服务覆盖或调整质量门禁时阅读。

## 技术主线

阅读和维护本项目时，建议抓住下面这条技术主线：

1. 这不是普通 prompt，而是一个围绕华为云 KooCLI 的可执行云操作框架。
2. 核心架构是 registry 控制面、safe exec 执行面、verifier 验证面、quality gate 回归面。
3. v0.3 已从 ECS 单点闭环和多服务覆盖继续扩展到账号盘点、闲置审计、可观测、Billing/Cost request spec 和治理候选画像；v0.3.2 进一步把 VPC/安全组、EIP、EVS、ELB、RDS、OBS、DNS、SCM、CDN、CES/LTS 组织成 P0 任务级 lifecycle closure planner；P1 把 TMS、CTS、CBR、RMS/Config、Billing/BSS、WAF、DLI、CodeArtsRepo 组织成带 evidence command plan 和治理汇总的治理闭环 planner；v0.3.3 把 CCE、NAT、DCS、RFS、UCS、IAM/KPS/IMS、安全姿态和数据库族组织成 P2 场景闭环 planner。准确 registry 服务数和 operation 计数以 `python3 scripts/hcloud_catalog_audit.py --pretty` 的 `registry` 字段为准。
4. 写类操作默认不自动提交，而是走 plan、dry-run、显式确认和后置验证，适合真实云资源场景的风险控制。
5. 单测、架构契约、materials drift 和 coverage 脚本是回归门禁，用来持续防止 coverage 和安全边界退化。

## 文档边界

这些文档解释实现，不直接替代以下文件：

- 面向 agent 的行为规则：`SKILL.md`
- 操作流程和 playbook：`references/`
- 机器可读服务能力：`references/service-registry.json`
- 可执行入口：`scripts/`
- 契约和回归验证：`tests/`

如果实现和文档出现冲突，以代码、测试和 `service-registry.json` 为准，然后更新本目录文档。

## 维护要求

修改实现时，通常需要同步检查：

```bash
python3 -m unittest discover tests
python3 -m compileall -q scripts
python3 scripts/check_materials_drift.py --pretty
```

只改开发者文档时，至少运行：

```bash
git diff --check
```
