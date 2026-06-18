---
name: huaweicloud-skill
description: 使用 hcloud 命令行工具执行华为云资源查询、分析、规划和变更。适用于用户明确要走 CLI/KooCLI 路线，或任务需要通过 hcloud 直接发现 service/operation、构造命令、执行查询或变更、排查认证、网络、缓存与输出格式问题的场景；当华为云部署静态站、独立站或 Web 应用需要图片素材时，可通过华为云 ModelArts MaaS 图像生成 API 生成本地站点资产。
---

# Huawei CLI Skill

## 核心定位

- 这是一套基于 `hcloud` 的华为云执行型 skill。
- SDK 是 `hcloud` 的补充，不是第二套大而全执行面。只有当 SDK 能让 `hcloud` 主链路更稳时才使用，例如补充参数类型、region/endpoint、错误结构、凭证来源线索，或执行少量 `references/sdk-supplement-registry.json` allowlist 内的稳定只读查询。
- 用户机器不要求有 SDK 源码仓库；如果需要 SDK 补充能力，优先使用已安装的 `huaweicloudsdk*` Python package。`reference-projects/huaweicloud-sdk-python-v3` 只作为本仓库维护期参考。
- Terraform 是 `hcloud` 的补充 IaC 变更面，适合可重复创建、环境复制、长期纳管、import 和 drift review；进入前先用本地 Terraform router/context inspect 选资产和查环境，不要全量浏览示例，也不要跳过 hcloud 发现与后置验证。
- MaaS 图像生成只作为华为云 Web/独立站部署的辅助资产生成能力，必须使用华为云 ModelArts MaaS API，默认模型为 `qwen-image`，不作为通用生图入口，也不登记为 KooCLI service。
- 目标不是背命令，而是让 agent 能稳定完成一条完整链路：
  - 识别上下文
  - 发现 service 和 operation
  - 构造安全命令
  - 执行查询或变更
  - 校验结果
  - 处理常见错误

## 推荐闭环流程

当用户提出上云、用云或排障目标，且任务落在 P0 高频服务（VPC/安全组、EIP、EVS、ELB、RDS、OBS、DNS、SCM、CDN、CES/LTS）时，优先按下面的本地闭环推进：

1. 先用 `hcloud_scenario_router.py` 判断目标命中的 playbook、guide、planner、SDK supplement 或 Terraform 候选。
2. 对 P0 任务运行 `hcloud_lifecycle_closure_plan.py`，生成六阶段 lifecycle plan 和 `acceptance_evidence_plan`。
3. 需要采集验收证据时，运行 `hcloud_acceptance_probe_plan.py`，只生成非执行探测模板；不要把模板输出当作已采集证据。
4. 证据采集后，把人工或工具整理出的本地 status JSON 交给 `hcloud_acceptance_evidence_result.py`，得到 `passed`、`warning`、`missing` 或 `blocked`。
5. 需要写周报、评审成熟度或判断下一批补强目标时，运行 `hcloud_closure_maturity_audit.py`，诚实区分 ECS 样板、P0 task-level planner、P1/P2 planner-only 和 metadata-backed evidence gap。

这个流程默认不执行 live probe、不处理凭据、不发账单请求、不开放治理/安全/数据库写操作。真实 submit 仍必须走对应 guarded flow，并获得用户对本次操作的明确确认。

## 安全边界摘要

真实云资源操作必须可审计、可复现、可验证。详细规则在 `references/runtime-safety-boundaries.md`；执行创建、变更、网络暴露、ECS 机内操作、COC/SSH fallback、应用验收或排障时先读取该 reference。

