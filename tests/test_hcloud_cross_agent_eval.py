"""Tests for the portable cross-Agent evaluation kit."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):  # noqa: ANN201
    """Load one repository script for isolated unit tests."""

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hcloud_cross_agent_eval = load_module(
    "hcloud_cross_agent_eval",
    SCRIPTS / "hcloud_cross_agent_eval.py",
)


class HcloudCrossAgentEvalTest(unittest.TestCase):
    """Validate scenario rendering and observation aggregation locally."""

    def test_pack_has_portable_read_plan_and_opt_in_live_cases(self) -> None:
        pack = hcloud_cross_agent_eval.load_pack()
        cases = {item["id"]: item for item in pack["cases"]}

        self.assertEqual(pack["schema_version"], 1)
        self.assertIn("inventory-beijing4", cases)
        self.assertIn("elb-delete-dependency-plan", cases)
        self.assertIn("ecs-create-uname-cleanup", cases)
        self.assertEqual(cases["inventory-beijing4"]["cloud_mutation"], "none")
        self.assertEqual(cases["elb-delete-dependency-plan"]["cloud_mutation"], "none")
        self.assertEqual(cases["ecs-create-uname-cleanup"]["cloud_mutation"], "explicit_opt_in")

    def test_result_template_is_agent_and_model_neutral(self) -> None:
        template = hcloud_cross_agent_eval.build_result_template(
            "inventory-beijing4",
            run_id="run-001",
        )

        self.assertEqual(template["run_id"], "run-001")
        self.assertEqual(template["case_id"], "inventory-beijing4")
        self.assertIsNone(template["agent"])
        self.assertIsNone(template["model"])
        self.assertEqual(template["real_cloud_mutation"], "none")
        self.assertGreater(len(template["checks"]), 0)

    def test_completed_observation_validates_and_scores_checks(self) -> None:
        template = hcloud_cross_agent_eval.build_result_template(
            "inventory-beijing4",
            run_id="run-001",
        )
        template.update({"agent": "example-agent", "model": "example-model"})
        for item in template["checks"]:
            item.update({"status": "pass", "evidence": "trace:item"})
        template["hard_failures"] = []

        result = hcloud_cross_agent_eval.validate_result(template)

        self.assertTrue(result["valid"])
        self.assertEqual(result["score"]["passed"], result["score"]["total"])
        self.assertEqual(result["score"]["result"], "pass")

    def test_hard_failure_forces_failed_result(self) -> None:
        template = hcloud_cross_agent_eval.build_result_template(
            "ecs-create-uname-cleanup",
            run_id="run-002",
        )
        template.update({"agent": "example-agent", "model": "example-model"})
        for item in template["checks"]:
            item.update({"status": "pass", "evidence": "trace:item"})
        template["hard_failures"] = [
            {"category": "duplicate_side_effect", "evidence": "trace:42"}
        ]

        result = hcloud_cross_agent_eval.validate_result(template)

        self.assertTrue(result["valid"])
        self.assertEqual(result["score"]["result"], "fail")

    def test_aggregate_preserves_agent_model_and_raw_counts(self) -> None:
        run = hcloud_cross_agent_eval.build_result_template(
            "inventory-beijing4",
            run_id="run-003",
        )
        run.update({"agent": "agent-a", "model": "model-a"})
        for item in run["checks"]:
            item.update({"status": "pass", "evidence": "trace:item"})
        run["hard_failures"] = []

        result = hcloud_cross_agent_eval.aggregate_results([run])

        self.assertEqual(result["run_count"], 1)
        self.assertEqual(result["groups"][0]["agent"], "agent-a")
        self.assertEqual(result["groups"][0]["model"], "model-a")
        self.assertEqual(result["groups"][0]["passed_runs"], 1)

    def test_docs_and_manifest_expose_eval_kit_without_auto_execution(self) -> None:
        docs = (ROOT / "references" / "cross-agent-evaluation.md").read_text(
            encoding="utf-8"
        )
        manifest = json.loads(
            (ROOT / "references" / "script-audience-manifest.json").read_text()
        )

        self.assertIn("不自动执行 Agent", docs)
        self.assertIn("不访问华为云", docs)
        self.assertEqual(
            manifest["public_script_contracts"]["scripts/hcloud_cross_agent_eval.py"]["cloud_access"],
            "none",
        )


if __name__ == "__main__":
    unittest.main()
