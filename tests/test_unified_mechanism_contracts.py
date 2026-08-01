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
        self.assertIn("task 级独立 workspace", skill)
        self.assertIn("多个 task 共用一个 workspace", skill)
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

    def test_templates_define_minimum_semantics_without_fixed_execution(self) -> None:
        task_template = read_text("templates/task.md")
        progress_template = read_text("templates/progress.md")

        for field in (
            "task_id",
            "goal",
            "important_constraints",
            "expected_outcome",
            "status",
            "current_approach",
            "recent_progress",
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
        ):
            self.assertIn(phrase, scenarios)


if __name__ == "__main__":
    unittest.main()