- 异步任务必须跟到终态，不能把 `job_id`、`accepted`、`ACTIVE` 当成业务完成。
- 执行型任务先查证据，再 dry-run / planner，再按 guarded flow 和用户明确确认提交。
- 查询类默认 JSON，输出要带命令、region/project、返回条数和关键字段。
- 安全组 SSH/Web 常见入口端口不得自动开放到 `0.0.0.0/0`；复用已有安全组也必须读回规则证据。
- Web、ELB、数据库、Docker、EVS 挂载等任务必须做协议、健康或机内验收，不能只看云侧状态。
- COC、cloud-init、SSH fallback 的使用边界见 `references/playbooks/coc-readiness.md` 和 `references/runtime-safety-boundaries.md`。

## 什么时候使用

优先在以下场景使用本 skill：

- 用户明确提到 `hcloud`、`KooCLI`、CLI、命令行方式管理华为云。
- 任务需要直接通过 `hcloud` 查询或变更华为云资源。
- 任务需要查看 `service` / `operation` 列表、构造 `--cli-jsonInput`、使用 `--cli-query`、`--dryrun`、`--cli-waiter` 等 CLI 能力。
- 任务需要排查 `hcloud` 的认证、区域、项目、缓存、网络、输出格式问题。
- 任务是在华为云 ECS/OBS/CDN 等 Web 载体上部署站点，并明确要求用华为云 MaaS 图像生成能力生成站点图片资产。


## 资料入口

先看整理后的资料，再回到原始材料：

1. `references/workflow.md`
2. `references/runtime-safety-boundaries.md`
3. `references/auth-and-context.md`
4. `references/cache-prewarm.md`
5. `references/local-meta-discovery.md`
6. `references/service-coverage.md`
7. `references/sdk-supplement.md`
8. `references/scenario-router.json`
9. `references/guides/`
10. `references/terraform-workflow.md`
11. `references/terraform/README.md`
12. `references/terraform/generation-guardrails.md`
13. `references/terraform/catalog/terraform-example-catalog.json`
14. `references/terraform/catalog/terraform-reference-catalog.json`
15. `references/command-construction.md`
16. `references/error-playbook.md`
17. `references/output-and-query.md`
18. `references/iam-actions-catalog.json`（权限失败诊断时读取；用于提示需检查的 IAM action、scope 和 deny 边界，不替代官方 IAM 文档）
19. `references/scripts.md`
20. `references/script-audience-manifest.json`（维护/升级评审时读取，用于判断脚本受众和精简边界）
21. `references/versioning-policy.md`（维护/发版时读取，版本事实以 `CHANGELOG.md` 和 `RELEASE_NOTES.md` 为准）
22. `references/service-registry.json`
23. `references/service-curation-profiles.json`
24. `scripts/hcloud_catalog_audit.py`
25. `references/playbooks/`
26. `references/source-map.md`
27. `examples/README.md`
28. `references/maas-image-generation.md`（MaaS 图像生成主参考；`references/qwen-image-generation.md` 为兼容旧文件名）

维护和升级评审时，可用 `tests/v0_6_acceptance_scenarios.md` 检查小白用户、小企业和中等企业场景是否仍被覆盖；不要在普通用户任务里加载测试文件。

原始 KooCLI 材料在 `materials/` 下，仅作为资料源，不应直接当作最终指令集使用。
华为云官方文档优先从 `https://support.huaweicloud.com/intl/zh-cn/` 查证；涉及 API 字段语义时，以官方文档和实际 `hcloud --dryrun`/查询结果为准。

## 默认工作流

1. 先确认上下文
   - 优先运行 `python3 scripts/hcloud_context_inspect.py --pretty`
   - 明确 `hcloud` 是否可用、当前 profile、默认 region、project、offline mode、meta cache 是否存在
   - 如果 `hcloud.found=false`，停止真实云查询和变更；提示用户先按华为云官方快速安装文档安装 KooCLI：`https://support.huaweicloud.com/qs-hcli/hcli_02_003.html`
   - 在 `hcloud` 可执行前，只能基于本 skill 的本地资料输出命令方案草稿，不要宣称已查询或修改华为云资源
2. 先发现，再执行
   - 先看 `hcloud --help`
   - 再看 `hcloud <service> --help`
   - 能拿到 operation 帮助时，再看 `hcloud <service> <operation> --help`
