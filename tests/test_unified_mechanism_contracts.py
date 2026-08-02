"""Contract tests for the lightweight unified-task mechanism."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    """Read one UTF-8 project asset by its repository-relative path."""
    return (ROOT / relative_path).read_text(encoding="utf-8")


class UnifiedMechanismContractsTest(unittest.TestCase):
    """Keep the first unified mechanism small, portable, and agent-owned."""

    def test_skill_requires_durable_memory_for_complex_tasks(self) -> None:
        skill = read_text("SKILL.md")

        for reference in (
            "references/unified-principles.md",
            "references/task-workspace-guide.md",
            "references/goal-capability-guide.md",
        ):
            self.assertIn(reference, skill)

        self.assertIn("Agent 仍然负责", skill)
        self.assertIn("自己的 workspace", skill)
        self.assertIn("简单查询", skill)
        self.assertIn("不要求创建 task 记录", skill)
        self.assertIn("必须在首次实质规划或执行前", skill)
        self.assertIn("文件读写工具", skill)
        self.assertIn("运行时待办", skill)
        self.assertIn("不算完成记录", skill)
        self.assertIn("task 级独立 workspace", skill)
        self.assertIn("多个 task 共用一个 workspace", skill)
        self.assertIn("同一 task", skill)
        self.assertIn("必须立即重新分类", skill)
        self.assertIn("下一项实质规划或执行前", skill)
        self.assertIn("进入付费、真实变更或异步等待前", skill)
        self.assertIn("可信摘要", skill)
        self.assertIn("必须更新", skill)
        self.assertIn("恢复任务时先读取", skill)

    def test_required_assets_exist(self) -> None:
        for relative_path in (
            "references/unified-principles.md",
            "references/task-workspace-guide.md",
            "references/goal-capability-guide.md",
            "templates/task.md",
            "templates/progress.md",
            "tests/unified-mechanism-scenarios.md",
            "tests/unified-mechanism-evaluation.md",
            "docs/unified-task-mechanism-implementation.md",
        ):
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())

    def test_workspace_guidance_keeps_state_agent_owned_and_flexible(self) -> None:
        guide = read_text("references/task-workspace-guide.md")

        for phrase in (
            "Agent 自己的 workspace",
            "task 级 workspace",
            "共享 workspace",
            "优先复用运行时",
            "当前 workspace",
            "tasks/<task_id>/",
            "不依赖 PID",
            "必须持久化",
            "首次实质规划或执行前",
            "每轮收到用户",
            "立即重新分类",
            "下一项实质规划或执行前",
            "轻量恢复检查",
            "付费调用、真实云变更或异步等待前",
            "可信摘要",
            "当前目标",
            "关键约束",
            "最近重要进展",
            "下一步",
            "AK/SK",
            "写入失败",
            "不能声称已经落盘",
        ):
            self.assertIn(phrase, guide)

        self.assertIn("可以合并", guide)
        self.assertIn("可以增加", guide)
        self.assertNotIn("不可变 TaskContract", guide)
        self.assertNotIn("固定状态机", guide)
        self.assertNotIn("每查看两次", guide)
        self.assertNotIn("PreToolUse", guide)

    def test_templates_define_minimum_semantics_without_fixed_execution(self) -> None:
        task_template = read_text("templates/task.md")
        progress_template = read_text("templates/progress.md")

        for field in (
            "task_id",
            "goal",
            "important_constraints",
            "authorization_boundary",
            "expected_outcome",
            "status",
            "current_approach",
            "recent_progress",
            "important_changes_or_failures",
            "evidence_and_artifacts",
            "open_questions",
            "next_step",
            "last_updated",
        ):
            self.assertIn(field, task_template)

        for field in (
            "用户变化",
            "关键结果",
            "依据或 artifact",
            "当前缺口",
            "下一步",
        ):
            self.assertIn(field, progress_template)

        combined = f"{task_template}\n{progress_template}"
        for forbidden in ("api_sequence", "fixed_parameters", "immutable_plan"):
            self.assertNotIn(forbidden, combined)

    def test_task_identity_has_portable_runtime_fallback(self) -> None:
        skill = read_text("SKILL.md")
        guide = read_text("references/task-workspace-guide.md")
        task_template = read_text("templates/task.md")

        for phrase in (
            "运行时 task ID 对 Agent 可见",
            "Agent 生成",
            "后续轮次",
            "不得冒充平台 ID",
        ):
            self.assertIn(phrase, guide)

        self.assertIn("task_id_source", task_template)
        self.assertIn("runtime", task_template)
        self.assertIn("agent-generated", task_template)
        self.assertIn("不可见", skill)
        self.assertIn("稳定任务描述符", skill)
        self.assertIn("缺少任一项不算完成建档", skill)

        combined = f"{skill}\n{guide}\n{task_template}"
        self.assertNotIn("CLOUD_CLAW_ACTION_TASK_RUN_ID", combined)
        self.assertNotIn("current-workspace 作为 task ID", combined)

    def test_side_effect_recovery_tracks_logical_resources_without_fixed_execution(self) -> None:
        skill = read_text("SKILL.md")
        safety = read_text("references/runtime-safety-boundaries.md")
        workspace_guide = read_text("references/task-workspace-guide.md")
        reconcile = read_text("references/playbooks/resource-idempotency-reconcile.md")
        task_template = read_text("templates/task.md")

        for phrase in (
            "逻辑角色",
            "预期数量",
            "canonical 资源",
            "待决操作",
            "结果未知",
            "先回读收敛",
        ):
            self.assertIn(phrase, skill)

        for phrase in (
            "同一逻辑角色",
            "一换一替换",
            "旧资源已不存在",
            "重新说明并取得确认",
            "不是连续重建授权",
            "cloud-init",
            "普通 stdout/stderr",
            "不固定具体 API、参数或完整调用顺序",
        ):
            self.assertIn(phrase, safety)

        for phrase in (
            "资源生命周期摘要",
            "expected_count",
            "canonical_resource",
            "pending_operation",
            "last_verified_at",
            "实时回读",
        ):
            self.assertIn(phrase, workspace_guide)
            self.assertIn(phrase, task_template)

        for phrase in (
            "名称不同",
            "逻辑角色",
            "待决 create/delete",
            "没有待决动作",
            "删除终态",
            "旧资源已不存在",
            "连续替换",
        ):
            self.assertIn(phrase, reconcile)

        combined = "\n".join((skill, safety, workspace_guide, reconcile, task_template))
        for forbidden in ("fixed_api_sequence", "mandatory_runtime_controller"):
            self.assertNotIn(forbidden, combined)

    def test_shared_principles_cover_scope_freshness_and_completion(self) -> None:
        principles = read_text("references/unified-principles.md")

        for phrase in (
            "用户声明",
            "Agent 推断",
            "工具观测",
            "source",
            "observed_at",
            "scope",
            "planned",
            "submitted",
            "resource_ready",
            "business_verified",
            "partially_succeeded",
            "outcome_unknown",
        ):
            self.assertIn(phrase, principles)

        self.assertIn("references/runtime-safety-boundaries.md", principles)
        self.assertIn("references/error-playbook.md", principles)

    def test_goal_capability_sample_reuses_existing_sources_and_allows_alternatives(self) -> None:
        guide = read_text("references/goal-capability-guide.md")

        for phrase in (
            "候选能力",
            "替代路径",
            "已知缺口",
            "信息来源",
            "references/scenario-router.json",
            "references/playbooks/entry-level-web-hosting.md",
            "references/playbooks/web-application-production-readiness.md",
        ):
            self.assertIn(phrase, guide)

        self.assertIn("不是唯一方案", guide)
        self.assertNotIn("固定调用顺序", guide)

    def test_behavior_scenarios_measure_benefit_and_cost(self) -> None:
        scenarios = read_text("tests/unified-mechanism-scenarios.md")

        for phrase in (
            "v0.8.2 基线",
            "v0.9.1 直接基线",
            "Plus 候选",
            "消融条件",
            "至少重复三次",
            "task 级 workspace",
            "共享 workspace",
            "运行时 task ID",
            "必须落盘",
            "目标保留",
            "任务隔离",
            "未知场景适应",
            "结论依据",
            "简单任务负担",
            "上下文清空",
            "同一 task 从简单查询升级",
            "下一项实质规划或执行前",
            "任务升级识别",
            "逻辑资源收敛",
            "删除 job 仍未确认终态",
            "禁止创建第二台同角色 ECS",
            "敏感输出边界",
        ):
            self.assertIn(phrase, scenarios)

    def test_plus_evaluation_protocol_is_reproducible_and_non_executing(self) -> None:
        evaluation = read_text("tests/unified-mechanism-evaluation.md")

        for phrase in (
            "v0.9.1 直接基线",
            "Plus 候选",
            "消融条件",
            "至少重复三次",
            "运行标识",
            "Agent 和模型",
            "工具权限",
            "workspace 拓扑",
            "真实云变更",
            "分子",
            "分母",
            "task 落盘采用率",
            "重要变化更新率",
            "恢复成功率",
            "目标能力完整率",
            "完成准确率",
            "副作用收敛率",
            "自主调整成功率",
            "简单任务负担",
            "没有读取 Skill",
            "读取但没有采用",
            "采用后仍然失败",
            "安全硬失败",
            "失败样例",
            "不自动执行 Agent",
        ):
            self.assertIn(phrase, evaluation)

        scenarios = read_text("tests/unified-mechanism-scenarios.md")
        implementation = read_text("docs/unified-task-mechanism-implementation.md")
        self.assertIn("tests/unified-mechanism-evaluation.md", scenarios)
        self.assertIn("tests/unified-mechanism-evaluation.md", implementation)
        self.assertIn("v0.9.1 直接行为基线", implementation)
        self.assertIn("18 次正式运行", implementation)
        self.assertIn("不外推", implementation)

    def test_plus_target_expansion_has_distinct_behavior_cases(self) -> None:
        scenarios = read_text("tests/unified-mechanism-scenarios.md")
        evaluation = read_text("tests/unified-mechanism-evaluation.md")

        for phrase in (
            "E1：跨服务资源盘点",
            "account、project、region",
            "覆盖、失败、部分结果和未查询项",
            "不能从资源清单推断账单金额",
            "E2：成本治理",
            "fact × grain × money_basis × scope × billing_period",
            "优化候选不等于执行授权",
            "不能把历史账单直接写成未来节省承诺",
        ):
            self.assertIn(phrase, scenarios)

        for phrase in (
            "UM-E1-CROSS-SERVICE-INVENTORY",
            "UM-E2-COST-GOVERNANCE",
            "现有切片 0 场景不能衡量",
        ):
            self.assertIn(phrase, evaluation)

    def test_implementation_doc_describes_current_scope(self) -> None:
        implementation = read_text("docs/unified-task-mechanism-implementation.md")

        for phrase in (
            "v0.9.0",
            "反推目标",
            "Agent 必须使用",
            "运行时待办",
            "平台自动日志",
            "task 级 workspace",
            "多个 task 共用 workspace",
            "不要求固定 Schema",
            "创建偏晚",
            "升级时创建、变化时更新、恢复时读取",
            "plus 版",
            "逻辑资源",
            "预期数量",
            "待决操作",
            "一换一替换",
            "三台同角色 ECS",
            "不固定具体 API、参数和完整调用顺序",
        ):
            self.assertIn(phrase, implementation)

        self.assertIn("unified-task-mechanism-implementation.md", read_text("docs/README.md"))
        self.assertIn("docs/unified-task-mechanism-implementation.md", read_text("README.md"))


if __name__ == "__main__":
    unittest.main()
