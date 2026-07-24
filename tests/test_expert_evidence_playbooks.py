"""Regression tests for expert evidence and diagnostic playbook invariants."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOKS = ROOT / "references" / "playbooks"


class ExpertEvidencePlaybooksTest(unittest.TestCase):
    """Keep expert judgment chains available without adding an executor."""

    def read_playbook(self, name: str) -> str:
        """Return one playbook as UTF-8 text."""
        return (PLAYBOOKS / name).read_text(encoding="utf-8")

    def assert_contains_all(self, content: str, values: tuple[str, ...]) -> None:
        """Assert that all required evidence terms remain in a playbook."""
        for value in values:
            with self.subTest(value=value):
                self.assertIn(value, content)

    def test_cci_preserves_cli_blocker_and_exec_degradation(self) -> None:
        content = self.read_playbook("cci-workload-readiness.md")

        self.assert_contains_all(
            content,
            (
                "包含点号的 annotation key",
                "创建后必须回读对象",
                "当前版本相关的 CLI 序列化阻塞",
                "exec 失败不等于容器故障",
                "status、events、container state",
            ),
        )

    def test_cce_preserves_metric_and_alarm_semantics(self) -> None:
        content = self.read_playbook("cce-cloud-native-assessment.md")

        self.assert_contains_all(
            content,
            (
                "ServiceMonitor",
                "PodMonitor",
                "NXDOMAIN",
                "WATCH/CONNECT",
                "active 为空不能证明",
                "resource ID",
                "只决定下一条证据",
            ),
        )

    def test_ucs_separates_identity_completion_and_compliance(self) -> None:
        content = self.read_playbook("ucs-fleet-readiness.md")

        self.assert_contains_all(
            content,
            (
                "源 CCE cluster ID",
                "UCS 分配的 cluster ID",
                "UCS 管理面",
                "status.phase=Available",
                "warn",
                "job `Success`",
                "不等于目标资源全部合规",
            ),
        )

    def test_flexus_and_coc_preserve_layered_completion_context(self) -> None:
        flexus = self.read_playbook("flexus-l-readiness.md")
        coc = self.read_playbook("coc-readiness.md")

        self.assert_contains_all(
            flexus,
            ("订单/请求", "管理通道", "远程任务", "应用功能", "完成到第几层"),
        )
        self.assert_contains_all(
            coc,
            ("coc_service_region", "target_instance_region", "provider", "resource_id"),
        )

    def test_dws_preserves_cpu_memory_and_io_attribution_boundaries(self) -> None:
        content = self.read_playbook("dws-diagnostic-method.md")

        self.assert_contains_all(
            content,
            (
                "ctime",
                "duration_ms",
                "cpu_rate",
                "CN/DN",
                "idle session",
                "throughput",
                "IOPS",
                "latency/await",
                "io_read",
                "不能写成“I/O Top SQL”",
            ),
        )

    def test_modelarts_preserves_progressive_training_evidence(self) -> None:
        content = self.read_playbook("observability-readiness.md")

        self.assert_contains_all(
            content,
            (
                "job detail",
                "failure analysis / task message",
                "target task log preview",
                "临时 OBS 完整日志 URL",
                "Running",
                "wrapper 异常",
                "置信度和缺失证据",
            ),
        )

    def test_icp_preserves_scope_and_current_evidence_boundary(self) -> None:
        content = self.read_playbook("obs-static-website-hosting.md")

        self.assert_contains_all(
            content,
            (
                "规则 × 适用范围 × 当前官方证据",
                "查询日期",
                "ICP 备案",
                "公安备案",
                "经营性许可",
                "evidence_gap",
                "不能作为最终事实",
            ),
        )

    def test_each_enhancement_family_has_three_way_regression_scenarios(self) -> None:
        scenarios = (ROOT / "tests" / "expert-evidence-scenarios.md").read_text(encoding="utf-8")

        self.assert_contains_all(
            scenarios,
            (
                "CCI-EXPERT-01",
                "CCE-EXPERT-01",
                "UCS-EXPERT-01",
                "FLEXUS-COC-EXPERT-01",
                "DWS-EXPERT-01",
                "MODELARTS-EXPERT-01",
                "ICP-EXPERT-01",
            ),
        )
        self.assertEqual(scenarios.count("- 正例："), 7)
        self.assertEqual(scenarios.count("- 易误判反例："), 7)
        self.assertEqual(scenarios.count("- 证据不足："), 7)


if __name__ == "__main__":
    unittest.main()