3. 查询类默认稳定化
   - 默认使用 `--cli-output=json`
   - 需要提炼时再加 `--cli-query`
   - 大结果默认先限制 `limit` 或筛选字段
   - `ListImages`、`ListFlavors`、`ListFlavorSellPolicies` 等大列表 API 默认视为高风险大输出；如果需要全量或大范围核验，优先考虑 `--result-file` / `--parsed-json-file` 落盘，只把条数、关键字段样本、摘要和文件位置带回对话
4. 复杂参数不要硬拼长命令
   - 优先 `--skeleton`
   - 或使用 `--cli-jsonInput`
5. 变更类先做预执行
   - 默认先用 `python3 scripts/hcloud_change_plan.py ...` 生成风险摘要和 dry-run/submit 命令
   - 支持 dry-run 的操作默认先加 `--dryrun`
   - 复杂创建类优先先补齐依赖项，再进入真实执行
6. 返回为空时显式校验
   - 为空不代表失败
   - 必要时加 `--debug` 查看状态码
7. 失败时按错误类型处理
   - 先看 `references/error-playbook.md`
   - 不要在未知错误上反复重试同一个命令

## 推荐脚本入口

详细命令模板和参数边界放在 `references/scripts.md`。这里仅保留任务到脚本的选择索引；需要具体命令时再读取该 reference。

| 任务 | 首选脚本 | 说明 |
| --- | --- | --- |
| 上下文/认证/region/project 检查 | `hcloud_context_inspect.py` | 真实云任务第一步。 |
| 环境体检/安装配置建议 | `hcloud_environment_doctor.py` | check-only 检查 hcloud/profile、SDK、Terraform、obsutil、MaaS key 和代理；不安装、不改配置、不调用云 API。 |
| 自然语言场景路由 | `hcloud_scenario_router.py` | 把目标映射到本地 playbook、指南、planner、SDK 补充点和 Terraform 候选；会用本地服务别名扩展中文口语，不执行云操作。 |
| 多轮任务前缓存预热 | `hcloud_prewarm_cache.py` | 预热 service/operation help。 |
| 真实 hcloud 查询或系统命令 | `hcloud_safe_exec.py` | 默认 JSON、脱敏、错误分桶；权限失败会附带本地 IAM action hint。 |
| 本地 KooCLI metadata 探查 | `hcloud_meta_lookup.py` | 查 service/operation detail cache。 |
| SDK 参数/region 补充 | `hcloud_sdk_catalog.py` | 读取已安装 SDK package 或维护期源码 fallback；只补证据，不执行云调用。 |
| SDK allowlist 只读桥 | `hcloud_sdk_readonly.py` | 仅执行 `sdk-supplement-registry.json` 登记的稳定只读补充；保留 hcloud fallback。 |
| Terraform 环境检查 | `hcloud_terraform_context_inspect.py` | 检查 Terraform CLI、hcloud、环境变量、provider cache 和禁止提交的运行时产物。 |
| Terraform 资产路由 | `hcloud_terraform_router.py` | 按用户意图从 73 个示例和 reference catalog 中选少量资产；只路由，不执行 plan/apply。 |
| Terraform catalog 维护 | `hcloud_terraform_catalog.py` | 生成 `references/terraform/catalog/*.json`；修改示例或 reference 后运行。 |
| Terraform provider inventory 维护 | `hcloud_terraform_provider_inventory.py` | 从本地 provider Markdown docs 重建 inventory，并可按需抽取 ForceNew/Import/敏感字段信号；只读维护/评审，不执行 import/apply。 |
| generated catalog 审计/重建 | `hcloud_catalog_audit.py`、`build_hcloud_catalog.py` | 运行时走 index/per-service 懒加载；full catalog 只作为可选本地临时产物，不提交、不直接 Read 大 JSON。 |
| ECS 创建前校验 | `hcloud_ecs_create_plan.py` | 检查 JSON、凭证、安全组和 dry-run/submit 命令。 |
| ECS job 终态 | `hcloud_ecs_wait_job.py` | job 终态不等同于 ECS 可用。 |
| ECS ACTIVE 验证 | `hcloud_ecs_verify_active.py` | 之后还要做 SSH/应用验收。 |
| COC/远程执行边界 | `references/playbooks/coc-readiness.md` | 判断 COC 可用性；不可用时按 SSH、cloud-init、重装/重建等受控 fallback 收敛。 |
| 低成本网站托管 | `references/playbooks/entry-level-web-hosting.md` | 为 OBS 静态站、Flexus L/轻量服务器、ECS 路径做小白/小企业选型和验收边界。 |
| list/count 资源发现 | `hcloud_resource_discovery.py` | registry 或 metadata-backed discovery；默认不执行。 |
| 账号资源盘点 | `hcloud_account_inventory.py` | 核心服务跨服务、跨 region、EPS scope 的只读盘点 planner；`--execute` 才真实查询。 |
| 闲置资源审计 | `hcloud_idle_audit.py` | 从已保存 JSON 查询结果识别 EIP/EVS/ECS/ELB/RDS/NAT 闲置候选，保留 region/EPS/tag 维度，不生成删除命令。 |
| 拆除/回收评审计划 | `hcloud_teardown_plan.py` | 从 idle audit 候选生成 planner-only 回收检查顺序；不生成 submit 命令。 |
| 可观测前置计划 | `hcloud_observability_plan.py` | 为资源生成状态复核 + CES 指标发现的只读闭环计划。 |
| CES 告警计划 | `hcloud_ces_alarm_plan.py` | CES metric/alarm 只读发现 + 告警规则 planner-only 草案；输出 SYS.ECS/AGT.ECS/Agent 指标提示，不 submit。 |
| LTS 日志只读查询 | `hcloud_lts_readonly.py` | LTS log group/stream/logs 只读 planner；日志内容要窄范围处理。 |
| 成本/账单能力探测 | `hcloud_billing_cost_probe.py` | 本地 catalog feasibility probe；不访问真实账单，不承诺已有 Billing API。 |
| 成本/账单只读规划 | `hcloud_billing_readonly.py` | 基于 BSS ontology 生成只读 request spec 和固定 region/lang 的 hcloud safe_exec 命令计划；默认不执行。 |
| 成本/账单结果摘要 | `hcloud_billing_result_summarize.py` | 读取 BSS safe_exec 结果或 JSON，默认只输出摘要；可输出已脱敏记录，不回显账号/资源/订单等原始 ID。 |
| 显式参数只读查询 | `hcloud_resource_query.py` | 目标型 `Show*`/`Get*` 必须显式传参。 |
| OBS 只读查询 | `hcloud_obs_readonly.py` | 走 `hcloud obs`/obsutil，不走普通 OpenAPI 形态。 |
| 服务 readiness | `hcloud_service_readiness.py` | 多服务只读验收，缺目标 ID 则 skipped。 |
| 生命周期闭环计划 | `hcloud_lifecycle_closure_plan.py` | P0 核心服务的六阶段 planner-only 闭环计划，覆盖 VPC/安全组、EIP、EVS、ELB、RDS、OBS、DNS、SCM、CDN、CES/LTS。 |
| 验收探测计划 | `hcloud_acceptance_probe_plan.py` | 从 lifecycle plan 生成非执行 probe 模板，不实际访问网络或云资源。 |
| 验收结果判定 | `hcloud_acceptance_evidence_result.py` | 读取 lifecycle plan 和本地 evidence status JSON，输出 passed/warning/missing/blocked。 |
| 闭环成熟度审计 | `hcloud_closure_maturity_audit.py` | 本地审计当前闭环层级，不执行 hcloud、SDK 或 Terraform。 |
| 治理闭环计划 | `hcloud_governance_closure_plan.py` | P1 治理服务的 planner-only 闭环计划，覆盖 TMS、CTS、CBR、RMS/Config、Billing/BSS、WAF、DLI、CodeArtsRepo，并输出 evidence command plan 和治理汇总。 |
| P2 场景闭环计划 | `hcloud_p2_scenario_closure_plan.py` | P2 场景服务的 planner-only 闭环计划，覆盖 CCE、NAT、DCS、RFS、UCS、IAM/KPS/IMS、安全姿态和数据库族，并诚实标注 metadata evidence gap。 |
| Terraform/IaC 工作流 | `references/terraform-workflow.md`、`references/terraform/README.md` | 当用户明确需要可重复 IaC、环境复制、import/drift 或长期纳管时读取；Terraform 不替代 hcloud 发现和后置验证。 |
| registry 多服务 smoke | `hcloud_readonly_smoke.py` | 只读 smoke；`--execute` 才真实查询。 |
| metadata-backed smoke | `hcloud_catalog_readonly_smoke.py` | 小批只读矩阵和失败分桶。 |
| curated 晋级审计 | `hcloud_curated_promotion_audit.py` | 校验 profile、playbook、risk profile 和 live-smoke 门槛。 |
| 通用变更风险计划 | `hcloud_change_plan.py` | 非执行 planner，含安全组入口策略检查。 |
| 服务级变更计划 | `hcloud_service_change_plan.py` | curated + metadata-backed planner-only。 |
| 通用 guarded change flow | `hcloud_guarded_change_flow.py` | 普通服务 Plan -> dry-run -> guarded submit -> verify。 |
| EIP guarded flow | `hcloud_eip_change_flow.py` | EIP 专用闭环。 |
| OBS 变更计划 | `hcloud_obs_change_plan.py` | OBS bucket/lifecycle/policy planner-only。 |
| 离线资源验收 | `hcloud_resource_verify.py` | 从 JSON 结果验证资源字段，不访问云端。 |
| 问题集/覆盖回归 | `check_question_coverage.py` | 离线 schema、风险和执行路径门禁。 |
| MaaS 站点图片资产 | `maas_text_to_image.py` | 仅用于华为云站点部署图片资产；`qwen_text_to_image.py` 为兼容旧入口。 |

变更类脚本的共同边界：默认只生成计划；真实 submit 必须有用户对本次操作的明确确认。metadata-backed mutation 的 dry-run 默认为 `unknown`，安全合规、身份、密钥和治理类服务会进入 `hard_guard`，通用 guarded flow 不得自动执行 submit。

## 默认执行规则

- 不要为了默认上下文就先追问 AK/SK。
- 当前配置可用时，优先复用已有 profile。
- 系统参数统一优先使用 `cli-*` 新参数名。
- 查询类默认走 JSON 输出，不默认走 table。
- 复杂 body 优先 `--cli-jsonInput`，不要手工拼几百字符命令。
- ECS 创建类 JSON 先用 `hcloud_ecs_create_plan.py` 检查占位符和关键字段。
- ECS 创建类 JSON 必须通过登录凭证门禁：`key_name` 和 `adminPass` 二选一；选择 `key_name` 时说明本地私钥验证方式，选择 `adminPass` 时说明密码 artifact 保存位置。
- ECS 创建类 JSON 写入安全组前，先用 `ListSecurityGroupRules` 或 `ShowSecurityGroup` 取得规则证据；`hcloud_ecs_create_plan.py` 引用已有安全组 ID 时必须传入 `--security-group-evidence-file`。当补规则被 `vpc:securityGroupRules:create` SCP/IAM 拒绝时，允许复用同 VPC/企业项目内已开放所需端口的现有安全组，但必须记录原目标安全组、复用安全组 ID/规则和拒绝错误。
- 变更类默认先查证据，再用 `hcloud_change_plan.py` 生成风险计划，再 `--dryrun`，再执行。
- ECS 创建类真实提交后，必须先用 `hcloud_ecs_wait_job.py` 或等价 `ShowJob` 查询 job 终态，再用 `hcloud_ecs_verify_active.py` 或等价查询确认目标实例 `ACTIVE`。
- ECS `ACTIVE` 后必须按 `references/playbooks/ecs-ssh-access-readiness.md` 做 SSH 验收；如果目标任务还包含 Web/Docker/WordPress 等应用，再进入对应服务 readiness。
- `--cli-waiter` 有重复调用风险，默认只建议用于查询或状态轮询。
- 华为云站点部署中如需生成图片资产，先读取 `references/maas-image-generation.md`，通过华为云 ModelArts MaaS 生成本地资产并完成图片质量检查后再部署。
- 用户明确要 Terraform/IaC 时，先运行 `hcloud_terraform_context_inspect.py` 和 `hcloud_terraform_router.py`；只读取 router 命中的少量 example/reference。只读排障、状态核验和一次性 hcloud 变更不要强行转 Terraform。
- 如果 live help 因网络或元数据问题失败，改走本地 meta cache 和 `references/`，不要瞎猜参数。

## 当前版本覆盖

当前版本重点覆盖以下内容：

- Huawei CLI 基本上下文探查
- Huawei CLI 本地 meta cache 发现
- `hcloud` 命令发现与构造
- CLI 认证、区域、项目和缓存问题排查
- ECS 查询与创建前准备
- ECS 创建 JSON 本地校验、dry-run 命令生成、job 终态轮询和 ACTIVE 资源验证
- COC/SSH fallback 和低成本网站托管 playbook，用于小白/小企业部署、排障和机内执行边界
- service registry、只读资源发现、通用变更风险计划、run journal、材料漂移检查和问题集回归检查
- 账号资源盘点 planner 和离线闲置资源候选审计，面向“管好云”的只读摸底与治理前置分析
- planner-only teardown review，用于按依赖顺序评审闲置候选的回收前检查，不直接执行删除/释放/退订
- 基于 CES `ListMetrics` 的可观测前置计划，用于先发现 namespace/metric/dimension，再结合资源状态和协议验收判断健康
- CES alarm planner-only 和 LTS read-only 日志查询 planner，配套 `references/playbooks/observability-readiness.md`
- Billing/Cost 生成官方 API request spec 和 BSS hcloud safe_exec 命令计划；不从资源清单推断费用，也不默认执行真实账单查询
- Billing/Cost 本地 feasibility probe，用于确认当前 bundled catalog 是否具备账单/成本直接候选；v0.3.1 可发现 metadata-backed `BSS`，但当前不等同于真实账单查询能力
- curated promotion audit 输出 `value_ranked_candidates`，用于按“上好云、用好云、管好云”价值维度选择下一批治理候选
- `hcloud_lifecycle_closure_plan.py` 提供 P0 核心服务的 planner-only 闭环计划入口，覆盖 VPC/安全组、EIP、EVS、ELB、RDS、OBS、DNS、SCM、CDN、CES/LTS，并把上下文/依赖发现、参数检查、风险门禁、受控执行、后置验证和治理审计统一成六阶段输出
- `hcloud_acceptance_probe_plan.py` 和 `hcloud_acceptance_evidence_result.py` 把 P0 lifecycle plan 继续推进到“如何采证”和“采到后如何判定”；前者只生成非执行模板，后者只读取本地 evidence status JSON
- `hcloud_closure_maturity_audit.py` 汇总当前成熟度层级，避免把 planner-only、metadata-backed evidence gap 或 request spec 误说成完整执行闭环
- `hcloud_governance_closure_plan.py` 提供 P1 治理闭环计划入口，覆盖 TMS、CTS、CBR、RMS/Config、Billing/BSS、WAF、DLI、CodeArtsRepo，把治理范围、只读 evidence command plan、风险/隐私门禁、review plan、治理汇总和 curated 晋级缺口统一输出；Billing/BSS 只生成 request spec 和需确认的 hcloud 命令计划，不默认执行
- `hcloud_p2_scenario_closure_plan.py` 提供 P2 场景闭环计划入口，覆盖 CCE、NAT、DCS、RFS、UCS、IAM/KPS/IMS、安全姿态和数据库族，把容器、网络、缓存、IaC、多集群、依赖、安全、数据库场景先收敛成只读 evidence plan、风险边界和下一步晋级缺口；安全和数据库族当前保持 metadata evidence gap，不宣称 curated 完整闭环
- Terraform 资产面已吸收 73 个示例和核心 provider/reference/inventory 文档；当前 provider inventory 快照来自本地 `1.93.0` reference，覆盖 1689 个 resource 和 2251 个 data source。运行时通过 `hcloud_terraform_router.py` 和 catalog 渐进选择，不默认全量读取。Terraform 可以生成和验证 IaC 草案，但 apply 仍需用户确认，完成后仍回到 hcloud 做状态和业务验收
- VPC / IMS / KPS / IAM / EIP 创建前只读发现方法
- VPC / IMS / KPS / ELB / EVS / NAT / DNS / SCM 等服务的第一层资源级只读查询登记
- ELB / EVS / NAT / RDS / CCE / CDN / DNS / SCM / CES 的低覆盖查询登记，用于离线数据集回归和前置发现
- 多服务只读 smoke、planner-only 变更计划和 JSON 结果验收脚本
- MaaS 图像生成辅助脚本，用于华为云站点部署时通过华为云 ModelArts MaaS 生成本地 Web 图片资产；主入口为 `maas_text_to_image.py`，旧 `qwen_text_to_image.py` 保留兼容
- OBS `hcloud obs`/obsutil 只读适配器和 planner-only bucket/lifecycle/policy 变更计划
- `hcloud_resource_detail_probe.py` 可对 EVS/NAT 等服务做 list-then-detail 抽样，有资源时执行 detail，无资源时结构化 skipped

当前对 ECS 的 guidance 最完整。P0/P1/P2 已分别形成 lifecycle、governance、scenario 三类 planner-only 闭环计划。对 IAM、VPC、IMS、KPS、EIP、DCS、RFS、UCS 主要提供工作流、发现方法和部分目标查询；对 ELB、EVS、NAT、RDS、CCE、CDN、DNS、SCM、OBS、CES 提供低覆盖查询登记、第一层目标查询和 planner-only 计划。安全姿态和数据库族长尾服务仍以 metadata-backed evidence gap 为主，不等同于 curated registry 覆盖；Billing/Cost 当前生成 request spec 和 BSS hcloud 命令计划，但不默认执行真实账单请求。

当前版本已经补了本地 meta cache 发现脚本和创建类示例模板；非 ECS 服务的 operation detail 缓存可能不完整，脚本会在缺少参数元数据时保守省略可选参数。

## 示例模板

示例文件放在 `examples/` 下。

当前重点提供：

- ECS `CreateServers` 的 `cli-jsonInput` 模板
- ECS `CreatePostPaidServers` 的 `cli-jsonInput` 模板
- 对应的 dry-run 命令说明

这些示例主要用于：

- 构造可审查的请求骨架
- 指导用户替换真实 ID 和参数
- 避免把几十个字段硬编码进一行命令

## 禁止事项

- 不要把 raw `materials/` 当成唯一事实来源直接复述。
- 不要在未确认上下文前直接执行高风险删除或不可逆变更。
- 不要把真实 AK/SK、token、密码写进文档、日志或最终回复。
- 不要把表格输出当成机器可稳定解析的默认格式。
- 本 skill 负责 CLI/KooCLI 主链路；Terraform/IaC 只在用户明确要求、场景路由命中或长期纳管确有价值时接管，并且必须保持 hcloud 发现、plan 确认和 hcloud 后置验证。
